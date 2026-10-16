"""Read exact terminal facts without granting current assignment or history authority."""

from sqlalchemy import case, func, select

from app.modules.tasks.api.assignment_outcome import TaskAssignmentOutcome
from app.modules.tasks.models import TaskAssignment
from app.modules.tasks.revision.models import TaskRevisionExhaustion
from app.modules.tasks.revision.models import TaskRevisionExpiration


async def latest_assignment_outcome(session, *, project_id, task_id, contributor_id=None):
    """Project the last closed assignment within an already authorized audience."""
    assignment, exhaustion, expiration = TaskAssignment, TaskRevisionExhaustion, TaskRevisionExpiration
    statement = select(
        assignment.id.label("assignment_id"),
        func.coalesce(exhaustion.source_submission_id, expiration.source_submission_id).label("submission_id"),
        assignment.status,
        case((exhaustion.id.is_not(None), "revision_limit_reached"), else_="revision_deadline_expired").label("status_reason"),
        assignment.released_at.label("closed_at"),
    ).outerjoin(exhaustion, exhaustion.assignment_id == assignment.id).outerjoin(
        expiration, expiration.assignment_id == assignment.id,
    ).where(
        assignment.project_id == str(project_id), assignment.task_id == str(task_id),
        assignment.status.in_(("revision_exhausted", "revision_expired")),
        assignment.released_at.is_not(None),
        (exhaustion.id.is_not(None) | expiration.id.is_not(None)),
    )
    if contributor_id is not None:
        statement = statement.where(assignment.contributor_id == str(contributor_id))
    with session.no_autoflush:
        row = (await session.execute(statement.order_by(
            assignment.released_at.desc(), assignment.id.desc(),
        ).limit(1))).mappings().one_or_none()
    return TaskAssignmentOutcome(**row) if row is not None else None
