from __future__ import annotations

from typing import Any

import jwt
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
from app.interfaces.auth import AuthVerificationUnavailableError


from tests.authentication.support import (
    rsa_public_jwk,
    production_verifier_settings,
    issue_asymmetric_token,
    jwks_transport,
)


async def test_jwks_unavailability_is_typed_and_redacted() -> None:
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=MockTransport(lambda request: Response(503, text="secret issuer body")),
    )
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    bearer = issue_asymmetric_token(private_key)

    with pytest.raises(AuthVerificationUnavailableError) as exc_info:
        await verifier.verify(bearer)

    assert bearer not in str(exc_info.value)
    assert "secret issuer body" not in str(exc_info.value)


@pytest.mark.parametrize("kind", ["empty", "duplicate-valid-key"])
async def test_invalid_jwks_documents_fail_closed(rsa_signing_material, kind) -> None:
    private_key, jwk = rsa_signing_material
    jwks_payload = {"keys": [] if kind == "empty" else [jwk, dict(jwk)]}
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=MockTransport(lambda request: Response(200, json=jwks_payload)),
    )

    message = "key set is invalid" if kind == "empty" else "key identifier is invalid"
    with pytest.raises(AuthVerificationUnavailableError, match=message):
        await verifier.verify(issue_asymmetric_token(private_key))


async def test_weak_rsa_signing_key_is_rejected() -> None:
    weak_key = rsa.generate_private_key(public_exponent=65_537, key_size=1_024)
    weak_jwk = rsa_public_jwk(weak_key, kid="weak-key")
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport(weak_jwk),
    )

    with pytest.warns(jwt.InsecureKeyLengthWarning):
        token = issue_asymmetric_token(weak_key, kid="weak-key")
    with pytest.raises(AuthVerificationUnavailableError, match="invalid"):
        await verifier.verify(token)


@pytest.mark.parametrize(
    "jwk_override",
    [
        {"kty": "EC"},
        {"alg": "RS512"},
        {"key_ops": ["sign"]},
        {"use": "enc"},
    ],
)
async def test_incompatible_jwk_metadata_is_rejected(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    jwk_override: dict[str, Any],
) -> None:
    private_key, jwk = rsa_signing_material
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=jwks_transport({**jwk, **jwk_override}),
    )

    with pytest.raises(AuthVerificationUnavailableError):
        await verifier.verify(issue_asymmetric_token(private_key))


@pytest.mark.parametrize("kind", ["malformed-json", "too-many-keys"])
async def test_malformed_and_excessive_jwks_fail_closed(rsa_signing_material, kind) -> None:
    private_key, jwk = rsa_signing_material
    response = (
        Response(200, content=b"not-json")
        if kind == "malformed-json"
        else Response(200, json={"keys": [jwk, {**jwk, "kid": "second"}]})
    )
    verifier = FlowAuthVerifier(
        production_verifier_settings(token_jwks_max_keys=1),
        jwks_transport=MockTransport(lambda request: response),
    )
    message = "response is invalid" if kind == "malformed-json" else "key set exceeds"
    with pytest.raises(AuthVerificationUnavailableError, match=message):
        await verifier.verify(issue_asymmetric_token(private_key))


async def test_jwks_redirect_does_not_receive_or_forward_bearer(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, _ = rsa_signing_material
    requests: list[Request] = []

    def redirect(request: Request) -> Response:
        requests.append(request)
        return Response(302, headers={"location": "https://attacker.test/jwks"})

    bearer = issue_asymmetric_token(private_key)
    verifier = FlowAuthVerifier(
        production_verifier_settings(),
        jwks_transport=MockTransport(redirect),
    )

    with pytest.raises(AuthVerificationUnavailableError):
        await verifier.verify(bearer)

    assert len(requests) == 1
    assert requests[0].url.host == "issuer.example.test"
    assert requests[0].headers.get("authorization") is None
    assert requests[0].content == b""
    assert all(request.url.host != "attacker.test" for request in requests)


async def test_oversized_jwks_response_fails_before_json_buffering() -> None:
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    verifier = FlowAuthVerifier(
        production_verifier_settings(token_jwks_max_response_bytes=1_024),
        jwks_transport=MockTransport(
            lambda request: Response(200, content=b"{" + b'"padding":"' + b"x" * 2_000 + b'"}')
        ),
    )

    with pytest.raises(AuthVerificationUnavailableError, match="exceeds"):
        await verifier.verify(issue_asymmetric_token(private_key))
