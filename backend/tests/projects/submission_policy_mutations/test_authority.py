"""Authority-shape, replay-custody and transaction-owner delegation guards."""

from dataclasses import replace
from uuid import UUID

import pytest

from app.modules.authorization.runtime import AuthorizationDenialCode
from app.modules.projects import submission_policy_mutation_service as module
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.submission_policy_mutations import rows
from projects.submission_policy_mutations.fixtures import case as case


@pytest.mark.parametrize(
    "field,value",
    [
        ("matched_authority_kind", module.MatchedAuthorityKind.FIXED_SERVICE),
        ("matched_grant_id", None),
        ("matched_scope_project_id", UUID(int=99)),
    ],
)
def test_human_authority_requires_covered_grant(case, field, value):
    setattr(case.decision, field, value)
    with pytest.raises(RuntimeError, match="lacked covered"):
        case.service._prove_human_authority(case.decision, rows.PROJECT)


async def test_unsupported_prepare_forwards_exact_denial(case):
    action = module.ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE
    caller, resource = object(), object()
    unsupported = module.PreparedAuthorizationUnsupported(
        AuthorizationDenialCode.ACTION_UNAVAILABLE
    )
    denial = RuntimeError("denied")
    case.prepared.prepare.side_effect = unsupported
    case.prepared.deny_unsupported.side_effect = denial
    with pytest.raises(RuntimeError) as observed:
        await case.service._prepare(case.prepared, action, caller, rows.PROJECT, resource)
    assert observed.value is denial
    case.prepared.deny_unsupported.assert_awaited_once_with(action, caller, resource, unsupported)


@pytest.mark.parametrize("operation", ["reserve", "complete"])
async def test_replay_delegates_exact_custody_without_transaction_ownership(case, operation):
    facts = rows.replay_facts()
    expected = {
        field: getattr(facts, field)
        for field in facts.__dataclass_fields__
        if field != "resource_context"
    }
    expected["resource_context_digest"] = module.authorization_resource_digest(
        facts.resource_context
    )
    expected["resource_context_json"] = facts.resource_context.model_dump(mode="json")
    if operation == "reserve":
        outcome = await case.service.reserve_replay(facts)
        assert outcome == case.replay.reserve.return_value
        case.replay.reserve.assert_awaited_once_with(**expected, status="pending")
    else:
        for field in (
            "operation_id",
            "project_id",
            "guide_id",
            "source_snapshot_id",
            "policy_id",
            "resource_context_json",
        ):
            del expected[field]
        await case.service.complete_replay(
            facts, response_json={"id": str(rows.POLICY)}, committed_policy_id=str(rows.POLICY)
        )
        case.replay.complete.assert_awaited_once_with(
            rows.OPERATION,
            **expected,
            response_json={"id": str(rows.POLICY)},
            committed_policy_id=str(rows.POLICY),
            committed_effective_policy_id=None,
            committed_pre_submit_policy_id=None,
        )
    case.session.commit.assert_not_awaited()
    case.session.rollback.assert_not_awaited()


@pytest.mark.parametrize("state", ["missing", "inactive", "nested"])
async def test_replay_requires_active_root_transaction(case, state):
    if state == "missing":
        case.session.sync_session.get_transaction.return_value = None
    elif state == "inactive":
        case.session.sync_session.get_transaction.return_value.is_active = False
    else:
        case.session.in_nested_transaction.return_value = True
    with pytest.raises(RuntimeError, match="one root transaction"):
        await case.service.reserve_replay(rows.replay_facts())
    case.replay.reserve.assert_not_awaited()


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("action_id", "invalid", "invalid submission-policy replay action"),
        ("request_digest", "sha256:" + "c" * 64, "do not match resource context"),
        ("idempotency_key", None, "human replay custody is invalid"),
    ],
)
async def test_invalid_human_replay_facts_never_reach_repository(case, field, value, error):
    with pytest.raises(ValueError, match=error):
        await case.service.reserve_replay(replace(rows.replay_facts(), **{field: value}))
    case.replay.reserve.assert_not_awaited()


def service_facts():
    facts = rows.replay_facts()
    custody = module.ProjectSetupServiceCustodyContext(
        setup_run_id=rows.SETUP,
        scope_project_id=rows.PROJECT,
        guide_id=rows.GUIDE,
        source_snapshot_id=rows.SNAPSHOT,
        setup_generation=4,
        expected_step="submission_artifact_policy",
        task_id=UUID(int=30),
        correlation_id=UUID(int=31),
        stale_output_digest="sha256:" + "c" * 64,
    )
    resource = facts.resource_context.model_copy(
        update={
            "target_kind": "derive",
            "execution_kind": "setup_service",
            "stale_output_digest": custody.stale_output_digest,
            "setup_service_custody": custody,
        }
    )
    return replace(
        facts,
        service_identity="workstream.project.setup",
        action_id=module.ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_DERIVE.value,
        idempotency_key=None,
        resource_context=resource,
        setup_run_id=str(rows.SETUP),
        setup_task_id=custody.task_id,
        correlation_id=custody.correlation_id,
    )


async def test_fixed_service_replay_preserves_exact_custody(case):
    facts = service_facts()
    await case.service.reserve_replay(facts)
    values = case.replay.reserve.await_args.kwargs
    assert values["service_identity"] == "workstream.project.setup"
    assert values["setup_run_id"] == str(rows.SETUP)
    assert values["setup_task_id"] == UUID(int=30)
    assert values["correlation_id"] == UUID(int=31)
    assert values["idempotency_key"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("setup_run_id", str(UUID(int=99))),
        ("setup_task_id", UUID(int=99)),
        ("correlation_id", UUID(int=99)),
    ],
)
async def test_fixed_service_replay_rejects_changed_custody(case, field, value):
    with pytest.raises(ValueError, match="service replay custody is invalid"):
        await case.service.reserve_replay(replace(service_facts(), **{field: value}))
    case.replay.reserve.assert_not_awaited()
