# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalOperand=false
from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

from httpx import ASGITransport, AsyncClient
import pytest

from app.core.config import get_settings
from app.main import create_app

from tests.actors.support import RATE_SECRET, set_dev_actor


@pytest.fixture
def actor_database_env(
    monkeypatch: pytest.MonkeyPatch,
    clean_postgres_database: str,
) -> Iterator[str]:
    """Run canonical actor tests against an isolated current schema."""
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    monkeypatch.setenv("WORKSTREAM_API_RATE_LIMIT_KEY_SECRET", RATE_SECRET)
    set_dev_actor(monkeypatch, roles="worker", subject="actor-registry-contributor")
    get_settings.cache_clear()
    try:
        yield clean_postgres_database
    finally:
        get_settings.cache_clear()


@pytest.fixture
async def actor_client(actor_database_env: str) -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield client
