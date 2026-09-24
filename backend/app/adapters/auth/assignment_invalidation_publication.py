"""Map newly staged AUTH loss into exact same-transaction OUTBOX targets."""

from uuid import uuid5

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.modules.authorization.api.assignment_invalidation import (
    AuthorityInvalidationPublication, AuthorityInvalidationPublicationUnavailable,
)
from app.modules.tasks.api.assignment_invalidation import (
    ASSIGNMENT_INVALIDATION_EVENT, AssignmentInvalidationTargetsPort,
    AssignmentInvalidationTargetsRequest,
)
from app.modules.outbox.api import (
    OutboxAppendInput, OutboxIdempotencyConflict, OutboxInputError,
    OutboxPersistenceError, OutboxAppendPort,
)


class AssignmentInvalidationPublication:
    """No commit, broker call or retained audit scan; failures abort the caller."""

    def __init__(self, targets: AssignmentInvalidationTargetsPort, outbox: OutboxAppendPort):
        self._targets, self._outbox = targets, outbox

    async def publish(self, facts: AuthorityInvalidationPublication) -> None:
        try:
            facts = AuthorityInvalidationPublication.model_validate(facts.model_dump())
            after = None
            while True:
                page = await self._targets.read_assignment_invalidation_targets_page(
                    AssignmentInvalidationTargetsRequest(
                        contributor_id=facts.contributor_id, project_id=facts.project_id,
                        invalidation_event_id=facts.invalidation_event_id,
                        invalidated_at=facts.invalidated_at, after=after,
                    )
                )
                for target in page.items:
                    event_id = uuid5(facts.invalidation_event_id, f"assignment:{target.assignment_id}")
                    await self._outbox.append(OutboxAppendInput(
                        event_id=event_id, event_type=ASSIGNMENT_INVALIDATION_EVENT, event_version=1,
                        aggregate_type="task_assignment", aggregate_id=target.assignment_id,
                        project_id=target.project_id, correlation_id=facts.correlation_id,
                        causation_event_id=facts.invalidation_event_id,
                        idempotency_key=f"assignment-invalidation:{event_id}",
                        payload=target.model_dump(mode="json"),
                    ))
                if page.next_after is None:
                    return
                after = page.next_after
        except (SQLAlchemyError, ValidationError, OutboxIdempotencyConflict,
                OutboxInputError, OutboxPersistenceError):
            raise AuthorityInvalidationPublicationUnavailable("authority publication unavailable") from None


def assignment_invalidation_publication(session):
    """Bind explicit public ports to the originating caller session."""
    from app.adapters.tasks import assignment_invalidation_targets
    from app.adapters.outbox import outbox_append

    return AssignmentInvalidationPublication(assignment_invalidation_targets(session), outbox_append(session))
