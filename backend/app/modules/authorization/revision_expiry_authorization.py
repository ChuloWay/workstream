"""Prepared service authority for the TASK-owned expiry operation."""

from contextlib import asynccontextmanager

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.revision_expiry import revision_expiry_resource
from app.modules.authorization.prepared import fixed_service_prepared_authorization
from app.modules.authorization.runtime import (
    AuthorizationDenied, PreparedAuthorizationHandleInvalid, PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported, PreparedAuthorityScope, PreparedAuthorityScopeKind,
)
from app.modules.tasks.api.revision_expiry import TaskRevisionExpiryAuthority, TaskRevisionExpiryUnavailable


class _PreparedExpiry:
    """Consume one process-local prepared handle against fresh locked facts."""
    def __init__(self, authority, handle, caller_input):
        """Retain the transaction-local authority and exact prepared request."""
        self._authority, self._handle, self._input = authority, handle, caller_input

    async def consume(self, facts):
        """Revalidate fixed-service authority before the expiry effect is written."""
        try:
            resource = revision_expiry_resource(facts)
            decision = await self._authority.service.consume(
                self._handle, ActionId.TASK_REVISION_EXPIRE, self._input, resource,
            )
        except (AuthorizationDenied, PreparedAuthorizationHandleInvalid,
                PreparedAuthorizationUnsupported, TypeError, ValueError) as exc:
            raise TaskRevisionExpiryUnavailable("revision expiry authority unavailable") from exc
        return TaskRevisionExpiryAuthority(
            self._authority.actor_profile_id, decision.decision_id, decision.resource_context_digest,
        )


class RevisionExpiryAuthorizationAdapter:
    """Adapt the fixed revision-expirer identity to TASK expiry authority."""
    def __init__(self, session):
        """Use the caller session so authorization and expiry commit together."""
        self._session = session

    @asynccontextmanager
    async def prepare_revision_expiry(self, facts):
        """Prepare the exact event, source and project binding for consumption."""
        try:
            resource = revision_expiry_resource(facts)
            async with fixed_service_prepared_authorization(
                self._session, service_identity=ServiceIdentity.TASK_REVISION_EXPIRER,
                request_id=facts.delivery_event_id,
                correlation_id=facts.target.routing_manifest_id,
            ) as authority:
                caller_input = PreparedAuthorizationInput(
                    idempotency_key=facts.delivery_event_id,
                    request_value=resource.model_dump(mode="json"),
                )
                handle = await authority.service.prepare(
                    ActionId.TASK_REVISION_EXPIRE, caller_input,
                    PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.PROJECT,
                                           project_id=resource.scope_project_id),
                )
                yield _PreparedExpiry(authority, handle, caller_input)
        except (AuthorizationDenied, PreparedAuthorizationHandleInvalid,
                PreparedAuthorizationUnsupported, TypeError, ValueError) as exc:
            raise TaskRevisionExpiryUnavailable("revision expiry authority unavailable") from exc
