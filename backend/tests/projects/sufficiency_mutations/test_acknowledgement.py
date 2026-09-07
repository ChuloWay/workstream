"""Warning acknowledgement provenance and setup continuation guards."""

from uuid import UUID

import pytest

from app.modules.projects import sufficiency_mutation_service as module
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.sufficiency_mutations import rows
from projects.sufficiency_mutations.commands import invoke
from projects.sufficiency_mutations.fixtures import case as case


async def test_acknowledgement_stages_exact_provenance(case):
    outcome = await invoke(case, "ack")
    report = case.report
    assert outcome.replayed is False
    assert (report.warnings_acknowledged_by_role, report.warnings_acknowledged_by_actor) == (
        "project_manager",
        str(rows.ACTOR),
    )
    assert (
        report.warnings_acknowledged_by_actor_profile_id,
        report.warnings_acknowledged_via_identity_link_id,
    ) == (
        str(rows.ACTOR),
        str(rows.LINK),
    )
    assert report.warnings_acknowledged_by_admin_role_grant_id == rows.GRANT
    assert (
        report.warning_acknowledgement_scope_type,
        report.warning_acknowledgement_scope_project_id,
    ) == (
        "project",
        str(rows.PROJECT),
    )
    assert (
        report.warning_acknowledgement_action_id == "project.guide_sufficiency.warnings.acknowledge"
    )
    assert report.warning_acknowledgement_decision_event_id == str(case.decision.decision_id)
    assert report.acknowledgement_note == "Understood"
    assert report.warnings_acknowledged_at is not None
    assert outcome.response.warnings_acknowledged_at == report.warnings_acknowledged_at
    case.replay.complete.assert_awaited_once_with(
        case.reservation,
        response_json=outcome.response.model_dump(mode="json"),
        report_id=str(rows.REPORT),
    )


@pytest.mark.parametrize(
    "fault,error,match",
    [
        ("missing", module.SufficiencyReportNotFound, "not found"),
        ("project_id", module.SufficiencyReportNotFound, "not found"),
        ("guide_id", module.SufficiencyReportNotFound, "not found"),
        ("missing_locked", module.SufficiencyReportNotFound, "not found"),
        (
            "source_snapshot_hash",
            module.GuideSufficiencyMutationConflict,
            "sufficiency_lineage_stale",
        ),
        ("status", module.PolicySetupBlocked, "only sufficiency warnings"),
    ],
)
async def test_acknowledgement_rejects_invalid_report(case, fault, error, match):
    if fault == "missing":
        case.projects.get_guide_sufficiency_report.return_value = None
    elif fault == "missing_locked":
        case.projects.lock_guide_sufficiency_report.return_value = None
    else:
        setattr(case.report, fault, "passed" if fault == "status" else str(UUID(int=99)))
    with pytest.raises(error, match=match):
        await invoke(case, "ack")
    case.prepared.consume.assert_not_awaited()
    case.replay.reserve.assert_not_awaited()
    case.replay.complete.assert_not_awaited()
    assert case.report.warnings_acknowledged_at is None


async def test_acknowledgement_rejects_repeat(case):
    case.report.warnings_acknowledged_at = rows.NOW
    with pytest.raises(module.GuideSufficiencyMutationConflict, match="already_acknowledged"):
        await invoke(case, "ack")
    assert case.report.warnings_acknowledged_at == rows.NOW
    case.replay.reserve.assert_not_awaited()
    case.replay.complete.assert_not_awaited()


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "id",
        "setup_generation",
        "output_sufficiency_report_id",
        "output_submission_artifact_policy_id",
    ],
)
async def test_acknowledgement_rejects_invalid_continuation(case, fault):
    case.report.project_setup_run_id = str(rows.SETUP)
    case.setup.output_sufficiency_report_id = str(rows.REPORT)
    if fault == "missing":
        case.projects.lock_project_setup_run.return_value = None
    else:
        setattr(case.setup, fault, 2 if fault == "setup_generation" else str(UUID(int=99)))
    before = vars(case.setup).copy()
    with pytest.raises(
        module.GuideSufficiencyMutationConflict, match="project_setup_run_context_mismatch"
    ):
        await invoke(case, "ack")
    case.prepared.consume.assert_awaited_once()
    case.projects.lock_project_setup_run.assert_awaited_once_with(str(rows.SETUP))
    assert vars(case.setup) == before
    case.replay.complete.assert_not_awaited()
    # Late failure: database rollback belongs to the real caller-transaction tests.


async def test_acknowledgement_resets_continuation(case):
    case.report.project_setup_run_id = str(rows.SETUP)
    case.setup.output_sufficiency_report_id = str(rows.REPORT)
    before = vars(case.setup).copy()
    outcome = await invoke(case, "ack")
    assert vars(case.setup) == {
        **before,
        "status": "enqueue_failed",
        "current_step": "enqueue",
        "celery_task_id": None,
        "error_code": None,
        "error_summary": None,
    }
    case.projects.lock_project_setup_run.assert_awaited_once_with(str(rows.SETUP))
    case.replay.complete.assert_awaited_once_with(
        case.reservation,
        response_json=outcome.response.model_dump(mode="json"),
        report_id=str(rows.REPORT),
    )
