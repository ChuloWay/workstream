"""Observable HTTP and real-lock coordination; no authentication decisions."""

import asyncio

from httpx import MockTransport, Response

from app.adapters.auth.flow import FlowAuthVerifier
from tests.authentication.support import production_verifier_settings


class RefreshOverlap:
    """Hold a real refresh until the test observes a waiter or duplicate I/O."""

    def __init__(self, jwk, monkeypatch, *, advance_after_wait=False):
        self.requests = []
        self.first_request = asyncio.Event()
        self.overlap = asyncio.Event()
        self.waiter = asyncio.Event()
        self.release_http = asyncio.Event()
        self.clock = [0.0]

        async def transport(request):
            self.requests.append(request)
            if len(self.requests) == 1:
                self.first_request.set()
            else:
                self.overlap.set()
            await self.release_http.wait()
            return Response(200, json={"keys": [jwk]})

        self.verifier = FlowAuthVerifier(
            production_verifier_settings(),
            jwks_transport=MockTransport(transport),
            monotonic=lambda: self.clock[0],
        )
        lock = self.verifier._refresh_lock
        original_acquire = lock.acquire

        async def observe_acquire():
            contending = lock.locked()
            if contending:
                self.waiter.set()
                self.overlap.set()
            result = await original_acquire()
            if contending and advance_after_wait:
                # Expire cooldown so the generation guard must stand alone.
                self.clock[0] = 31.0
            return result

        monkeypatch.setattr(lock, "acquire", observe_acquire)
