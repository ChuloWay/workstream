"""Live PREP custody and precise retained-decision replay without a database."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.authorization.api import AuthorizationDenied, PreparedAuthorizationInvalid
from app.modules.authorization.runtime import (
    HumanAuthorizationContext,
    ActorKind,
    PreparedAuthorizationHandleInvalid,
)
from app.modules.authorization.domain.post_policy import post_policy_resource
from app.modules.authorization.catalogue import ActionId
from app.modules.actors.api import ServiceIdentity
from .support import Case, DERIVE, APPROVE, CORRECT, READ


@pytest.mark.parametrize("action", [DERIVE, APPROVE, CORRECT, READ])
async def test_current_principal_receives_exact_evidence(monkeypatch, action):
    case = Case(monkeypatch, action)
    async with case.prepare() as handle:
        receipt = await case.consume(handle)
    assert len(case.events) == 1
    event = case.events[0]
    assert event.after_facts == dict(allowed=True, resource_context_digest=case.facts.digest)
    assert event.correlation_id == str(case.facts.locator.operation_id)
    if action == READ:
        assert receipt is None
    else:
        assert receipt.resource_context_digest == case.facts.digest
        assert receipt.admin_role_grant_id == (None if action == DERIVE else case.grant.id)
        assert receipt.service_identity == (case.service_identity if action == DERIVE else None)


@pytest.mark.parametrize(
    "principal",
    [
        "human",
        "forged_service_identity",
        *[
            identity
            for identity in ServiceIdentity
            if identity is not ServiceIdentity.PROJECT_SETUP
        ],
    ],
)
async def test_derive_rejects_other_principals(monkeypatch, principal):
    case = Case(monkeypatch, DERIVE)
    if principal == "human":
        case.actor_kind = "human"
        case.context = HumanAuthorizationContext(
            **case.context.model_dump(exclude={"actor_kind", "service_identity"}),
            actor_kind=ActorKind.HUMAN,
        )
    elif principal == "forged_service_identity":
        case.service_identity = ServiceIdentity.REVIEW_PROJECTION.value
    else:
        case.context = case.context.model_copy(update={"service_identity": principal})
    with pytest.raises(AuthorizationDenied):
        async with case.prepare():
            pytest.fail("uncovered principal prepared")
    assert case.events == []


@pytest.mark.parametrize("action", [DERIVE, APPROVE, CORRECT, READ])
@pytest.mark.parametrize("field", ["actor_status", "link_status"])
async def test_inactive_identity_denies(monkeypatch, action, field):
    case = Case(monkeypatch, action)
    setattr(case, field, "suspended" if field == "actor_status" else "revoked")
    with pytest.raises(AuthorizationDenied):
        async with case.prepare():
            pytest.fail("inactive identity prepared")
    assert case.events == []


@pytest.mark.parametrize("action", [APPROVE, CORRECT, READ])
@pytest.mark.parametrize(
    "principal", ["operator", "audit_authority", "foreign", "system", "revoked"]
)
async def test_manager_requires_current_exact_project_grant(monkeypatch, action, principal):
    case = Case(monkeypatch, action)
    if principal == "foreign":
        case.grant.scope_project_id = str(uuid4())
    elif principal == "system":
        case.grant.scope_type = "system"
    elif principal == "revoked":
        case.grant.status = "revoked"
    else:
        case.role = principal
    with pytest.raises(AuthorizationDenied):
        async with case.prepare():
            pytest.fail("uncovered manager prepared")
    assert case.events == []


@pytest.mark.parametrize(
    "field",
    [
        "project_id",
        "guide_id",
        "compilation_id",
        "actor_profile_id",
        "identity_link_id",
        "operation_id",
        "request_id",
    ],
)
async def test_prepared_selector_substitution_rejects(monkeypatch, field):
    case = Case(monkeypatch)
    async with case.prepare() as handle:
        changed = replace(case.facts, locator=replace(case.facts.locator, **{field: uuid4()}))
        with pytest.raises(PreparedAuthorizationInvalid):
            await handle.consume_new(changed)
    assert case.events == []


@pytest.mark.parametrize(
    "failure", ["reused", "closed", "new_transaction", "nested", "wrong_session"]
)
async def test_handle_lifetime_is_exact(monkeypatch, failure):
    case = Case(monkeypatch)
    async with case.prepare() as handle:
        if failure == "closed":
            handle._service.close()
        elif failure == "reused":
            await handle.consume_new(case.facts)
        elif failure == "new_transaction":
            case.session.root = SimpleNamespace(is_active=True)
        elif failure == "nested":
            monkeypatch.setattr(case.session, "in_nested_transaction", lambda: True)
        else:
            handle._service._session = type(case.session)()
        with pytest.raises(PreparedAuthorizationInvalid):
            await handle.consume_new(case.facts)
    assert len(case.events) == (1 if failure == "reused" else 0)


@pytest.mark.parametrize("action", [DERIVE, APPROVE, CORRECT])
async def test_replay_rechecks_current_authority_without_new_evidence(monkeypatch, action):
    case = Case(monkeypatch, action)
    async with case.prepare() as handle:
        receipt = await handle.consume_new(case.facts)
    facts = replace(case.facts, locator=replace(case.facts.locator, request_id=uuid4()))
    case.context = case.context.model_copy(update={"request_id": facts.locator.request_id})
    async with case.prepare(facts=facts) as handle:
        await handle.validate_replay(facts, receipt.authorization_decision_event_id)
    assert len(case.events) == 1
    case.link_status = "revoked"
    with pytest.raises(AuthorizationDenied):
        async with case.prepare(facts=facts):
            pytest.fail("revoked caller prepared replay")
    assert len(case.events) == 1


@pytest.mark.parametrize("action", [DERIVE, APPROVE, CORRECT])
@pytest.mark.parametrize(
    "field",
    [
        "id",
        "action_id",
        "actor_id",
        "permission_id",
        "resource_id",
        "project_id",
        "correlation_id",
        "after_facts",
        "matched_grant_id",
        "request_id",
    ],
)
async def test_replay_evidence_substitution_rejects(monkeypatch, action, field):
    case = Case(monkeypatch, action)
    async with case.prepare() as handle:
        receipt = await handle.consume_new(case.facts)
    setattr(case.events[0], field, "invalid")
    async with case.prepare() as handle:
        with pytest.raises(PreparedAuthorizationInvalid):
            await handle.validate_replay(case.facts, receipt.authorization_decision_event_id)
    assert len(case.events) == 1


async def test_proposal_handle_rejects_post_policy_read(monkeypatch):
    from tests.authorization.guide_proposals.support import Case as ProposalCase
    from .support import post_facts

    case = ProposalCase(monkeypatch, READ)
    facts = post_facts(READ)
    facts = replace(
        facts,
        locator=type(facts.locator)(
            **{
                name: getattr(case.facts.locator, name)
                for name in facts.locator.__dataclass_fields__
            }
        ),
    )
    async with case.prepare() as handle:
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await handle._service.consume(
                handle._handle, ActionId(READ), handle._input, post_policy_resource(facts)
            )
    assert case.events == []


async def test_post_policy_handle_rejects_proposal_read(monkeypatch):
    from app.modules.authorization.domain.guide_proposals import proposal_resource
    from tests.projects.guide_compilation.proposals.contract_support import authority_case

    case = Case(monkeypatch, READ)
    _, _, facts, _ = authority_case()
    facts = replace(
        facts,
        locator=type(facts.locator)(
            **{
                name: getattr(case.facts.locator, name)
                for name in facts.locator.__dataclass_fields__
            }
        ),
    )
    async with case.prepare() as handle:
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await handle._service.consume(
                handle._handle, ActionId(READ), handle._input, proposal_resource(facts)
            )
    assert case.events == []


@pytest.mark.parametrize("action", [DERIVE, APPROVE, CORRECT, READ])
async def test_raw_kernel_cannot_authorize_post_policy(monkeypatch, action):
    from app.modules.authorization.runtime import AuthorizationDenied as KernelDenied

    case = Case(monkeypatch, action)
    async with case.prepare() as handle:
        with pytest.raises(KernelDenied):
            await handle._service._authorization.require(
                ActionId(action), post_policy_resource(case.facts)
            )
    assert all(
        e.after_facts != dict(allowed=True, resource_context_digest=case.facts.digest)
        for e in case.events
    )


@pytest.mark.parametrize(
    "action,method", [(READ, "consume_new"), (READ, "validate_replay"), (APPROVE, "authorize_read")]
)
async def test_nominal_method_cannot_change_operation_kind(monkeypatch, action, method):
    case = Case(monkeypatch, action)
    async with case.prepare() as handle:
        args = (case.facts, uuid4()) if method == "validate_replay" else (case.facts,)
        with pytest.raises(PreparedAuthorizationInvalid):
            await getattr(handle, method)(*args)
    assert case.events == []


@pytest.mark.parametrize("field", ["actor_profile_id", "identity_link_id", "request_id"])
async def test_authenticated_context_cannot_be_replaced_by_locator(monkeypatch, field):
    case = Case(monkeypatch)
    context = case.context.model_copy(update={field: uuid4()})
    with pytest.raises(AuthorizationDenied):
        async with case.prepare(context=context):
            pytest.fail("foreign authenticated context accepted")
    assert case.events == []


@pytest.mark.parametrize(
    "field,value", [("action_id", "project.guide.activate"), ("project_id", "not-uuid")]
)
async def test_invalid_locator_denies_before_preparation(monkeypatch, field, value):
    case = Case(monkeypatch)
    facts = replace(case.facts, locator=replace(case.facts.locator, **{field: value}))
    with pytest.raises(PreparedAuthorizationInvalid):
        async with case.prepare(facts=facts):
            pytest.fail("invalid locator accepted")
    assert case.events == []


async def test_evidence_failure_is_unavailable_not_an_allow(monkeypatch):
    from app.modules.authorization.api import AuthorizationUnavailable
    from app.modules.authorization.runtime import AuthorizationEvidenceUnavailable

    case = Case(monkeypatch)

    async def fail(*args):
        raise AuthorizationEvidenceUnavailable("private backend detail")

    monkeypatch.setattr(case, "add_authority_event", fail)
    async with case.prepare() as handle:
        with pytest.raises(
            AuthorizationUnavailable, match="post-policy authority unavailable"
        ) as failure:
            await handle.consume_new(case.facts)
    assert "private backend detail" not in str(failure.value)
    assert case.events == []


@pytest.mark.parametrize("family", [None, "guide_proposal", "post_policy_extra"])
async def test_prepare_rejects_missing_or_unknown_operation_family(monkeypatch, family):
    from app.modules.authorization.runtime import PreparedAuthorizationInput
    from app.modules.authorization.domain.post_policy import post_policy_selectors

    case = Case(monkeypatch, APPROVE)
    async with case.prepare() as handle:
        value = post_policy_selectors(case.facts.locator)
        if family is None:
            del value["operation_family"]
        else:
            value["operation_family"] = family
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await handle._service.consume(
                handle._handle,
                ActionId(APPROVE),
                PreparedAuthorizationInput(
                    idempotency_key=case.facts.locator.operation_id, request_value=value
                ),
                post_policy_resource(case.facts),
            )
    assert case.events == []


async def test_handle_rejects_a_different_issuer(monkeypatch):
    case = Case(monkeypatch)
    async with case.prepare() as first, case.prepare() as second:
        first._handle = second._handle
        with pytest.raises(PreparedAuthorizationInvalid):
            await first.consume_new(case.facts)
    assert case.events == []
