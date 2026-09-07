"""Controlled AUTH service fixtures; not PostgreSQL or real transaction proof."""

from __future__ import annotations
from types import SimpleNamespace
from uuid import uuid4
from app.modules.actors.api import ServiceIdentity
from app.modules.audit.schemas import AuthorityAuditEventInput
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    IdentityLinkStatus,
    AuthorizationContext,
    HumanAuthorizationContext,
    ServiceAuthorizationContext,
)


def _runtime_context(
    *,
    actor_status: ActorStatus = ActorStatus.ACTIVE,
    link_status: IdentityLinkStatus = IdentityLinkStatus.ACTIVE,
    actor_kind: ActorKind = ActorKind.HUMAN,
    service_identity: ServiceIdentity = ServiceIdentity.ARTIFACT_VERIFIER,
) -> AuthorizationContext:
    context_type = (
        ServiceAuthorizationContext
        if actor_kind is ActorKind.SERVICE
        else HumanAuthorizationContext
    )
    service_fields = (
        {"service_identity": service_identity} if actor_kind is ActorKind.SERVICE else {}
    )
    return context_type(
        actor_profile_id=uuid4(),
        actor_kind=actor_kind,
        actor_status=actor_status,
        identity_link_id=uuid4(),
        identity_link_status=link_status,
        request_id=uuid4(),
        correlation_id=uuid4(),
        **service_fields,
    )


class _DecisionEvidence:
    def __init__(self) -> None:
        self.events: list[AuthorityAuditEventInput] = []

    async def add_authority_event(self, event: AuthorityAuditEventInput) -> None:
        self.events.append(event)


_DEFAULT_REVALIDATOR = object()


def _runtime_service(
    context: AuthorizationContext,
    *,
    session=None,
    admin_repository=None,
    revalidate=_DEFAULT_REVALIDATOR,
    revalidate_service=None,
) -> tuple[AuthorizationService, _DecisionEvidence]:
    if revalidate is _DEFAULT_REVALIDATOR:

        async def revalidate(current, _resource):
            return current

    service = AuthorizationService(
        session if session is not None else object(),  # type: ignore[arg-type]
        context,
        revalidate_actor_self=revalidate,
        revalidate_service=revalidate_service,
        admin_repository=admin_repository,
    )
    evidence = _DecisionEvidence()
    service._audit = evidence  # type: ignore[assignment]
    return service, evidence


class _PreparedTestSession:
    """Minimal stable-root session contract for capability unit tests."""

    def __init__(self) -> None:
        self.root = SimpleNamespace(is_active=True)
        self.nested = False
        self.sync_session = self

    def get_transaction(self):
        return self.root

    def in_nested_transaction(self) -> bool:
        return self.nested
