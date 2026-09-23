"""Explicit composition of the shared delivery owner; feature registration is separate."""

from collections.abc import Callable
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.authorization.api.outbox_dispatch import OutboxDispatchAuthorizationPort
from app.modules.outbox.api import DeliveryOptions
from app.modules.outbox.delivery import OutboxDelivery
from app.modules.outbox.registry import HandlerRegistry


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
    """Install real dispatcher authority with no unapproved feature handler."""
    from app.adapters.auth import outbox_dispatch_authorization

    return outbox_delivery(
        session_factory, authorization_factory=outbox_dispatch_authorization,
        registry=HandlerRegistry([]), options=DeliveryOptions(),
    )
