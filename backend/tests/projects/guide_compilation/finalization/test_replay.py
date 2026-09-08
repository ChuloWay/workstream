"""Strict replay effects and exact stored receipt/post-state comparison."""

from datetime import timedelta
from uuid import uuid4

import pytest

from app.modules.authorization.api import AuthorizationDenied
from app.modules.projects.api import ProjectGuideSetupFinalizationError
from .support import scenario


async def test_replay_uses_stored_prefinalization_digest_and_validates_final_state():
    case = scenario()
    original = await case.service.finalize(case.command)
    result = await case.service.finalize(case.command)
    assert result == original
    assert case.auth.events == ["prepare", "consume", "close", "prepare", "replay", "close"]
    assert case.repo.calls.count("persist") == 1


@pytest.mark.parametrize("drift", [None, timedelta(microseconds=1)])
async def test_replay_requires_exact_database_finalization_timestamp(drift):
    case = scenario()
    await case.service.finalize(case.command)
    case.view.setup.finished_at = None if drift is None else case.view.setup.finished_at + drift
    with pytest.raises(ProjectGuideSetupFinalizationError, match="source_state_unavailable"):
        await case.service.finalize(case.command)
    assert case.repo.calls.count("persist") == 1
    assert case.auth.events.count("consume") == 1
    assert case.auth.events[-2:] == ["prepare", "close"]


async def test_replay_preflight_closes_once_after_validation():
    case = scenario()
    await case.service.finalize(case.command)
    case.auth.events.clear()
    await case.service.finalize(case.command)
    assert case.auth.events == ["prepare", "replay", "close"]


async def test_replay_denial_closes_once_without_effect():
    case = scenario()
    await case.service.finalize(case.command)
    case.auth.events.clear()
    case.auth.replay_error = AuthorizationDenied("revoked")
    with pytest.raises(ProjectGuideSetupFinalizationError, match="service_authority_denied"):
        await case.service.finalize(case.command)
    assert case.auth.events == ["prepare", "replay", "close"]
    assert case.repo.calls.count("persist") == 1


@pytest.mark.parametrize(
    "field",
    [
        "result_hash",
        "source_state_digest",
        "sufficiency_report_id",
        "authority_resource_digest",
        "facts_digest",
        "scope_project_id",
        "action_id",
        "permission_id",
        "service_identity",
        "scope_type",
        "identity_link_id",
        "actor_profile_id",
        "component_hashes",
    ],
)
async def test_same_operation_changed_stored_facts_denies(field):
    case = scenario()
    await case.service.finalize(case.command)
    row = case.repo.rows[0]
    value = "sha256:" + "f" * 64 if field.endswith(("hash", "digest")) else str(uuid4())
    if field == "component_hashes":
        value = {}
    setattr(row, field, value)
    with pytest.raises(ProjectGuideSetupFinalizationError, match="source_state_unavailable"):
        await case.service.finalize(case.command)
    assert case.auth.events.count("consume") == 1
    assert case.repo.calls.count("persist") == 1


async def test_postlock_receipt_discovery_switches_same_capability_to_replay():
    case = scenario()
    original = await case.service.finalize(case.command)
    stored = case.repo.rows
    case.repo.rows = ()
    case.repo.after_lock = lambda: setattr(case.repo, "rows", stored)
    case.auth.events.clear()
    result = await case.service.finalize(case.command)
    assert result == original
    assert case.auth.events == ["prepare", "replay", "close"]
    assert case.repo.calls.count("persist") == 1


@pytest.mark.parametrize(
    "field",
    [
        "status",
        "current_step",
        "output_sufficiency_report_id",
        "output_submission_artifact_policy_id",
    ],
)
async def test_replay_rejects_malformed_closed_setup(field):
    case = scenario()
    await case.service.finalize(case.command)
    setattr(case.view.setup, field, "mismatch")
    with pytest.raises(ProjectGuideSetupFinalizationError):
        await case.service.finalize(case.command)
    assert case.repo.calls.count("persist") == 1


async def test_other_operation_cannot_own_the_selected_generation():
    case = scenario()
    await case.service.finalize(case.command)
    case.repo.rows[0].operation_id = uuid4()
    with pytest.raises(ProjectGuideSetupFinalizationError):
        await case.service.finalize(case.command)
    assert case.auth.events.count("consume") == 1
