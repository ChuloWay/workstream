"""Decision-shape and exact PREP composition proof, not AUTH evaluator proof."""

from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.core.hashing import canonical_json_hash
from app.modules.authorization.runtime import AuthorizationDenialCode
from app.modules.projects import sufficiency_mutation_service as module
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.sufficiency_mutations import rows
from projects.sufficiency_mutations.commands import invoke
from projects.sufficiency_mutations.fixtures import case as case


@pytest.mark.parametrize(
    "field,value",
    [
        ("matched_authority_kind", module.MatchedAuthorityKind.FIXED_SERVICE),
        ("matched_grant_id", None),
        ("matched_scope_project_id", UUID(int=99)),
    ],
)
async def test_human_authority_requires_matching_grant(case, field, value):
    setattr(case.decision, field, value)
    with pytest.raises(RuntimeError, match="lacked Project Manager authority"):
        case.service._prove_human(case.decision, rows.PROJECT)


@pytest.mark.parametrize("scope", [None, rows.PROJECT])
async def test_human_authority_accepts_covered_scope(case, scope):
    case.decision.matched_scope_project_id = scope
    assert case.service._prove_human(case.decision, rows.PROJECT) is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("matched_authority_kind", module.MatchedAuthorityKind.ADMIN_ROLE_GRANT),
        ("matched_grant_id", rows.GRANT),
    ],
)
async def test_setup_authority_requires_fixed_service(case, field, value):
    case.decision.matched_authority_kind = module.MatchedAuthorityKind.FIXED_SERVICE
    case.decision.matched_grant_id = None
    setattr(case.decision, field, value)
    with pytest.raises(RuntimeError, match="lacked fixed setup-service authority"):
        case.service._prove_authority(case.decision, rows.PROJECT, "setup_service")


async def test_setup_authority_accepts_fixed_decision(case):
    case.decision.matched_authority_kind = module.MatchedAuthorityKind.FIXED_SERVICE
    case.decision.matched_grant_id = None
    assert case.service._prove_authority(case.decision, rows.PROJECT, "setup_service") is None


async def test_prepare_forwards_exact_unsupported_denial(case):
    caller, resource = object(), object()
    action = module.ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN
    failure = module.PreparedAuthorizationUnsupported(
        AuthorizationDenialCode.PERMISSION_NOT_GRANTED
    )
    case.prepared.prepare.side_effect = failure
    assert (
        await case.service._prepare(case.prepared, action, caller, rows.PROJECT, resource) is None
    )
    case.prepared.deny_unsupported.assert_awaited_once_with(action, caller, resource, failure)


async def test_prepare_returns_handle(case):
    caller, resource = object(), object()
    action = module.ActionId.PROJECT_GUIDE_SUFFICIENCY_RUN
    assert (
        await case.service._prepare(case.prepared, action, caller, rows.PROJECT, resource)
        is case.handle
    )
    case.prepared.prepare.assert_awaited_once_with(
        action,
        caller,
        module.PreparedAuthorityScope(
            kind=module.PreparedAuthorityScopeKind.PROJECT, project_id=rows.PROJECT
        ),
    )
    case.prepared.deny_unsupported.assert_not_awaited()


def custody():
    return module.ProjectSetupServiceCustodyContext(
        setup_run_id=rows.SETUP,
        scope_project_id=rows.PROJECT,
        guide_id=rows.GUIDE,
        source_snapshot_id=rows.SNAPSHOT,
        setup_generation=1,
        expected_step="guide_sufficiency",
        task_id=UUID(int=20),
        correlation_id=UUID(int=21),
        stale_output_digest=rows.STALE_HASH,
    )


async def run_agent(case):
    return await case.service._run_agent(
        actor_profile_id=str(rows.ACTOR),
        identity_link_id=str(rows.LINK),
        prepared=case.prepared,
        key=rows.KEY,
        project_id=rows.PROJECT,
        guide_id=rows.GUIDE,
        source_snapshot_id=rows.SNAPSHOT,
        execution_kind="setup_service",
        setup_service_custody=custody(),
    )


async def test_agent_requires_material(case):
    with pytest.raises(
        module.PolicySetupBlocked, match="verified guide sufficiency is unavailable"
    ):
        await run_agent(case)
    case.service._lineage.assert_not_awaited()
    case.prepared.prepare.assert_not_awaited()
    case.prepared.consume.assert_not_awaited()


async def test_agent_requires_setup_lineage(case):
    case.service._material = AsyncMock()
    case.service._lineage.return_value = replace(case.lineage, setup_run_id=None)
    with pytest.raises(RuntimeError, match="required setup run was not resolved"):
        await run_agent(case)
    assert case.service._material.mock_calls == []
    case.prepared.prepare.assert_not_awaited()
    case.prepared.consume.assert_not_awaited()


def test_legacy_run_agent_entry_is_absent():
    assert not hasattr(module.GuideSufficiencyMutationService, "run_agent")


@pytest.mark.parametrize(
    "command,action,target,suffix,body",
    [
        (
            "create",
            "project.guide_sufficiency_report.create",
            "report",
            "sufficiency-reports",
            {
                "source_snapshot_id": str(rows.SNAPSHOT),
                "status": "passed",
                "findings": [],
                "summary": "Assessment",
            },
        ),
        (
            "ack",
            "project.guide_sufficiency.warnings.acknowledge",
            "warning_acknowledgement",
            "sufficiency-reports/{report_id}/acknowledge-warnings",
            {"acknowledgement_note": "Understood"},
        ),
        (
            "dispatch",
            "project.guide_sufficiency.run",
            "run",
            "source-snapshots/{source_snapshot_id}/run-sufficiency-agent",
            {"source_snapshot_id": str(rows.SNAPSHOT)},
        ),
    ],
)
async def test_mutation_passes_exact_prepared_context(case, command, action, target, suffix, body):
    await invoke(case, command)
    reserve = case.replay.reserve.await_args.kwargs
    selected_action, caller, scope = case.prepared.prepare.await_args.args
    handle, consumed_action, consumed_caller, resource = case.prepared.consume.await_args.args
    report_id = case.replay.complete.await_args.kwargs["report_id"]
    replay_value = {
        "action_id": action,
        "route": "POST /api/v1/projects/{project_id}/guides/{guide_id}/" + suffix,
        "actor_profile_id": str(rows.ACTOR),
        "identity_link_id": str(rows.LINK),
        "idempotency_key": str(rows.KEY),
        "project_id": str(rows.PROJECT),
        "guide_id": str(rows.GUIDE),
        "report_id": str(rows.REPORT) if command == "ack" else None,
        "source_snapshot_id": str(rows.SNAPSHOT),
        "body": body,
        "execution_kind": "human",
        "setup_service_custody": None,
    }
    digest = canonical_json_hash(
        {"domain": "workstream.guide_sufficiency.idempotency.v1", **replay_value}
    )
    stale = (
        rows.STALE_HASH
        if command != "dispatch"
        else canonical_json_hash(
            {
                "domain": "workstream.project_setup.manual_dispatch.v1",
                "project_id": str(rows.PROJECT),
                "guide_id": str(rows.GUIDE),
                "source_snapshot_id": str(rows.SNAPSHOT),
                "setup_run_id": str(rows.SETUP),
                "setup_generation": 1,
            }
        )
    )
    assert selected_action.value == consumed_action.value == action
    assert handle is case.handle and consumed_caller is caller
    assert scope == module.PreparedAuthorityScope(
        kind=module.PreparedAuthorityScopeKind.PROJECT, project_id=rows.PROJECT
    )
    assert caller.idempotency_key == rows.KEY
    assert caller.request_value == {
        **replay_value,
        "report_id": report_id,
        "guide_version": "v1",
        "source_snapshot_hash": rows.SNAPSHOT_HASH,
        "operation_id": str(reserve["operation_id"]),
        "request_digest": digest,
        "target_kind": target,
        "setup_generation": 1,
        "stale_output_digest": stale,
        "material_digest": None,
    }
    assert resource.model_dump(mode="json") == {
        "resource_type": "project_guide_sufficiency_mutation",
        "resource_id": report_id or str(rows.SNAPSHOT),
        "operation_id": str(reserve["operation_id"]),
        "request_digest": digest,
        "scope_project_id": str(rows.PROJECT),
        "guide_id": str(rows.GUIDE),
        "guide_version": "v1",
        "source_snapshot_id": str(rows.SNAPSHOT),
        "source_snapshot_hash": rows.SNAPSHOT_HASH,
        "target_kind": target,
        "execution_kind": "human",
        "sufficiency_report_id": report_id,
        "setup_generation": 1,
        "stale_output_digest": stale,
        "material_digest": None,
        "setup_service_custody": None,
    }
