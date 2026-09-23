"""Canonical fixed-service authority for the existing hidden TASK effect."""

from contextlib import asynccontextmanager, contextmanager

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.assignment_invalidation import assignment_invalidation_resource
from app.modules.authorization.prepared import fixed_service_prepared_authorization
from app.modules.authorization.runtime import (
    AuthorizationDenied, PreparedAuthorizationHandleInvalid, PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported, PreparedAuthorityScope, PreparedAuthorityScopeKind,
)
from app.modules.tasks.api.assignment_invalidation import (
    AssignmentInvalidationAuthority, AssignmentInvalidationUnavailable, PreparedAssignmentInvalidation,
)


@contextmanager
def _denials():
    """Terminal denials only; evidence and database uncertainty stay UNKNOWN."""
    try:
        yield
    except (AuthorizationDenied, PreparedAuthorizationHandleInvalid, PreparedAuthorizationUnsupported) as exc:
        raise AssignmentInvalidationUnavailable("assignment reconciliation denied") from exc


def _resource(facts):
    try:
        return assignment_invalidation_resource(facts)
    except (AttributeError, TypeError, ValueError) as exc:
        raise AssignmentInvalidationUnavailable("assignment reconciliation facts invalid") from exc


class _PreparedReconciliation(PreparedAssignmentInvalidation):
    def __init__(self, authority, handle, caller_input):
        self._authority, self._handle, self._input = authority, handle, caller_input

    async def consume(self, facts):
        resource = _resource(facts)
        with _denials():
            decision = await self._authority.service.consume(
                self._handle, ActionId.TASK_ASSIGNMENT_AUTHORITY_RECONCILE, self._input, resource,
            )
        return AssignmentInvalidationAuthority(
            self._authority.actor_profile_id, decision.decision_id, decision.resource_context_digest,
        )


class AssignmentInvalidationAuthorizationAdapter:
    """No principal selector, extra resolver or independent transaction."""

    def __init__(self, session):
        self._session = session

    @asynccontextmanager
    async def prepare_assignment_invalidation(self, facts):
        resource = _resource(facts)
        with _denials():
            async with fixed_service_prepared_authorization(
                self._session, service_identity=ServiceIdentity.TASK_ASSIGNMENT_RECONCILER,
                request_id=facts.delivery_event_id,
                correlation_id=facts.target.authority_invalidation_event_id,
            ) as authority:
                caller_input = PreparedAuthorizationInput(
                    idempotency_key=facts.delivery_event_id,
                    request_value=resource.model_dump(mode="json"),
                )
                handle = await authority.service.prepare(
                    ActionId.TASK_ASSIGNMENT_AUTHORITY_RECONCILE, caller_input,
                    PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.PROJECT, project_id=resource.scope_project_id),
                )
                yield _PreparedReconciliation(authority, handle, caller_input)
