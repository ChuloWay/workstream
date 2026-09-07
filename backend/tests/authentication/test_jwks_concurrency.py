"""JWKS refresh exclusion and deadlines with observable contention."""

import asyncio

from httpx import MockTransport
import pytest

from app.adapters.auth.flow import FlowAuthVerifier
from app.interfaces.auth import AuthVerificationError, AuthVerificationUnavailableError
from tests.authentication.concurrency_support import RefreshOverlap
from tests.authentication.support import (
    issue_asymmetric_token,
    jwks_transport,
    production_verifier_settings,
)


@pytest.mark.parametrize("distinct", [False, True], ids=["same-kid", "distinct-kid-after-cooldown"])
async def test_unknown_kid_refresh_is_single_flight(rsa_signing_material, monkeypatch, distinct):
    private_key, jwk = rsa_signing_material
    case = RefreshOverlap(jwk, monkeypatch, advance_after_wait=distinct)
    tokens = [
        issue_asymmetric_token(private_key, kid="unknown-a"),
        issue_asymmetric_token(private_key, kid="unknown-b" if distinct else "unknown-a"),
    ]
    tasks = []
    try:
        tasks.append(asyncio.create_task(case.verifier.verify(tokens[0])))
        await asyncio.wait_for(case.first_request.wait(), timeout=2)
        tasks.append(asyncio.create_task(case.verifier.verify(tokens[1])))
        await asyncio.wait_for(case.overlap.wait(), timeout=2)
        assert len(case.requests) == 1, "contender performed a duplicate refresh"
        assert case.waiter.is_set(), "contender never attempted the held real lock"
        assert all(not task.done() for task in tasks)
        case.release_http.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=2)
        assert all(isinstance(result, AuthVerificationError) for result in results)
        assert all(str(result) == "token key identifier is unknown" for result in results)
        assert len(case.requests) == 1
    finally:
        case.release_http.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_jwks_http_request_is_inside_total_deadline(rsa_signing_material):
    private_key, _jwk = rsa_signing_material
    requests = []

    async def slow_jwks(request):
        requests.append(request)
        await asyncio.Event().wait()
        raise AssertionError("unreleased HTTP request unexpectedly resumed")

    verifier = FlowAuthVerifier(
        production_verifier_settings(token_jwks_total_timeout_seconds=0.5),
        jwks_transport=MockTransport(slow_jwks),
    )
    with pytest.raises(AuthVerificationUnavailableError, match="unavailable|timed out"):
        await asyncio.wait_for(verifier.verify(issue_asymmetric_token(private_key)), timeout=2)
    assert len(requests) == 1


async def test_jwks_lock_wait_is_inside_total_deadline(rsa_signing_material):
    private_key, jwk = rsa_signing_material
    requests = []
    verifier = FlowAuthVerifier(
        production_verifier_settings(token_jwks_total_timeout_seconds=0.5),
        jwks_transport=jwks_transport(jwk, requests),
    )
    await verifier._refresh_lock.acquire()
    try:
        with pytest.raises(
            AuthVerificationUnavailableError, match="issuer key resolution timed out"
        ):
            await asyncio.wait_for(verifier.verify(issue_asymmetric_token(private_key)), timeout=2)
        assert requests == []
    finally:
        verifier._refresh_lock.release()
