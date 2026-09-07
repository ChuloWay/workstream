"""Fail-closed guards for exact projection replay authorization."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.authorization import prepared_projection_replay as replay_module
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.guide_compilation_projections import (
    projection_resource_context,
)
from app.modules.authorization.runtime import (
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
)

from .replay_support import ReplayCase


@pytest.mark.parametrize("mismatch", ("action", "binding", "transaction", "scope"))
async def test_projection_replay_rejects_listed_prepared_custody_mismatch(monkeypatch, mismatch):
    case = ReplayCase(monkeypatch)
    async with case.prepare() as original:
        receipt = await original.consume_new(case.facts)
    async with case.prepare() as replay:
        service = case.services[1]
        action = ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN
        caller_input = replay._input
        resource = projection_resource_context("guide_sufficiency", replay.identity, case.facts)
        if mismatch == "action":
            action = ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE
        elif mismatch == "binding":
            caller_input = PreparedAuthorizationInput(
                idempotency_key=uuid4(),
                request_value=caller_input.request_value,
            )
        elif mismatch == "transaction":
            case.session.root = SimpleNamespace(is_active=True)
        else:
            resource = resource.model_copy(update={"scope_project_id": uuid4()})

        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await service.validate_replay(
                replay._handle,
                action,
                caller_input,
                resource,
                receipt.decision_event_id,
            )
        assert service._authorization._sealed_prelocked == set()
    assert len(case.evidence.events) == 1


async def test_projection_replay_rejects_project_setup_resource_guard(monkeypatch):
    case = ReplayCase(monkeypatch)
    monkeypatch.setattr(replay_module, "project_setup_resource_matches", lambda *_a: False)
    async with case.prepare() as original:
        receipt = await original.consume_new(case.facts)
    async with case.prepare() as replay:
        service = case.services[1]
        resource = projection_resource_context("guide_sufficiency", replay.identity, case.facts)
        with pytest.raises(PreparedAuthorizationUnsupported):
            await service.validate_replay(
                replay._handle,
                ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN,
                replay._input,
                resource,
                receipt.decision_event_id,
            )
        assert service._authorization._sealed_prelocked == set()
    assert len(case.evidence.events) == 1
