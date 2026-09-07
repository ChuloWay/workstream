"""Exact identity and signed SQL-key delegation, not PostgreSQL lock proof."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.hashing import canonical_json_hash
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.execution_fence_fixtures import fence_case as fence_case, open_fence


async def test_fence_rejects_non_async_engine(fence_case: SimpleNamespace) -> None:
    """An invalid engine cannot reach connection acquisition or work."""
    fence_case.service._session.bind = object()

    with pytest.raises(RuntimeError, match="requires an async database engine"):
        async with open_fence(fence_case):
            pytest.fail("invalid engine entered protected work")

    fence_case.engine.connect.assert_not_called()
    assert fence_case.events == []


async def test_fence_hashes_exact_identity(
    fence_case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Actor, action and operation identities stay in the owning hash domain."""
    hashing = Mock(wraps=canonical_json_hash)
    monkeypatch.setattr(fence_case.module, "canonical_json_hash", hashing)

    async with open_fence(fence_case):
        pass

    hashing.assert_called_once_with({
        "domain": fence_case.domain,
        "actor_profile_id": "00000000-0000-0000-0000-000000000001",
        "action_id": (
            "project.guide_sufficiency.run"
            if fence_case.domain == "workstream.guide_sufficiency.execution_fence.v1"
            else "project.submission_artifact_policy.derive"
        ),
        "key": "00000000-0000-0000-0000-000000000002",
    })


@pytest.mark.parametrize("prefix,expected", [
    ("0000000000000000", 0),
    ("7fffffffffffffff", 9223372036854775807),
    ("8000000000000000", -9223372036854775808),
    ("ffffffffffffffff", -1),
])
async def test_fence_delegates_exact_signed_key(
    fence_case: SimpleNamespace, monkeypatch: pytest.MonkeyPatch,
    prefix: str, expected: int,
) -> None:
    """Every signed-boundary key reaches acquisition and release unchanged."""
    monkeypatch.setattr(
        fence_case.module, "canonical_json_hash", Mock(return_value="sha256:" + prefix + "a" * 48),
    )

    async with open_fence(fence_case):
        pass

    fence_case.engine.connect.assert_called_once_with()
    fence_case.connection.__aenter__.assert_awaited_once_with()
    fence_case.connection.scalar.assert_awaited_once()
    query, parameters = fence_case.connection.scalar.await_args.args
    assert str(query) == "select pg_try_advisory_lock(:lock_key)"
    assert parameters == {"lock_key": expected}
    fence_case.connection.execute.assert_awaited_once()
    query, parameters = fence_case.connection.execute.await_args.args
    assert str(query) == "select pg_advisory_unlock(:lock_key)"
    assert parameters == {"lock_key": expected}
