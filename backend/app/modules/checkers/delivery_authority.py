"""Bind hidden request delivery to the canonical executor and real phase AUTH."""

from contextlib import asynccontextmanager

from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable, PreparedExecution, PreparedFinalization,
)


class _DeliveryPhase:
    """Canonical AUTH owns its receipt; delivery only adds exact invocation custody."""

    def __init__(self, prepared, fence, envelope, request, eligible):
        self._prepared, self._fence = prepared, fence
        self._envelope, self._request, self._eligible = envelope, request, eligible

    def _require_request(self, facts):
        if facts.request != self._request:
            raise CheckerExecutionUnavailable("checker_delivery_request_unavailable")

    async def _require_invocation(self):
        observed = await self._fence.fence_invocation(self._envelope)
        if observed is None or observed.claim != self._envelope.claim:
            raise CheckerExecutionUnavailable("checker_delivery_invocation_unavailable")

    async def validate_replay(self, facts, evidence_id):
        self._require_request(facts)
        await self._prepared.validate_replay(facts, evidence_id)
        await self._require_invocation()


class _DeliveryExecute(_DeliveryPhase, PreparedExecution):
    async def consume(self, facts):
        self._require_request(facts)
        # Expired running custody is uncertain, not permission for another try.
        if not self._eligible or facts.lease.lease_generation != 1:
            raise CheckerExecutionUnavailable("checker_delivery_execution_unavailable")
        evidence = await self._prepared.consume(facts)
        await self._require_invocation()
        return evidence


class _DeliveryFinalize(_DeliveryPhase, PreparedFinalization):
    async def consume(self, facts):
        self._require_request(facts)
        if not self._eligible:
            raise CheckerExecutionUnavailable("checker_delivery_execution_unavailable")
        evidence = await self._prepared.consume(facts)
        await self._require_invocation()
        return evidence


class DeliveryExecutionAuthority:
    """TASK precedes AUTH and CHECKERS; outbox locks follow in consume/replay."""

    def __init__(self, *, authority, tasks, fence, envelope, request):
        self._envelope, self._request = envelope, request
        self._authority, self._tasks, self._fence = authority, tasks, fence

    async def preflight(self, request):
        if request != self._request:
            raise CheckerExecutionUnavailable("checker_delivery_request_unavailable")
        await self._authority.preflight(request)

    @asynccontextmanager
    async def prepare_execution(self, request):
        eligible = await self._tasks.lock_evaluation_scope(request)
        async with self._authority.prepare_execution(request) as prepared:
            yield _DeliveryExecute(prepared, self._fence,
                                   self._envelope, self._request, eligible)

    @asynccontextmanager
    async def prepare_finalization(self, request):
        eligible = await self._tasks.lock_evaluation_scope(request)
        async with self._authority.prepare_finalization(request) as prepared:
            yield _DeliveryFinalize(prepared, self._fence,
                                    self._envelope, self._request, eligible)
