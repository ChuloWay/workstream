from __future__ import annotations

from typing import Any

import pytest  # type: ignore[import-not-found]
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import (  # type: ignore[import-not-found]
    MockTransport,
    Request,
    Response,
)

from app.adapters.auth.flow import (
    FlowAuthVerifier,
)
from app.adapters.auth.metrics import InProcessAuthVerifierMetrics
from app.interfaces.auth import AuthVerificationError, AuthVerificationUnavailableError


from tests.authentication.support import (
    rsa_public_jwk,
    production_verifier_settings,
    issue_asymmetric_token,
    jwks_transport,
)


async def test_jwks_cache_hit_avoids_second_network_request(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    requests: list[Request] = []
    metrics = InProcessAuthVerifierMetrics()
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport(jwk, requests),
        metrics=metrics,
    )

    await verifier.verify(issue_asymmetric_token(private_key))
    await verifier.verify(issue_asymmetric_token(private_key, claims={"jti": "token-id-2"}))

    assert len(requests) == 1
    assert any(
        name == "workstream_auth_jwks_cache_total" and ("result", "hit") in labels
        for name, labels in metrics.snapshot()
    )


def test_verifier_metrics_enforce_closed_labels_without_identity_values() -> None:
    metrics = InProcessAuthVerifierMetrics()
    for result in ("success", "invalid", "unsupported_kind", "unavailable"):
        metrics.verification(result)  # type: ignore[arg-type]
    for result in ("hit", "miss", "negative_hit", "expired"):
        metrics.jwks_cache(result)  # type: ignore[arg-type]
    for result in ("success", "failure"):
        metrics.jwks_refresh(result)  # type: ignore[arg-type]
    for mode in ("disabled", "required"):
        for result in ("success", "inactive", "invalid", "unavailable", "skipped"):
            metrics.introspection(mode, result)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="not allowed"):
        metrics.verification("opaque-subject-token-id")  # type: ignore[arg-type]

    snapshot = repr(metrics.snapshot())
    for forbidden in ("opaque-subject", "token-id", "https://", "client-secret", "BEGIN"):
        assert forbidden not in snapshot


async def test_unknown_kid_refreshes_once_then_uses_bounded_negative_cache(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    requests: list[Request] = []
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport(jwk, requests),
    )
    token = issue_asymmetric_token(private_key, kid="unknown-key")

    with pytest.raises(AuthVerificationError, match="unknown"):
        await verifier.verify(token)
    with pytest.raises(AuthVerificationError, match="unknown"):
        await verifier.verify(token)

    assert len(requests) == 1


async def test_rotation_clears_matching_negative_kid() -> None:
    first_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    rotated_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    first_jwk = rsa_public_jwk(first_key, kid="first-key")
    rotated_jwk = rsa_public_jwk(rotated_key, kid="rotated-key")
    clock = [0.0]
    requests: list[Request] = []

    def rotating_jwks(request: Request) -> Response:
        requests.append(request)
        keys = [first_jwk] if len(requests) < 3 else [first_jwk, rotated_jwk]
        return Response(200, json={"keys": keys})

    verifier = FlowAuthVerifier(
        production_verifier_settings(
            token_jwks_cache_ttl_seconds=30,
            token_unknown_kid_cache_ttl_seconds=300,
        ),
        jwks_transport=MockTransport(rotating_jwks),
        monotonic=lambda: clock[0],
    )
    await verifier.verify(issue_asymmetric_token(first_key, kid="first-key"))
    clock[0] = 31.0
    rotated_token = issue_asymmetric_token(rotated_key, kid="rotated-key")
    with pytest.raises(AuthVerificationError, match="unknown"):
        await verifier.verify(rotated_token)
    clock[0] = 62.0
    assert verifier._negative_kids["rotated-key"] > clock[0]
    with pytest.raises(AuthVerificationError, match="unknown"):
        await verifier.verify(issue_asymmetric_token(rotated_key, kid="rotation-trigger"))
    assert "rotated-key" not in verifier._negative_kids

    result = await verifier.verify(rotated_token)

    assert result.token.subject == "opaque-subject-1"
    assert len(requests) == 3


async def test_negative_kid_cache_evicts_oldest_at_capacity(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    verifier = FlowAuthVerifier(
        production_verifier_settings(token_unknown_kid_cache_max_entries=1),
        jwks_transport=jwks_transport(jwk),
        monotonic=lambda: 0.0,
    )
    await verifier.verify(issue_asymmetric_token(private_key))
    for kid in ("unknown-a", "unknown-b"):
        with pytest.raises(AuthVerificationError):
            await verifier.verify(issue_asymmetric_token(private_key, kid=kid))
    assert tuple(verifier._negative_kids) == ("unknown-b",)


async def test_negative_kid_cache_expires_during_verification(rsa_signing_material):
    private_key, jwk = rsa_signing_material
    clock = [0.0]
    requests = []
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport(jwk, requests),
        monotonic=lambda: clock[0],
    )
    valid = issue_asymmetric_token(private_key)
    await verifier.verify(valid)
    with pytest.raises(AuthVerificationError, match="unknown"):
        await verifier.verify(issue_asymmetric_token(private_key, kid="unknown"))
    assert tuple(verifier._negative_kids) == ("unknown",)
    clock[0] = 31.0

    result = await verifier.verify(valid)

    assert result.token.subject == "opaque-subject-1"
    assert not verifier._negative_kids
    assert len(requests) == 1


async def test_expired_jwks_cache_refreshes_during_longer_unknown_kid_cooldown(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    clock = [0.0]
    requests: list[Request] = []

    def outage_after_prime(request: Request) -> Response:
        requests.append(request)
        if len(requests) == 1:
            return Response(200, json={"keys": [jwk]})
        return Response(503)

    verifier = FlowAuthVerifier(
        production_verifier_settings(
            token_jwks_cache_ttl_seconds=30,
            token_unknown_kid_cache_ttl_seconds=300,
        ),
        jwks_transport=MockTransport(outage_after_prime),
        monotonic=lambda: clock[0],
    )
    token = issue_asymmetric_token(private_key)
    await verifier.verify(token)
    clock[0] = 31.0

    with pytest.raises(AuthVerificationUnavailableError):
        await verifier.verify(token)
    clock[0] = 32.0
    with pytest.raises(AuthVerificationUnavailableError, match="cooling down"):
        await verifier.verify(token)

    assert len(requests) == 2


async def test_refresh_failure_cooldown_preserves_valid_cached_key_hits(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    clock = [0.0]
    requests: list[Request] = []

    def outage_after_prime(request: Request) -> Response:
        requests.append(request)
        if len(requests) == 1:
            return Response(200, json={"keys": [jwk]})
        return Response(503)

    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=MockTransport(outage_after_prime),
        monotonic=lambda: clock[0],
    )
    valid_token = issue_asymmetric_token(private_key)
    await verifier.verify(valid_token)
    clock[0] = 31.0
    with pytest.raises(AuthVerificationUnavailableError):
        await verifier.verify(issue_asymmetric_token(private_key, kid="unknown-during-outage"))

    clock[0] = 32.0
    assert (await verifier.verify(valid_token)).token.token_id == "token-id-1"
    with pytest.raises(AuthVerificationUnavailableError, match="cooling down"):
        await verifier.verify(issue_asymmetric_token(private_key, kid="another-unknown"))
    assert len(requests) == 2
