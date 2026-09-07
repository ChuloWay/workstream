from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest  # type: ignore[import-not-found]
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.auth import clear_auth_verifier_cache
from app.core.config import get_settings


from tests.authentication.support import rsa_public_jwk


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    clear_auth_verifier_cache()
    yield
    get_settings.cache_clear()
    clear_auth_verifier_cache()


@pytest.fixture(scope="module")
def rsa_signing_material() -> tuple[rsa.RSAPrivateKey, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    return private_key, rsa_public_jwk(private_key, kid="issuer-key-1")


@pytest.fixture
def auth_database_env(
    monkeypatch: pytest.MonkeyPatch,
    clean_postgres_database: str,
) -> Iterator[str]:
    """Run auth route persistence tests against a clean migrated schema."""
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    monkeypatch.setenv(
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET",
        "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
    )
    get_settings.cache_clear()
    try:
        yield clean_postgres_database
    finally:
        get_settings.cache_clear()
