"""Closed values, explicit composition and preserved append/live boundaries."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.outbox.api import DeliveryOptions, OutboxClaim
from app.modules.outbox.registry import HandlerRegistry


def test_append_transaction_and_hidden_delivery_boundaries():
    import ast

    root = Path(__file__).resolve().parents[2] / "app"
    for name in ("service.py", "repository.py"):
        tree = ast.parse((root / "modules/outbox" / name).read_text())
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("commit", "begin")
            for node in ast.walk(tree)
        )
    for directory in (root / "workers", root / "api/routes"):
        for path in directory.rglob("*.py"):
            tree = ast.parse(path.read_text())
            assert not any(
                isinstance(node, ast.ImportFrom) and node.module and "outbox" in node.module
                for node in ast.walk(tree)
            )
    tree = ast.parse((root / "modules/outbox/api.py").read_text())
    assert not any(
        isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("app.modules.authorization")
        for node in ast.walk(tree)
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"lease_seconds": 0},
        {"lease_seconds": True},
        {"handler_timeout_seconds": 300},
        {"max_attempts": 101},
        {"retry_base_seconds": 301},
        {"retry_cap_seconds": 0},
        {"extra": 1},
    ],
)
def test_invalid_delivery_options_reject(changes):
    with pytest.raises(ValueError):
        DeliveryOptions(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"event_id": "invalid"},
        {"project_id": "invalid"},
        {"payload_digest": "invalid"},
        {"claim_generation": True},
        {"claim_generation": 0},
        {"claim_owner": "unsafe owner"},
        {"claimed_at": datetime(2020, 1, 1)},
        {"claim_expires_at": datetime(2000, 1, 1, tzinfo=timezone.utc)},
    ],
)
def test_invalid_claims_reject(changes):
    now = datetime.now(timezone.utc)
    values = dict(
        event_id=uuid4(),
        project_id=uuid4(),
        payload_digest="sha256:" + "a" * 64,
        claim_generation=1,
        claim_owner="worker",
        claimed_at=now,
        claim_expires_at=now + timedelta(seconds=5),
    )
    with pytest.raises(ValueError):
        OutboxClaim(**{**values, **changes})


@pytest.mark.parametrize("key", [("bad key", 1), ("valid", 0), ("valid", True)])
def test_registry_rejects_invalid_exact_keys(key):
    with pytest.raises(ValueError):
        HandlerRegistry([(*key, lambda envelope: None)])


def test_registry_rejects_duplicates_and_has_no_default():
    def handler(envelope):
        return None

    with pytest.raises(ValueError):
        HandlerRegistry([("event", 1, handler), ("event", 1, handler)])
    registry = HandlerRegistry([("event", 1, handler)])
    assert registry.keys == (("event", 1),)
    assert registry.get("event", 1) is handler
    assert registry.get("event", 2) is None
    assert HandlerRegistry([]).get("event", 1) is None
