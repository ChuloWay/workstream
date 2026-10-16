"""ART projection of a contributor's selected PRE runs and their retained intake custody."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.api.submission_preparation import (
    PreparationFindingCounts, SubmissionBundlePreparationDetail, SubmissionBundlePreparationStatus,
    pre_submission_finding_counts, public_pre_submission_results,
)
from app.modules.artifacts.models import (
    ArtifactPutAttempt, SubmissionBundleAdmission, SubmissionBundleDurableIntent,
)
from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitRunReadPort

_ADMISSION_STATE = {"ready": "ready", "consumed": "submitted", "stale": "stale"}


class SubmissionBundlePreparationReader:
    """Read-only; the caller supplies authority and the response transaction."""

    def __init__(self, session: AsyncSession, *, runs: SelectedPreSubmitRunReadPort) -> None:
        self._session, self._runs = session, runs

    async def read(self, *, actor_profile_id, task_id, preparation_id, limit, before):
        views, more = await self._runs.read_contributor_runs(
            actor_profile_id=actor_profile_id, task_id=task_id, run_id=preparation_id,
            limit=limit, before=before,
        )
        custody = {}
        if views:
            rows = (await self._session.execute(select(
                SubmissionBundleDurableIntent.selected_pre_submit_run_id, ArtifactPutAttempt.status,
                SubmissionBundleAdmission.id, SubmissionBundleAdmission.status,
                SubmissionBundleAdmission.consumed_by_submission_id,
            ).join(
                ArtifactPutAttempt, ArtifactPutAttempt.id == SubmissionBundleDurableIntent.put_attempt_id,
            ).outerjoin(
                SubmissionBundleAdmission,
                SubmissionBundleAdmission.durable_intent_id == SubmissionBundleDurableIntent.id,
            ).where(
                SubmissionBundleDurableIntent.selected_pre_submit_run_id.in_([str(view.run_id) for view in views]),
            ))).all()
            custody = {UUID(str(row[0])): row[1:] for row in rows}
        items = []
        for view in views:
            terminal = view.terminal
            execution = terminal.execution if terminal is not None else None
            stored = custody.get(view.run_id)
            if view.status in {"queued", "running"}:
                outcome, state = "pending", "checking"
            elif view.status == "infrastructure_failed":
                outcome, state = "infrastructure_failed", "infrastructure_failed"
            elif not execution.eligible:
                outcome, state = "failed", "checks_failed"
            else:
                outcome = "passed"
                state = _ADMISSION_STATE[stored[2]] if stored is not None and stored[2] is not None else "storing"
            items.append(SubmissionBundlePreparationDetail(
                preparation_id=view.run_id, task_id=view.task_id, assignment_id=view.assignment_id,
                outcome=outcome, state=state,
                storage_status=SubmissionBundlePreparationStatus(stored[0]) if stored is not None else None,
                infrastructure_failure_code=terminal.infrastructure_failure_code if terminal is not None else None,
                archive_sha256=view.archive_sha256, archive_byte_count=view.archive_byte_count,
                finding_counts=(
                    PreparationFindingCounts(**pre_submission_finding_counts(execution))
                    if execution is not None else None
                ),
                admission_id=stored[1] if stored is not None and stored[2] == "ready" else None,
                submission_id=stored[3] if stored is not None else None,
                created_at=view.queued_at, completed_at=view.completed_at,
                findings=public_pre_submission_results(execution) if execution is not None else [],
            ))
        return tuple(items), more
