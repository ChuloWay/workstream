from __future__ import annotations

import asyncio
from typing import Any

import httpx  # type: ignore[import-not-found]
import pytest  # type: ignore[import-not-found]
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import (  # type: ignore[import-not-found]
    AsyncClient,
    MockTransport,
    Request,
    Response,
)

from app.adapters.auth.flow import (
    FlowAuthVerifier,
)
from app.interfaces.auth import AuthVerificationError, AuthVerificationUnavailableError


from tests.authentication.support import (
    introspection_settings,
    issue_asymmetric_token,
    jwks_transport,
)


async def test_required_introspection_is_separate_and_credential_bound(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    jwks_requests: list[Request] = []
    introspection_requests: list[Request] = []

    def introspection_handler(request: Request) -> Response:
        introspection_requests.append(request)
        return Response(
            200,
            json={
                "active": True,
                "iss": "https://issuer.example.test",
                "sub": "opaque-subject-1",
                "aud": "workstream",
                "jti": "token-id-1",
            },
        )

    verifier = FlowAuthVerifier(
        introspection_settings(),
        jwks_transport=jwks_transport(jwk, jwks_requests),
        introspection_transport=MockTransport(introspection_handler),
    )
    bearer = issue_asymmetric_token(private_key)

    result = await verifier.verify(bearer)

    assert result.token.token_id == "token-id-1"
    assert len(jwks_requests) == 1
    assert jwks_requests[0].method == "GET"
    assert jwks_requests[0].headers.get("authorization") is None
    assert jwks_requests[0].content == b""
    assert bearer.encode() not in jwks_requests[0].content
    assert len(introspection_requests) == 1
    assert introspection_requests[0].method == "POST"
    assert introspection_requests[0].url.host == "introspection.example.test"
    assert introspection_requests[0].headers["authorization"].startswith("Basic ")
    assert bearer.encode() in introspection_requests[0].content


async def test_required_introspection_does_not_follow_redirect(rsa_signing_material):
    private_key, jwk = rsa_signing_material
    bearer = issue_asymmetric_token(private_key)
    redirect_requests: list[Request] = []

    def introspection_redirect(request: Request) -> Response:
        redirect_requests.append(request)
        return Response(302, headers={"location": "https://attacker.test/collect"})

    redirecting = FlowAuthVerifier(
        introspection_settings(),
        jwks_transport=jwks_transport(jwk),
        introspection_transport=MockTransport(introspection_redirect),
    )
    with pytest.raises(AuthVerificationUnavailableError):
        await redirecting.verify(bearer)
    assert len(redirect_requests) == 1
    assert redirect_requests[0].url.host == "introspection.example.test"
    assert bearer.encode() in redirect_requests[0].content
    assert all(request.url.host != "attacker.test" for request in redirect_requests)


async def test_jwks_and_introspection_use_distinct_owned_client_factories(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    clients: dict[str, list[AsyncClient]] = {"jwks": [], "introspection": []}

    def factory(name: str, transport: MockTransport):
        def build_client(**kwargs: Any) -> AsyncClient:
            client = AsyncClient(transport=transport, **kwargs)
            clients[name].append(client)
            return client

        return build_client

    introspection_transport = MockTransport(
        lambda request: Response(
            200,
            json={
                "active": True,
                "iss": "https://issuer.example.test",
                "sub": "opaque-subject-1",
                "aud": "workstream",
                "jti": "token-id-1",
            },
        )
    )
    verifier = FlowAuthVerifier(
        introspection_settings(),
        jwks_client_factory=factory("jwks", jwks_transport(jwk)),
        introspection_client_factory=factory("introspection", introspection_transport),
    )

    await verifier.verify(issue_asymmetric_token(private_key))

    assert len(clients["jwks"]) == 1
    assert len(clients["introspection"]) == 1
    assert clients["jwks"][0] is not clients["introspection"][0]
    assert clients["jwks"][0].is_closed
    assert clients["introspection"][0].is_closed


@pytest.mark.parametrize(
    "response_override",
    [
        {"active": False},
        {"iss": "https://other.example.test"},
        {"sub": "other-subject"},
        {"aud": "other-audience"},
        {"jti": "other-token-id"},
    ],
)
async def test_required_introspection_fails_closed_on_inactive_or_mismatch(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    response_override: dict[str, Any],
) -> None:
    private_key, jwk = rsa_signing_material
    response = {
        "active": True,
        "iss": "https://issuer.example.test",
        "sub": "opaque-subject-1",
        "aud": "workstream",
        "jti": "token-id-1",
    }
    response.update(response_override)
    verifier = FlowAuthVerifier(
        introspection_settings(),
        jwks_transport=jwks_transport(jwk),
        introspection_transport=MockTransport(lambda request: Response(200, json=response)),
    )

    with pytest.raises(AuthVerificationError):
        await verifier.verify(issue_asymmetric_token(private_key))


@pytest.mark.parametrize("missing_field", ["iss", "sub", "aud", "jti"])
async def test_required_introspection_rejects_missing_identity_fields(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    missing_field: str,
) -> None:
    private_key, jwk = rsa_signing_material
    response = {
        "active": True,
        "iss": "https://issuer.example.test",
        "sub": "opaque-subject-1",
        "aud": "workstream",
        "jti": "token-id-1",
    }
    response.pop(missing_field)
    verifier = FlowAuthVerifier(
        introspection_settings(),
        jwks_transport=jwks_transport(jwk),
        introspection_transport=MockTransport(lambda request: Response(200, json=response)),
    )

    with pytest.raises(AuthVerificationError):
        await verifier.verify(issue_asymmetric_token(private_key))


@pytest.mark.parametrize(
    "response",
    [
        Response(200, content=b"not-json-secret-response"),
        Response(200, content=b"x" * 300),
        Response(503, content=b"issuer-secret-response"),
    ],
)
async def test_introspection_response_failures_are_redacted(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
    response: Response,
) -> None:
    private_key, jwk = rsa_signing_material
    bearer = issue_asymmetric_token(private_key)
    verifier = FlowAuthVerifier(
        introspection_settings(token_introspection_max_response_bytes=256),
        jwks_transport=jwks_transport(jwk),
        introspection_transport=MockTransport(lambda request: response),
    )

    with pytest.raises(AuthVerificationUnavailableError) as exc_info:
        await verifier.verify(bearer)

    error = exc_info.value
    assert error.__cause__ is None
    assert error.__context__ is None
    serialized_error = repr(vars(error)) + repr(error.args)
    for forbidden in (
        bearer,
        "client-secret",
        "not-json-secret-response",
        "issuer-secret-response",
    ):
        assert forbidden not in serialized_error


async def test_introspection_transport_error_drops_credential_bearing_exception(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material
    bearer = issue_asymmetric_token(private_key)

    def fail_with_request(request: Request) -> Response:
        raise httpx.ReadTimeout("transport-secret", request=request)

    verifier = FlowAuthVerifier(
        introspection_settings(),
        jwks_transport=jwks_transport(jwk),
        introspection_transport=MockTransport(fail_with_request),
    )

    with pytest.raises(AuthVerificationUnavailableError) as exc_info:
        await verifier.verify(bearer)

    error = exc_info.value
    assert error.__cause__ is None
    assert error.__context__ is None
    assert bearer not in repr(vars(error))
    assert "client-secret" not in repr(vars(error))


async def test_introspection_total_timeout_fails_closed(
    rsa_signing_material: tuple[rsa.RSAPrivateKey, dict[str, Any]],
) -> None:
    private_key, jwk = rsa_signing_material

    async def slow_introspection(request: Request) -> Response:
        await asyncio.sleep(0.6)
        return Response(200, json={"active": True})

    verifier = FlowAuthVerifier(
        introspection_settings(token_introspection_total_timeout_seconds=0.5),
        jwks_transport=jwks_transport(jwk),
        introspection_transport=MockTransport(slow_introspection),
    )

    with pytest.raises(AuthVerificationUnavailableError):
        await verifier.verify(issue_asymmetric_token(private_key))
