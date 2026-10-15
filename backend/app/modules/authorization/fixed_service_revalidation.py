"""Fresh actor and identity-link checks for fixed-service authority."""

from uuid import UUID

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind, ActorStatus, IdentityLinkStatus, ServiceAuthorizationContext,
)


def fixed_service_context_revalidator(
    repository: AdminAuthorizationRepository,
    expected_identity: ServiceIdentity,
):
    """Build AUTH's canonical fixed-service lifecycle revalidator."""

    async def revalidate(
        original: ServiceAuthorizationContext,
        _requested_action: ActionId,
    ) -> ServiceAuthorizationContext | None:
        locked = await repository.lock_request_actor(
            original.identity_link_id, original.actor_profile_id
        )
        if locked is None:
            return None
        link, profile = locked
        if (
            profile.actor_kind != ActorKind.SERVICE.value
            or profile.service_identity != expected_identity.value
        ):
            return None
        try:
            return ServiceAuthorizationContext(
                actor_profile_id=UUID(profile.id),
                actor_kind=ActorKind.SERVICE,
                actor_status=ActorStatus(profile.status),
                identity_link_id=UUID(link.id),
                identity_link_status=IdentityLinkStatus(link.status),
                service_identity=expected_identity,
                request_id=original.request_id,
                correlation_id=original.correlation_id,
            )
        except (TypeError, ValueError):
            return None

    return revalidate
