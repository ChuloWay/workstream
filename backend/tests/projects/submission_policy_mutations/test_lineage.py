"""Exact PROJECT owner selectors and valid-context controls, not physical locks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.core.hashing import canonical_json_hash
from app.modules.projects import submission_policy_mutation_service as module
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.submission_policy_mutations import rows
from projects.submission_policy_mutations.fixtures import case as case


@pytest.fixture
def lineage_case(case):
    project = SimpleNamespace(id=str(rows.PROJECT))
    guide = SimpleNamespace(
        id=str(rows.GUIDE), project_id=str(rows.PROJECT), version="v1", status="draft"
    )
    snapshot = SimpleNamespace(id=str(rows.SNAPSHOT), bundle_hash=rows.SNAPSHOT_HASH)
    setup = SimpleNamespace(
        id=str(rows.SETUP),
        guide_version="v1",
        source_snapshot_id=str(rows.SNAPSHOT),
        source_snapshot_hash=rows.SNAPSHOT_HASH,
        setup_generation=4,
    )
    report = rows.unacknowledged_report()
    ports = {
        "get_project": project,
        "get_guide": guide,
        "lock_project_guide": guide,
        "get_latest_guide_source_snapshot": snapshot,
        "lock_latest_guide_source_snapshot": snapshot,
        "get_latest_project_setup_run": setup,
        "lock_latest_project_setup_run": setup,
        "get_sufficiency_report_for_snapshot": report,
        "lock_guide_sufficiency_report": report,
        "get_submission_artifact_policy": case.predecessor,
        "lock_submission_artifact_policy": case.predecessor,
    }
    case.projects = SimpleNamespace(
        **{key: AsyncMock(return_value=value) for key, value in ports.items()}
    )
    case.service._projects = case.projects
    case.owner_calls = MagicMock()
    for name, port in vars(case.projects).items():
        case.owner_calls.attach_mock(port, name)
    case.service._validation = SimpleNamespace(
        validate_source_snapshot_integrity=AsyncMock(),
        verified_source_material_refs=AsyncMock(return_value=["guide-source:item"]),
    )
    case.service._lineage = module.SubmissionPolicyMutationService._lineage.__get__(case.service)
    case.project, case.guide, case.snapshot, case.setup, case.report = (
        project,
        guide,
        snapshot,
        setup,
        report,
    )
    return case


async def load(case, lock=False):
    return await case.service._lineage(
        rows.PROJECT, rows.GUIDE, rows.SNAPSHOT, lock=lock, predecessor_id=rows.POLICY
    )


@pytest.mark.parametrize("lock", [False, True])
async def test_lineage_loads_exact_owner_context(lineage_case, lock):
    case = lineage_case
    result = await load(case, lock)
    assert result == module._ManualPolicyLineage(
        guide_version="v1",
        snapshot_id=rows.SNAPSHOT,
        snapshot_hash=rows.SNAPSHOT_HASH,
        setup_run_id=rows.SETUP,
        setup_generation=4,
        report_id=rows.REPORT,
        report_status="passed",
        acknowledgement_digest=None,
        source_material_refs=("guide-source:item",),
        predecessor_id=rows.POLICY,
        predecessor_version="manual-v1",
        predecessor_status="draft",
        predecessor_hash=case.predecessor.policy_hash,
    )
    case.projects.get_project.assert_awaited_once_with(str(rows.PROJECT), for_update=lock)
    guide = case.projects.lock_project_guide if lock else case.projects.get_guide
    guide.assert_awaited_once_with(str(rows.GUIDE))
    snapshot = (
        case.projects.lock_latest_guide_source_snapshot
        if lock
        else case.projects.get_latest_guide_source_snapshot
    )
    snapshot.assert_awaited_once_with(str(rows.PROJECT), str(rows.GUIDE), "v1")
    if lock:
        case.projects.lock_latest_project_setup_run.assert_awaited_once_with(
            str(rows.PROJECT), str(rows.GUIDE), "v1"
        )
        case.projects.lock_guide_sufficiency_report.assert_awaited_once_with(
            str(rows.REPORT), str(rows.PROJECT), str(rows.GUIDE), "v1"
        )
        case.projects.lock_submission_artifact_policy.assert_awaited_once_with(str(rows.POLICY))
    else:
        case.projects.get_latest_project_setup_run.assert_awaited_once_with(
            str(rows.PROJECT), str(rows.GUIDE)
        )
        case.projects.lock_guide_sufficiency_report.assert_not_awaited()
        case.projects.get_submission_artifact_policy.assert_awaited_once_with(str(rows.POLICY))
    case.service._validation.validate_source_snapshot_integrity.assert_awaited_once_with(
        case.snapshot, module.PolicySetupBlocked
    )
    case.service._validation.verified_source_material_refs.assert_awaited_once_with(case.report)
    if lock:
        assert [entry[0] for entry in case.owner_calls.mock_calls] == [
            "get_project",
            "lock_project_guide",
            "lock_latest_guide_source_snapshot",
            "lock_latest_project_setup_run",
            "get_sufficiency_report_for_snapshot",
            "lock_guide_sufficiency_report",
            "lock_submission_artifact_policy",
        ]


@pytest.mark.parametrize(
    "port,error",
    [
        ("get_project", "project not found"),
        ("get_guide", "guide not found"),
        ("get_latest_project_setup_run", "sufficiency report is required"),
        ("get_sufficiency_report_for_snapshot", "sufficiency report is required"),
    ],
)
async def test_missing_lineage_denies(lineage_case, port, error):
    getattr(lineage_case.projects, port).return_value = None
    with pytest.raises(module.ProjectServiceError, match=error):
        await load(lineage_case)


@pytest.mark.parametrize(
    "owner,field,value,error",
    [
        ("guide", "project_id", str(UUID(int=99)), "guide not found"),
        ("guide", "status", "active", "only draft guides"),
        ("snapshot", "id", str(UUID(int=99)), "lineage_stale"),
        ("setup", "source_snapshot_hash", "sha256:" + "c" * 64, "lineage_stale"),
        ("report", "setup_generation", 5, "does not allow policy"),
        ("predecessor", "lifecycle_status", "approved", "immutable"),
    ],
)
async def test_incompatible_lineage_denies(lineage_case, owner, field, value, error):
    setattr(getattr(lineage_case, owner), field, value)
    with pytest.raises(module.ProjectServiceError, match=error):
        await load(lineage_case)


@pytest.mark.parametrize("scope", ["project", "system"])
def test_warning_acknowledgement_digest_binds_exact_provenance(scope):
    report = rows.warning_report()
    report.warning_acknowledgement_scope_type = scope
    expected = canonical_json_hash(
        {
            "domain": "workstream.guide_sufficiency.warning_acknowledgement.v1",
            "report_id": str(rows.REPORT),
            "actor_profile_id": str(rows.ACTOR),
            "identity_link_id": str(rows.LINK),
            "grant_id": str(rows.GRANT),
            "scope_type": scope,
            "scope_project_id": str(rows.PROJECT),
            "action_id": "project.guide_sufficiency.warnings.acknowledge",
            "decision_event_id": str(UUID(int=20)),
            "acknowledged_at": rows.NOW.isoformat(),
        }
    )
    assert (
        module.SubmissionPolicyMutationService._acknowledgement_digest(report, rows.PROJECT)
        == expected
    )


def test_unacknowledged_warning_blocks_policy_mutation():
    report = rows.unacknowledged_report("passed_with_warnings")
    with pytest.raises(module.PolicySetupBlocked, match="authorized Project Manager"):
        module.SubmissionPolicyMutationService._acknowledgement_digest(report, rows.PROJECT)


def test_warning_acknowledgement_rejects_foreign_project():
    report = rows.warning_report()
    report.warning_acknowledgement_scope_project_id = str(UUID(int=99))
    with pytest.raises(module.PolicySetupBlocked, match="authorized Project Manager"):
        module.SubmissionPolicyMutationService._acknowledgement_digest(report, rows.PROJECT)
