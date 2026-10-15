"""Record one attempt outcome inside the deciding owner's own transaction."""

from typing import Literal

from sqlalchemy import update

from app.modules.tasks.models import Submission

AttemptOutcome = Literal["review_pending", "accepted", "needs_revision", "rejected"]
# PostgreSQL records this reason on a needs_revision attempt whose run had no
# failed member: a checker coverage gap returned to the contributor.
COVERAGE_RETURN_REASON = "checker_coverage_incomplete"


async def record_attempt_outcome(session, *, submission_id, task_id, outcome: AttemptOutcome) -> None:
    """Request the transition; PostgreSQL derives its time and reason from committed evidence.

    The deciding owner must already have flushed that evidence (routing manifest,
    FinalAcceptance or revision expiration) in the same transaction.
    """
    result = await session.execute(
        update(Submission)
        .where(Submission.id == str(submission_id), Submission.task_id == str(task_id))
        .values(attempt_status=outcome)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise RuntimeError("submission attempt outcome target unavailable")
