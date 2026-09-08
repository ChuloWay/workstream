"""Single-use transaction custody and bidirectional resource-kind denial."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.authorization.api import (
    PreparedAuthorizationInvalid,
    ProjectGuideProjectionLocator,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.guide_compilation_projections import (
    projection_prepare_context,
    projection_resource_context,
)
from app.modules.authorization.api import guide_sufficiency_projection_identity
from app.modules.authorization.runtime import (
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    ProjectSetupRunMutationResourceContext,
)
from tests.authorization.guide_compilation_projections.support import sufficiency_facts
from .support import Case, DIGEST


def legacy_resource(project_id):
    setup = uuid4()
    return ProjectSetupRunMutationResourceContext(
        resource_type="project_setup_run_mutation",
        resource_id=setup,
        scope_project_id=project_id,
        guide_id=uuid4(),
        setup_run_id=setup,
        setup_generation=1,
        expected_step="guide_sufficiency",
        task_id=uuid4(),
        correlation_id=uuid4(),
        stale_output_digest=DIGEST,
    )


@pytest.mark.parametrize("first", ["consume", "replay"])
@pytest.mark.parametrize("second", ["consume", "replay"])
async def test_handle_lifetime_is_bound(monkeypatch, first, second):
    case = Case(monkeypatch)
    async with case.prepare() as prepared:
        receipt = await prepared.consume_new(case.facts)
    async with case.prepare() as prepared:
        if first == "consume":
            await prepared.consume_new(case.facts)
        else:
            await prepared.validate_replay(case.facts, receipt.decision_event_id)
        with pytest.raises(PreparedAuthorizationInvalid):
            if second == "consume":
                await prepared.consume_new(case.facts)
            else:
                await prepared.validate_replay(case.facts, receipt.decision_event_id)
    assert len(case.evidence.events) == (2 if first == "consume" else 1)


@pytest.mark.parametrize(
    "mutation", ["close", "nested", "inactive", "commit", "rollback", "root", "session"]
)
@pytest.mark.parametrize("operation", ["consume", "replay"])
async def test_transaction_and_closed_handle_denial(monkeypatch, mutation, operation):
    case = Case(monkeypatch)
    async with case.prepare() as prepared:
        receipt = await prepared.consume_new(case.facts)
    async with case.prepare() as prepared:
        service = case.services[-1]
        if mutation == "close":
            service.close()
        elif mutation == "nested":
            monkeypatch.setattr(case.session, "in_nested_transaction", lambda: True)
        elif mutation == "inactive":
            case.session.root.is_active = False
        elif mutation in {"commit", "rollback"}:
            # This double proves invalid root identity; actual commit/rollback is PG custody.
            case.session.root = None
        elif mutation == "root":
            case.session.root = SimpleNamespace(is_active=True)
        else:
            service._session = type(case.session)()
        with pytest.raises(PreparedAuthorizationInvalid):
            if operation == "consume":
                await prepared.consume_new(case.facts)
            else:
                await prepared.validate_replay(case.facts, receipt.decision_event_id)
    assert len(case.evidence.events) == 1


@pytest.mark.parametrize("kind", ["legacy", "projection"])
async def test_exact_resource_kinds_cannot_be_substituted(monkeypatch, kind):
    case = Case(monkeypatch)
    attempt_id = uuid4()
    identity = guide_sufficiency_projection_identity(
        attempt_id=attempt_id,
        actor_profile_id=case.first.actor_profile_id,
        identity_link_id=case.first.identity_link_id,
    )
    projection = projection_resource_context(
        "guide_sufficiency", identity, sufficiency_facts(case.facts.project_id, attempt_id)
    )
    resource = legacy_resource(case.facts.project_id) if kind == "legacy" else projection
    async with case.prepare() as prepared:
        service = case.services[-1]
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await service.consume(
                prepared._handle, ActionId.PROJECT_SETUP_RUN_UPDATE, prepared._input, resource
            )
        await prepared.consume_new(case.facts)
    assert len(case.evidence.events) == 1


async def test_finalization_cannot_consume_projection_preparation(monkeypatch):
    case = Case(monkeypatch)
    async with case.prepare():
        service = case.services[-1]
        locator = ProjectGuideProjectionLocator(
            project_id=case.facts.project_id, attempt_id=uuid4()
        )
        identity = guide_sufficiency_projection_identity(
            attempt_id=locator.attempt_id,
            actor_profile_id=case.first.actor_profile_id,
            identity_link_id=case.first.identity_link_id,
        )
        context = projection_prepare_context("guide_sufficiency", locator, identity)
        caller = PreparedAuthorizationInput(
            idempotency_key=identity.operation_id, request_value=context.model_dump(mode="json")
        )
        scope = PreparedAuthorityScope(
            kind=PreparedAuthorityScopeKind.PROJECT, project_id=locator.project_id
        )
        handle = await service.prepare(ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN, caller, scope)
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await service.consume(
                handle, ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN, caller, case.resource()
            )
        resource = projection_resource_context(
            "guide_sufficiency", identity, sufficiency_facts(locator.project_id, locator.attempt_id)
        )
        decision = await service.consume(
            handle, ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN, caller, resource
        )
        assert decision.allowed


@pytest.mark.parametrize(
    "request_value", [[], {}, {"binding_kind": "project_guide_setup_finalization"}]
)
async def test_missing_or_malformed_preparation_denies(monkeypatch, request_value):
    case = Case(monkeypatch)
    async with case.prepare():
        service = case.services[-1]
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await service.prepare(
                ActionId.PROJECT_SETUP_RUN_UPDATE,
                PreparedAuthorizationInput(
                    idempotency_key=case.facts.operation_id, request_value=request_value
                ),
                PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT, project_id=case.facts.project_id
                ),
            )


async def test_finalization_prepare_tag_cannot_target_other_action(monkeypatch):
    case = Case(monkeypatch)
    async with case.prepare() as prepared:
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await case.services[-1].prepare(
                ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN,
                prepared._input,
                PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT, project_id=case.facts.project_id
                ),
            )
