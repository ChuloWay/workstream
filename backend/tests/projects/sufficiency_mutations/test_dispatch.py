"""Manual dispatch intent, unusable context, and queue-progress replay."""

from dataclasses import replace
from uuid import UUID

import pytest

from app.modules.projects import sufficiency_mutation_service as module
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.sufficiency_mutations import rows
from projects.sufficiency_mutations.commands import invoke, seed_replay
from projects.sufficiency_mutations.fixtures import case as case


async def test_dispatch_stages_exact_intent(case):
    expected_task_id = case.setup.celery_task_id
    case.setup.celery_task_id = None
    case.setup.continuation_verification_job_id = str(UUID(int=31))
    before = vars(case.setup).copy()
    outcome = await invoke(case, "dispatch")
    assert (outcome.replayed, outcome.dispatch_claimed) == (False, True)
    assert vars(case.setup) == {
        **before,
        "status": "dispatch_pending",
        "current_step": "dispatch",
        "error_code": None,
        "error_summary": None,
        "celery_task_id": expected_task_id,
    }
    assert outcome.response.status == "dispatch_pending"
    case.projects.lock_project_setup_run.assert_awaited_once_with(str(rows.SETUP))
    case.projects.get_sufficiency_report_for_snapshot.assert_awaited_once_with(str(rows.SNAPSHOT))
    case.prepared.consume.assert_awaited_once()
    case.replay.complete.assert_awaited_once_with(
        case.reservation,
        response_json=outcome.response.model_dump(mode="json"),
        report_id=None,
    )
    case.session.commit.assert_not_awaited()


async def test_dispatch_preserves_already_queued_intent(case):
    case.setup.status = "queued"
    before = vars(case.setup).copy()
    outcome = await invoke(case, "dispatch")
    assert (outcome.replayed, outcome.dispatch_claimed) == (False, False)
    assert vars(case.setup) == before
    assert outcome.response.celery_task_id == before["celery_task_id"]
    case.prepared.consume.assert_awaited_once()
    case.replay.complete.assert_awaited_once_with(
        case.reservation,
        response_json=outcome.response.model_dump(mode="json"),
        report_id=None,
    )


@pytest.mark.parametrize("field", ["project_setup_run_id", "setup_generation"])
async def test_dispatch_ignores_unrelated_report(case, field):
    case.report.project_setup_run_id = str(rows.SETUP)
    case.report.setup_generation = 1
    setattr(case.report, field, 2 if field == "setup_generation" else str(UUID(int=99)))
    case.projects.get_sufficiency_report_for_snapshot.return_value = case.report
    outcome = await invoke(case, "dispatch")
    assert outcome.dispatch_claimed is True
    case.prepared.consume.assert_awaited_once()
    case.replay.complete.assert_awaited_once()


async def test_dispatch_replay_survives_queue_progress(case):
    record = await seed_replay(case, "dispatch")
    case.service._lineage.return_value = replace(
        case.lineage, stale_output_digest=rows.RESOURCE_HASH
    )
    case.setup.status = "running_sufficiency_agent"
    before = vars(case.setup).copy()
    outcome = await invoke(case, "dispatch")
    assert (outcome.replayed, outcome.dispatch_claimed) == (True, False)
    assert outcome.response.model_dump(mode="json") == record.response_json
    assert vars(case.setup) == before
    case.prepared.consume.assert_awaited_once()
    case.replay.reserve.assert_not_awaited()
    case.replay.complete.assert_not_awaited()


@pytest.mark.parametrize(
    "fault,match",
    [
        ("lineage", "project_setup_run_context_mismatch"),
        ("missing_row", "project_setup_run_context_mismatch"),
        *(
            (status, "guide_sufficiency_run_not_needed")
            for status in (
                "sufficiency_blocked",
                "running_policy_derivation_agent",
                "policy_draft_ready",
                "running_post_submit_derivation_agent",
                "post_submit_setup_blocked",
                "post_submit_policy_compiled",
            )
        ),
        *(
            (field, "guide_sufficiency_run_not_needed")
            for field in (
                "output_sufficiency_report_id",
                "output_submission_artifact_policy_id",
                "output_post_submit_checker_policy_id",
            )
        ),
        ("authoritative_report", "guide_sufficiency_run_not_needed"),
        ("material", "verified_guide_material_not_ready"),
        ("task", "project_setup_task_identity_stale"),
    ],
)
async def test_dispatch_rejects_unusable_setup(case, fault, match):
    if fault == "lineage":
        case.service._lineage.return_value = replace(case.lineage, setup_run_id=None)
    elif fault == "missing_row":
        case.projects.lock_project_setup_run.return_value = None
    elif fault.startswith("output_"):
        setattr(case.setup, fault, str(UUID(int=99)))
    elif fault == "authoritative_report":
        case.report.project_setup_run_id = str(rows.SETUP)
        case.report.setup_generation = 1
        case.projects.get_sufficiency_report_for_snapshot.return_value = case.report
    elif fault == "material":
        case.setup.celery_task_id = None
    elif fault == "task":
        case.setup.celery_task_id = str(UUID(int=99))
    else:
        case.setup.status = fault
    before = vars(case.setup).copy()
    with pytest.raises(module.GuideSufficiencyMutationConflict, match=match):
        await invoke(case, "dispatch")
    case.prepared.consume.assert_not_awaited()
    case.replay.reserve.assert_not_awaited()
    case.replay.complete.assert_not_awaited()
    assert vars(case.setup) == before
