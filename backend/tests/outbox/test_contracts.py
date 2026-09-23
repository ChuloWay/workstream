"""Closed values, explicit composition and preserved append/live boundaries."""

import ast
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.outbox.api import DeliveryOptions, HandlerOutcome, OutboxClaim
from app.modules.outbox.registry import HandlerRegistry


def _outbox_imports(source):
    """Recognize both Python import forms, independent of local aliases."""
    imports = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return any("outbox" in name.split(".") for name in imports)


@pytest.mark.parametrize(
    "source",
    [
        "import app.modules.outbox.delivery as delivery",
        "from app.modules.outbox.delivery import OutboxDelivery as Owner",
        "from app.modules import outbox",
        "from app.adapters.outbox import outbox_delivery as factory",
        "import app.adapters.outbox as adapter",
    ],
)
def test_composition_guard_detects_import_forms(source):
    assert _outbox_imports(source)
    assert not _outbox_imports("from app.modules.tasks import service as outbox")


def test_append_transaction_and_explicit_delivery_boundaries():
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
            if path == root / "workers/outbox.py":
                imports = [node for node in ast.walk(ast.parse(path.read_text()))
                           if isinstance(node, ast.ImportFrom) and node.module == "app.adapters.outbox"]
                assert len(imports) == 1
                assert [name.name for name in imports[0].names] == ["production_outbox_delivery"]
            else:
                assert not _outbox_imports(path.read_text()), path
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
    async def handler(envelope):
        return HandlerOutcome.ACKNOWLEDGE

    with pytest.raises(ValueError):
        HandlerRegistry([(*key, handler)])


def test_registry_rejects_duplicates_and_has_no_default():
    async def handler(envelope):
        return HandlerOutcome.ACKNOWLEDGE

    with pytest.raises(ValueError):
        HandlerRegistry([("event", 1, handler), ("event", 1, handler)])
    registry = HandlerRegistry([("event", 1, handler)])
    assert registry.keys == (("event", 1),)
    assert registry.get("event", 1) is handler
    assert registry.get("event", 2) is None
    assert HandlerRegistry([]).get("event", 1) is None


@pytest.mark.parametrize("field", ["claimed_at", "claim_expires_at"])
@pytest.mark.parametrize("fault", ["raises", "invalid"])
def test_invalid_timezone_is_sanitized(field, fault):
    class InvalidTimezone(tzinfo):
        def utcoffset(self, dt):
            if fault == "raises":
                raise RuntimeError("private-timezone-marker")
            return timedelta(days=2)

    now = datetime.now(timezone.utc)
    values = dict(
        event_id=uuid4(),
        project_id=uuid4(),
        payload_digest="sha256:" + "a" * 64,
        claim_generation=1,
        claim_owner="test-worker",
        claimed_at=now,
        claim_expires_at=now + timedelta(seconds=5),
    )
    values[field] = now.replace(tzinfo=InvalidTimezone())
    with pytest.raises(ValueError, match="outbox timestamp requires a valid timezone") as caught:
        OutboxClaim(**values)
    assert "private-timezone-marker" not in str(caught.value)
    assert caught.value.__cause__ is caught.value.__context__ is None
    for error in caught.value.errors(include_input=False):
        original = error.get("ctx", {}).get("error")
        assert original.__cause__ is original.__context__ is None


@pytest.mark.parametrize("kind", ["function", "bound_method", "callable_object"])
async def test_registry_accepts_async_handler_forms(kind):
    async def handler(envelope):
        return HandlerOutcome.ACKNOWLEDGE

    class AsyncHandler:
        async def handle(self, envelope):
            return HandlerOutcome.ACKNOWLEDGE

        async def __call__(self, envelope):
            return HandlerOutcome.ACKNOWLEDGE

    instance = AsyncHandler()
    selected = {"function": handler, "bound_method": instance.handle, "callable_object": instance}[
        kind
    ]
    registry = HandlerRegistry([("event", 1, selected)])
    assert registry.get("event", 1) is selected
    assert await registry.get("event", 1)(None) is HandlerOutcome.ACKNOWLEDGE


@pytest.mark.parametrize(
    "kind", ["sync_function", "sync_callable", "awaitable_factory", "class", "noncallable"]
)
def test_registry_rejects_sync_handlers_without_calling_them(kind):
    called = []

    async def result():
        return HandlerOutcome.ACKNOWLEDGE

    def sync_function(envelope):
        called.append(envelope)
        return HandlerOutcome.ACKNOWLEDGE

    def awaitable_factory(envelope):
        called.append(envelope)
        return result()

    class SyncHandler:
        __call__ = staticmethod(sync_function)

    class AsyncHandler:
        async def __call__(self, envelope):
            return HandlerOutcome.ACKNOWLEDGE

    handler = {
        "sync_function": sync_function,
        "sync_callable": SyncHandler(),
        "awaitable_factory": awaitable_factory,
        "class": AsyncHandler,
        "noncallable": None,
    }[kind]
    with pytest.raises(ValueError, match="outbox registration is invalid"):
        HandlerRegistry([("event", 1, handler)])
    assert called == []


@pytest.mark.parametrize("fault", ["type", "deny", "action", "permission", "decision_id"])
def test_delivery_rejects_malformed_authorization_decision(fault):
    """Controlled port-result proof only; no claim of live authority or SQL custody."""
    from dataclasses import replace
    from uuid import uuid4
    from app.modules.authorization.api.decisions import AuthorizationDecision, DecisionOutcome
    from app.modules.outbox.api import DeliveryUnavailable
    from app.modules.outbox.delivery import _allow

    valid = AuthorizationDecision(uuid4(), "outbox.dispatch", "outbox.dispatch", DecisionOutcome.ALLOW)
    assert _allow(valid) == str(valid.decision_id)
    invalid = {
        "type": object(),
        "deny": replace(valid, outcome=DecisionOutcome.DENY, denial_code="denied"),
        "action": replace(valid, action_id="task.claim"),
        "permission": replace(valid, permission_id="task.claim"),
        "decision_id": replace(valid, decision_id="not-a-uuid"),
    }[fault]
    with pytest.raises(DeliveryUnavailable):
        _allow(invalid)
