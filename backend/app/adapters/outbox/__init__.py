"""Explicit composition of the shared delivery owner; feature registration is separate."""

from collections.abc import Callable
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.authorization.api.outbox_dispatch import OutboxDispatchAuthorizationPort
from app.modules.outbox.api import DeliveryOptions, InvocationFencePort, OutboxAppendPort
from app.modules.outbox.delivery import OutboxDelivery, CommittedInvocationReader
from app.modules.outbox.delivery_repository import DeliveryRepository
from app.modules.outbox.registry import HandlerRegistry


def outbox_invocation_fence(session: AsyncSession) -> InvocationFencePort:
    """Use the existing owner's locks in the caller's effect transaction."""
    return DeliveryRepository(session)


def outbox_delivery(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    authorization_factory: Callable[[AsyncSession], OutboxDispatchAuthorizationPort],
    registry: HandlerRegistry,
    options: DeliveryOptions,
) -> OutboxDelivery:
    """No default authority, installed handler, worker or runtime discovery."""
    return OutboxDelivery(
        session_factory,
        authorization_factory=authorization_factory,
        registry=registry,
        options=options,
    )


def production_outbox_delivery(session_factory):
    """Install exact assignment and selected evaluation handlers."""
    from app.adapters.artifacts import worker_post_submission_materialization
    from app.adapters.auth import (
        outbox_dispatch_authorization,
        assignment_invalidation_authorization,
    )
    from app.adapters.tasks import (
        TransactionalAssignmentInvalidationHandler,
        evaluation_completion_handler,
        evaluation_request_handler,
    )
    from app.modules.checkers.api.execution import COMPLETION_EVENT, REQUEST_EVENT
    from app.modules.tasks.api.assignment_invalidation import ASSIGNMENT_INVALIDATION_EVENT

    return outbox_delivery(
        session_factory,
        authorization_factory=outbox_dispatch_authorization,
        registry=HandlerRegistry(
            [
                (
                    ASSIGNMENT_INVALIDATION_EVENT,
                    1,
                    TransactionalAssignmentInvalidationHandler(
                        session_factory,
                        observer=CommittedInvocationReader(session_factory),
                        authorization_factory=assignment_invalidation_authorization,
                    ),
                ),
                (
                    REQUEST_EVENT,
                    1,
                    evaluation_request_handler(
                        sessions=session_factory,
                        materialization=worker_post_submission_materialization(
                            sessions=session_factory
                        ),
                    ),
                ),
                (
                    COMPLETION_EVENT,
                    1,
                    evaluation_completion_handler(sessions=session_factory),
                ),
            ]
        ),
        options=DeliveryOptions(),
    )


def outbox_append(session: AsyncSession) -> OutboxAppendPort:
    """Compose the sole append participant behind its public transaction port."""
    from app.modules.outbox.service import OutboxService

    return OutboxService(session)


def committed_invocation_reader(sessions):
    """Expose the existing independent observer without private cross-owner imports."""
    return CommittedInvocationReader(sessions)
