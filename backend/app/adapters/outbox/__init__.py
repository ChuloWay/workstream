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
    """Install the exact assignment handler with separate dispatcher and feature authority."""
    from app.adapters.auth import outbox_dispatch_authorization, assignment_invalidation_authorization
    from app.adapters.tasks import TransactionalAssignmentInvalidationHandler
    from app.modules.tasks.api.assignment_invalidation import ASSIGNMENT_INVALIDATION_EVENT

    return outbox_delivery(
        session_factory, authorization_factory=outbox_dispatch_authorization,
        registry=HandlerRegistry([(ASSIGNMENT_INVALIDATION_EVENT, 1,
            TransactionalAssignmentInvalidationHandler(
                session_factory, observer=CommittedInvocationReader(session_factory),
                authorization_factory=assignment_invalidation_authorization,
            ),
        )]), options=DeliveryOptions(),
    )


def outbox_append(session: AsyncSession) -> OutboxAppendPort:
    """Compose the sole append participant behind its public transaction port."""
    from app.modules.outbox.service import OutboxService

    return OutboxService(session)
