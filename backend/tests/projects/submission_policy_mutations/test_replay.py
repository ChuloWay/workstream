"""Stored replay classification at real service ports, not database recovery proof."""

import json
from unittest.mock import call
from uuid import UUID

import pytest

from app.modules.projects import submission_policy_mutation_service as module
from projects.submission_policy_mutations import rows
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.submission_policy_mutations.fixtures import (
    case as case,
    capture_replay,
    invoke,
)


@pytest.mark.parametrize("command", ["create", "update"])
async def test_committed_replay_returns_original_without_mutation(case, command):
    original, record = await capture_replay(case, command)
    replayed = await invoke(case, command)
    assert replayed.replayed is True
    assert replayed.response == original.response
    expected_lookups = [call(original.response.id)]
    assert case.projects.get_submission_artifact_policy.await_args_list == expected_lookups
    case.prepared.prepare.assert_awaited_once()
    caller = case.prepared.prepare.await_args.args[1]
    resource = module.ProjectSubmissionArtifactPolicyMutationResourceContext.model_validate_json(
        json.dumps(record.resource_context_json)
    )
    assert caller.request_value == resource.model_dump(mode="json")
    case.prepared.consume.assert_awaited_once_with(
        case.handle,
        module.ActionId(record.action_id),
        caller,
        resource,
    )
    case.replay.reserve.assert_not_awaited()
    case.replay.complete.assert_not_awaited()
    case.projects.add_submission_artifact_policy.assert_not_awaited()
    case.projects.supersede_draft_submission_artifact_policy.assert_not_awaited()


@pytest.mark.parametrize("command", ["create", "update"])
async def test_locked_concurrent_winner_replays_before_live_lineage_moves(case, command):
    original, record = await capture_replay(case, command)
    initial = case.service._lineage.return_value
    case.service._lineage.reset_mock(side_effect=True)
    case.service._lineage.side_effect = [
        initial,
        AssertionError("winner replay must precede another mutable-lineage read"),
    ]
    misses = 2 if command == "update" else 1
    case.replay.find_human_namespace.side_effect = [*([None] * misses), record]

    replayed = await invoke(case, command)

    assert replayed.replayed is True
    assert replayed.response == original.response
    assert case.service._lineage.await_count == 1
    case.projects.get_project.assert_awaited_once_with(str(rows.PROJECT), for_update=True)
    case.prepared.consume.assert_awaited_once()
    case.replay.reserve.assert_not_awaited()
    case.projects.add_submission_artifact_policy.assert_not_awaited()


@pytest.mark.parametrize("command", ["create", "update"])
async def test_replay_requires_current_pm_admission(case, command):
    await capture_replay(case, command)
    case.service._admin.find_effective_grant.reset_mock()
    case.service._admin.find_effective_grant.return_value = None
    with pytest.raises(module.SubmissionArtifactPolicyNotFound, match="not found"):
        await invoke(case, command)
    case.service._admin.find_effective_grant.assert_awaited_once_with(
        rows.ACTOR,
        module.PermissionId.PROJECT_EFFECTIVE_POLICY_MANAGE,
        scope_project_id=rows.PROJECT,
        allowed_roles=frozenset({module.AdminRole.PROJECT_MANAGER}),
    )
    case.replay.find_human_namespace.assert_not_awaited()
    case.projects.get_submission_artifact_policy.assert_not_awaited()
    case.prepared.consume.assert_not_awaited()


@pytest.mark.parametrize("command", ["create", "update"])
@pytest.mark.parametrize(
    "field", ["actor_profile_id", "identity_link_id", "project_id", "guide_id"]
)
async def test_replay_rejects_substituted_identity(case, command, field):
    _, record = await capture_replay(case, command)
    setattr(record, field, str(UUID(int=99)))
    with pytest.raises(module.SubmissionPolicyMutationConflict, match="idempotency_mismatch"):
        await invoke(case, command)
    case.projects.add_submission_artifact_policy.assert_not_awaited()
    case.replay.complete.assert_not_awaited()


@pytest.mark.parametrize("command", ["create", "update"])
async def test_replay_rejects_changed_resource_digest(case, command):
    _, record = await capture_replay(case, command)
    record.resource_context_digest = "sha256:" + "f" * 64
    with pytest.raises(module.SubmissionPolicyMutationConflict, match="idempotency_mismatch"):
        await invoke(case, command)
    case.projects.add_submission_artifact_policy.assert_not_awaited()


@pytest.mark.parametrize("command", ["create", "update"])
async def test_pending_replay_never_returns_success(case, command):
    _, record = await capture_replay(case, command)
    record.status = "pending"
    record.response_json = record.committed_policy_id = record.committed_at = None
    with pytest.raises(module.SubmissionPolicyMutationConflict, match="idempotency_pending"):
        await invoke(case, command)
    case.replay.reserve.assert_not_awaited()
    case.prepared.consume.assert_not_awaited()
    case.projects.add_submission_artifact_policy.assert_not_awaited()
