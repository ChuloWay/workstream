"""One-use activation authority, live principal checks and immutable replay."""

import copy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.authorization.api import AuthorizationDenied, PreparedAuthorizationInvalid, AuthorizationUnavailable
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.guide_activation import activation_resource, activation_selectors
from app.modules.authorization.runtime import (
    AuthorizationDenied as KernelDenied, AuthorizationEvidenceUnavailable,
    PreparedAuthorizationHandleInvalid, PreparedAuthorizationInput, ServiceAuthorizationContext, ActorKind,
)
from app.modules.actors.api import ServiceIdentity
from .support import Case


async def test_current_manager_consumes_and_replays_exact_evidence(monkeypatch):
    case = Case(monkeypatch)
    async with case.prepare() as handle:
        receipt = await handle.consume_new(case.facts)
    assert receipt.resource_context_digest == case.facts.digest
    assert receipt.admin_role_grant_id == case.grant.id
    assert case.last_filters["exact_project_scope"] is True
    assert case.last_filters["for_update"] is True
    assert len(case.events) == 1
    assert case.events[0].after_facts == dict(allowed=True, resource_context_digest=case.facts.digest)
    assert case.events[0].correlation_id == str(case.facts.locator.operation_id)
    facts = case.facts.model_copy(update={"locator": case.facts.locator.model_copy(update={"request_id": uuid4()})})
    case.context = case.context.model_copy(update={"request_id": facts.locator.request_id})
    async with case.prepare(facts=facts) as handle:
        await handle.validate_replay(facts, receipt.authorization_decision_event_id)
        with pytest.raises(PreparedAuthorizationInvalid):
            await handle.validate_replay(facts, receipt.authorization_decision_event_id)
    assert len(case.events) == 1
    case.grant.status = "revoked"
    with pytest.raises(AuthorizationDenied):
        async with case.prepare(facts=facts):
            pytest.fail("revoked replay authority")


@pytest.mark.parametrize("failure", ["operator", "audit_authority", "finance_authority", "foreign", "system", "revoked", "actor_status", "link_status"])
async def test_requires_live_exact_project_manager(monkeypatch, failure):
    case = Case(monkeypatch)
    if failure == "foreign":
        case.grant.scope_project_id = str(uuid4())
    elif failure == "system":
        case.grant.scope_type = "system"
        case.grant.scope_project_id = None
    elif failure == "revoked":
        case.grant.status = "revoked"
    elif failure in {"actor_status", "link_status"}:
        setattr(case, failure, "suspended" if failure == "actor_status" else "revoked")
    else:
        case.role = failure
    with pytest.raises(AuthorizationDenied):
        async with case.prepare():
            pytest.fail("uncovered authority prepared")
    assert case.events == []


@pytest.mark.parametrize("identity", list(ServiceIdentity))
async def test_service_never_prepares_activation(monkeypatch, identity):
    case = Case(monkeypatch)
    context = ServiceAuthorizationContext(
        **case.context.model_dump(exclude={"actor_kind"}), actor_kind=ActorKind.SERVICE,
        service_identity=identity,
    )
    with pytest.raises(AuthorizationDenied):
        async with case.prepare(context=context):
            pytest.fail("service prepared activation")
    assert case.events == []


@pytest.mark.parametrize("field", ["actor_profile_id", "identity_link_id", "request_id"])
async def test_locator_cannot_supply_authenticated_identity(monkeypatch, field):
    case = Case(monkeypatch)
    with pytest.raises(AuthorizationDenied):
        async with case.prepare(context=case.context.model_copy(update={field: uuid4()})):
            pytest.fail("foreign context")
    assert case.events == []


@pytest.mark.parametrize("field", ["project_id", "guide_id", "operation_id", "actor_profile_id", "identity_link_id", "request_id", "action_id"])
async def test_prepared_locator_substitution_rejects(monkeypatch, field):
    case = Case(monkeypatch)
    changed = case.facts.model_copy(update={"locator": case.facts.locator.model_copy(update={field: "project.guide.update" if field == "action_id" else uuid4()})})
    async with case.prepare() as handle:
        with pytest.raises(PreparedAuthorizationInvalid):
            await handle.consume_new(changed)
    assert case.events == []


@pytest.mark.parametrize("failure", ["reused", "closed", "new_transaction", "nested", "wrong_session", "copied", "foreign_issuer"])
async def test_handle_lifetime_is_exact(monkeypatch, failure):
    case = Case(monkeypatch)
    async with case.prepare() as handle, case.prepare() as other:
        if failure == "closed":
            handle._service.close()
        elif failure == "reused":
            await handle.consume_new(case.facts)
        elif failure == "new_transaction":
            case.session.root = SimpleNamespace(is_active=True)
        elif failure == "nested":
            monkeypatch.setattr(case.session, "in_nested_transaction", lambda: True)
        elif failure == "wrong_session":
            handle._service._session = type(case.session)()
        elif failure == "copied":
            with pytest.raises(TypeError):
                copy.copy(handle)
            return
        else:
            handle._handle = other._handle
        with pytest.raises(PreparedAuthorizationInvalid):
            await handle.consume_new(case.facts)
    assert len(case.events) == (1 if failure == "reused" else 0)


@pytest.mark.parametrize("field", ["id", "action_id", "actor_id", "permission_id", "resource_id", "project_id", "correlation_id", "after_facts", "matched_grant_id", "request_id"])
async def test_replay_cannot_substitute_original_evidence(monkeypatch, field):
    case = Case(monkeypatch)
    async with case.prepare() as handle:
        receipt = await handle.consume_new(case.facts)
    setattr(case.events[0], field, "invalid")
    async with case.prepare() as handle:
        with pytest.raises(PreparedAuthorizationInvalid):
            await handle.validate_replay(case.facts, receipt.authorization_decision_event_id)
    assert len(case.events) == 1


async def test_direct_kernel_denies(monkeypatch):
    case = Case(monkeypatch)
    async with case.prepare() as handle:
        with pytest.raises(KernelDenied):
            await handle._service._authorization.require(ActionId.PROJECT_GUIDE_ACTIVATE, activation_resource(case.facts))
    assert all(e.after_facts["allowed"] is False for e in case.events)


@pytest.mark.parametrize("family", [None, "post_policy", "guide_activation_extra"])
async def test_unknown_preparation_family_rejects(monkeypatch, family):
    case = Case(monkeypatch)
    value = activation_selectors(case.facts.locator)
    if family is None:
        del value["operation_family"]
    else:
        value["operation_family"] = family
    async with case.prepare() as handle:
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await handle._service.consume(handle._handle, ActionId.PROJECT_GUIDE_ACTIVATE,
                PreparedAuthorizationInput(idempotency_key=case.facts.locator.operation_id, request_value=value),
                activation_resource(case.facts))
    assert case.events == []


async def test_evidence_failure_cannot_allow(monkeypatch):
    case = Case(monkeypatch)

    async def fail(*args):
        raise AuthorizationEvidenceUnavailable("private backend detail")

    monkeypatch.setattr(case, "add_authority_event", fail)
    async with case.prepare() as handle:
        with pytest.raises(AuthorizationUnavailable, match="activation authority unavailable") as error:
            await handle.consume_new(case.facts)
    assert "private backend detail" not in str(error.value)
    assert case.events == []


@pytest.mark.parametrize("field,value", [("action_id", "project.guide.update"), ("project_id", "bad")])
async def test_invalid_locator_never_prepares(monkeypatch, field, value):
    case = Case(monkeypatch)
    facts = case.facts.model_copy(update={"locator": case.facts.locator.model_copy(update={field: value})})
    with pytest.raises(PreparedAuthorizationInvalid):
        async with case.prepare(facts=facts):
            pytest.fail("invalid locator prepared")
    assert case.events == []


async def test_prepare_binds_authenticated_operation_not_caller_selectors(monkeypatch):
    case = Case(monkeypatch)
    async with case.prepare() as handle:
        value = activation_selectors(case.facts.locator)
        value["actor_profile_id"] = str(uuid4())
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await handle._service.consume(handle._handle, ActionId.PROJECT_GUIDE_ACTIVATE,
                PreparedAuthorizationInput(idempotency_key=case.facts.locator.operation_id, request_value=value),
                activation_resource(case.facts))
    assert case.events == []


@pytest.mark.parametrize("resource_kind", ["post_policy", "substituted_activation"])
async def test_raw_prep_rejects_wrong_final_resource(monkeypatch, resource_kind):
    from app.modules.authorization.domain.post_policy import post_policy_resource
    from tests.authorization.post_policy.support import post_facts, APPROVE

    case = Case(monkeypatch)
    resource = (
        post_policy_resource(post_facts(APPROVE, case.facts.locator.project_id))
        if resource_kind == "post_policy"
        else activation_resource(case.facts).model_copy(update={"resource_id": uuid4()})
    )
    async with case.prepare() as handle:
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await handle._service.consume(handle._handle, ActionId.PROJECT_GUIDE_ACTIVATE, handle._input, resource)
    assert case.events == []
