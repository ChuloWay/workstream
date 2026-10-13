"""Fixed selected-PRE principal through canonical AUTH/PREP."""

from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.domain.pre_submit import (
    EXECUTE,
    FINALIZE,
    pre_submit_prepare_values,
    pre_submit_resource,
)
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
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitAuthorityEvidence,
    SelectedPreSubmitAuthorityUnavailable,
)


@contextmanager
def _authority_errors():
    try:
        yield
    except (
        AuthorizationDenied,
        AuthorizationEvidenceUnavailable,
        PreparedAuthorizationHandleInvalid,
        PreparedAuthorizationUnsupported,
    ) as error:
        raise SelectedPreSubmitAuthorityUnavailable(
            "selected_pre_submit_authority_unavailable"
        ) from error


class _PreparedPhase:
    def __init__(self, service, handle, caller_input, action):
        self._service = service
        self._handle = handle
        self._input = caller_input
        self._action = action

    async def consume(self, facts):
        with _authority_errors():
            decision = await self._service.consume(
                self._handle,
                self._action,
                self._input,
                pre_submit_resource(self._action, facts),
            )
        return SelectedPreSubmitAuthorityEvidence(
            evidence_id=decision.decision_id,
            facts_digest=facts.facts_digest,
        )


@asynccontextmanager
async def _prepare(session, action, reservation):
    """Acquire the fixed principal before selected owner locks."""
    values = pre_submit_prepare_values(reservation)
    with _authority_errors():
        async with fixed_service_prepared_authorization(
            session,
            service_identity=ServiceIdentity.CHECKER_PRE_SUBMIT,
            request_id=reservation.attempt_id,
            correlation_id=reservation.attempt_id,
        ) as authority:
            caller_input = PreparedAuthorizationInput(
                idempotency_key=reservation.attempt_id,
                request_value=values,
            )
            handle = await authority.service.prepare(
                action,
                caller_input,
                PreparedAuthorityScope(
                    kind=PreparedAuthorityScopeKind.PROJECT,
                    project_id=reservation.project_id,
                ),
            )
            yield _PreparedPhase(authority.service, handle, caller_input, action)


class SelectedPreSubmitAuthorization:
    """Expose only execute and finalize for the fixed selected-PRE principal."""

    def __init__(self, session):
        self._session = session

    def prepare_execution(self, reservation):
        return _prepare(self._session, EXECUTE, reservation)

    def prepare_finalization(self, facts):
        return _prepare(self._session, FINALIZE, facts.lease.reservation)


__all__ = ("SelectedPreSubmitAuthorization",)
