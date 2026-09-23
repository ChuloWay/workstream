"""Fixed dispatcher authority over the existing AUTH/PREP owner."""

from contextlib import asynccontextmanager, contextmanager

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.api import (
    AuthorizationDenied as BoundaryDenied,
    AuthorizationUnavailable,
    PreparedAuthorizationInvalid,
)
from app.modules.authorization.api.decisions import AuthorizationDecision, DecisionOutcome
from app.modules.authorization.api.outbox_dispatch import (
    PreparedOutboxDispatch,
    outbox_dispatch_resource_digest,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.outbox_dispatch import outbox_dispatch_resource
from app.modules.authorization.prepared import fixed_service_prepared_authorization
from app.modules.authorization.runtime import (
    AuthorizationDenied,
    AuthorizationEvidenceUnavailable,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)


@contextmanager
def _authority_errors():
    """Expose stable boundary failures without swallowing owner exceptions."""
    try:
        yield
    except PreparedAuthorizationHandleInvalid as exc:
        raise PreparedAuthorizationInvalid("invalid outbox authority") from exc
    except (PreparedAuthorizationUnsupported, AuthorizationDenied) as exc:
        raise BoundaryDenied("outbox authority denied") from exc
    except AuthorizationEvidenceUnavailable as exc:
        raise AuthorizationUnavailable("outbox authority unavailable") from exc


class _PreparedDispatch(PreparedOutboxDispatch):
    """Shared PREP alone retains one-use/session/root-transaction custody."""

    def __init__(self, service, handle, caller_input, digest):
        self._service, self._handle = service, handle
        self._input, self._digest = caller_input, digest

    async def consume(self, facts):
        """Compare recomposed owner facts before consuming the exact capability."""
        try:
            resource = outbox_dispatch_resource(facts)
            if outbox_dispatch_resource_digest(facts) != self._digest:
                raise ValueError("facts changed")
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreparedAuthorizationInvalid("invalid outbox facts") from exc
        with _authority_errors():
            decision = await self._service.consume(
                self._handle,
                ActionId.OUTBOX_DISPATCH,
                self._input,
                resource,
            )
        return AuthorizationDecision(
            decision_id=decision.decision_id,
            action_id=decision.action_id.value,
            permission_id=decision.permission_id.value,
            outcome=DecisionOutcome.ALLOW if decision.allowed else DecisionOutcome.DENY,
            denial_code=decision.denial_code.value if decision.denial_code else None,
        )


class OutboxDispatchAuthorizationAdapter:
    """Resolve the fixed principal at each phase, never from broker selectors."""

    def __init__(self, session):
        self._session = session

    @asynccontextmanager
    async def prepare_outbox_dispatch(self, *, facts, request_id, correlation_id):
        """Acquire service locks before OUTBOX locks its event and attempt."""
        try:
            resource = outbox_dispatch_resource(facts)
            digest = outbox_dispatch_resource_digest(resource.facts)
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreparedAuthorizationInvalid("invalid outbox facts") from exc
        with _authority_errors():
            async with fixed_service_prepared_authorization(
                self._session,
                service_identity=ServiceIdentity.OUTBOX_DISPATCHER,
                request_id=request_id,
                correlation_id=correlation_id,
            ) as authority:
                caller_input = PreparedAuthorizationInput(
                    idempotency_key=request_id,
                    request_value={"outbox_dispatch_digest": digest},
                )
                handle = await authority.service.prepare(
                    ActionId.OUTBOX_DISPATCH,
                    caller_input,
                    PreparedAuthorityScope(
                        kind=PreparedAuthorityScopeKind.PROJECT,
                        project_id=resource.scope_project_id,
                    ),
                )
                yield _PreparedDispatch(authority.service, handle, caller_input, digest)
