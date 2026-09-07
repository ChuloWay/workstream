"""Independent configuration and claim-collection contracts."""

import pytest
from httpx import AsyncClient, MockTransport, Response

from app.adapters.auth.flow import FlowAuthVerifier, _normalize_audience, _normalize_scopes
from app.interfaces.auth import AuthVerificationError
from tests.authentication.support import production_verifier_settings


def test_audience_collection_preserves_exact_values():
    assert _normalize_audience(["workstream-api", "secondary-api"]) == (
        "workstream-api",
        "secondary-api",
    )


def test_scope_collection_preserves_exact_values():
    assert _normalize_scopes(["workstream:human", "profile:read"]) == frozenset(
        {"workstream:human", "profile:read"}
    )


@pytest.mark.parametrize("audience", [["audience"] * 17, "a" * 257], ids=["too-many", "too-long"])
def test_audience_collection_rejects_excess(audience):
    with pytest.raises(AuthVerificationError, match="audience"):
        _normalize_audience(audience)


@pytest.mark.parametrize(
    "scopes",
    [["embedded whitespace"], [f"scope-{i}" for i in range(65)]],
    ids=["embedded-whitespace", "too-many"],
)
def test_scope_collection_rejects_malformed_values(scopes):
    with pytest.raises(AuthVerificationError, match="scope"):
        _normalize_scopes(scopes)


@pytest.mark.parametrize("endpoint", ["jwks", "introspection"])
def test_client_factory_and_transport_are_mutually_exclusive(endpoint):
    with pytest.raises(
        ValueError, match="JWKS transport" if endpoint == "jwks" else "introspection transport"
    ):
        FlowAuthVerifier(
            production_verifier_settings(),
            **{
                f"{endpoint}_transport": MockTransport(lambda request: Response(500)),
                f"{endpoint}_client_factory": AsyncClient,
            },
        )


@pytest.mark.parametrize(
    ("key", "algorithm", "message"),
    [
        ({}, "RS256", "modulus"),
        ({"crv": "P-384"}, "ES256", "curve"),
        ({"crv": "X25519"}, "EdDSA", "curve"),
    ],
    ids=["missing-rsa-modulus", "wrong-ec-curve", "wrong-eddsa-curve"],
)
def test_signing_key_strength_rejects_incompatible_parameters(key, algorithm, message):
    with pytest.raises(ValueError, match=message):
        FlowAuthVerifier._validate_jwk_strength(key, algorithm=algorithm)
