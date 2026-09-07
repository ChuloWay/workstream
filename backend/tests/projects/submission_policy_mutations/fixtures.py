"""Standard mock ports for service composition, never database guarantees."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.modules.projects import submission_policy_mutation_service as module
from projects.submission_policy_fixtures import project_submission_artifact_policy_body
from projects.submission_policy_mutations import rows


@pytest.fixture
def case():
    session = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.in_nested_transaction.return_value = False
    session.sync_session.get_transaction.return_value = SimpleNamespace(is_active=True)
    service = module.SubmissionPolicyMutationService(session)
    prior = rows.predecessor()

    async def stamp_created(policy):
        policy.created_at = policy.updated_at = rows.NOW

    projects = SimpleNamespace(
        add_submission_artifact_policy=AsyncMock(side_effect=stamp_created),
        get_submission_artifact_policy=AsyncMock(return_value=prior),
        supersede_draft_submission_artifact_policy=AsyncMock(return_value=True),
    )
    replay = SimpleNamespace(
        find_by_operation=AsyncMock(return_value=None),
        reserve=AsyncMock(return_value=("claimed", SimpleNamespace(id=rows.OPERATION))),
        complete=AsyncMock(),
    )
    handle = object()
    decision = SimpleNamespace(
        matched_authority_kind=module.MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        matched_grant_id=rows.GRANT,
        matched_scope_project_id=rows.PROJECT,
        decision_id=UUID(int=20),
    )
    prepared = SimpleNamespace(
        prepare=AsyncMock(return_value=handle),
        consume=AsyncMock(return_value=decision),
        deny_unsupported=AsyncMock(side_effect=RuntimeError("unexpected denial")),
    )
    service._projects, service._replay = projects, replay
    service._admin = SimpleNamespace(find_effective_grant=AsyncMock(return_value=object()))
    service._lineage = AsyncMock(return_value=rows.lineage())
    return SimpleNamespace(
        service=service,
        session=session,
        projects=projects,
        replay=replay,
        prepared=prepared,
        handle=handle,
        decision=decision,
        predecessor=prior,
        resolved=SimpleNamespace(
            profile=SimpleNamespace(id=str(rows.ACTOR)),
            identity_link=SimpleNamespace(id=str(rows.LINK)),
        ),
    )


def select_update(case):
    prior = case.predecessor
    case.service._lineage.return_value = replace(
        rows.lineage(),
        predecessor_id=rows.POLICY,
        predecessor_version=prior.policy_version,
        predecessor_status="draft",
        predecessor_hash=prior.policy_hash,
    )


async def invoke(case, command="create", **changes):
    if command == "create":
        payload = module.SubmissionArtifactPolicyCreate.model_validate(
            {
                "source_snapshot_id": rows.SNAPSHOT,
                "policy_version": "manual-v1",
                "policy_body": project_submission_artifact_policy_body(),
                "change_summary": "initial",
                **changes,
            }
        )
        return await case.service.create_manual(
            case.resolved,
            case.prepared,
            rows.KEY,
            rows.PROJECT,
            rows.GUIDE,
            payload,
        )
    payload = module.SubmissionArtifactPolicyUpdate.model_validate(
        {
            "expected_policy_hash": case.predecessor.policy_hash,
            "successor_policy_version": "manual-v2",
            "change_summary": "replacement",
            **changes,
        }
    )
    return await case.service.update_manual(
        case.resolved,
        case.prepared,
        rows.KEY,
        rows.PROJECT,
        rows.GUIDE,
        rows.POLICY,
        payload,
    )


async def capture_replay(case, command):
    """Use a completed real command as setup, then expose only its passive result."""
    if command == "update":
        select_update(case)
    outcome = await invoke(case, command)
    reserved = case.replay.reserve.await_args.kwargs
    response = case.replay.complete.await_args.kwargs
    record = SimpleNamespace(
        **{key: value for key, value in reserved.items() if key != "status"},
        status="committed",
        response_json=response["response_json"],
        committed_policy_id=response["committed_policy_id"],
        committed_at=rows.NOW,
    )
    committed = case.projects.add_submission_artifact_policy.await_args.args[0]
    case.projects.get_submission_artifact_policy.return_value = committed
    case.replay.find_by_operation.return_value = record
    for port in (case.projects, case.replay, case.prepared):
        for value in vars(port).values():
            if isinstance(value, AsyncMock):
                value.reset_mock()
    return outcome, record
