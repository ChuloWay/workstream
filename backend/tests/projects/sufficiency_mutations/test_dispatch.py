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
    before = vars(case.setup).copy()
    outcome = await invoke(case, "dispatch")
    assert (outcome.replayed, outcome.dispatch_claimed) == (False, True)
    assert vars(case.setup) == {
        **before,
        "status": "dispatch_pending",
        "current_step": "dispatch",
        "error_code": None,
        "error_summary": None,
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
        ("terminal", "guide_sufficiency_run_not_needed"),
        ("output", "guide_sufficiency_run_not_needed"),
        ("material", "verified_guide_material_not_ready"),
        ("task", "project_setup_task_identity_stale"),
    ],
)
async def test_dispatch_rejects_unusable_setup(case, fault, match):
    if fault == "lineage":
        case.service._lineage.return_value = replace(case.lineage, setup_run_id=None)
    elif fault == "missing_row":
        case.projects.lock_project_setup_run.return_value = None
    elif fault == "terminal":
        case.setup.status = "policy_draft_ready"
    elif fault == "output":
        case.setup.output_submission_artifact_policy_id = str(UUID(int=99))
    elif fault == "material":
        case.setup.celery_task_id = None
    else:
        case.setup.celery_task_id = str(UUID(int=99))
    before = vars(case.setup).copy()
    with pytest.raises(module.GuideSufficiencyMutationConflict, match=match):
        await invoke(case, "dispatch")
    case.prepared.consume.assert_not_awaited()
    case.replay.reserve.assert_not_awaited()
    case.replay.complete.assert_not_awaited()
    assert vars(case.setup) == before
