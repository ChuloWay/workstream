"""Observe real decisions while independently checking their persisted digest."""

import hashlib
import json

import pytest

from app.modules.authorization.kernel import AuthorizationService


@pytest.fixture
def policy_decisions(monkeypatch):
    """Observe the executed decision without replacing authorization or audit writes."""
    captured = {}
    original = AuthorizationService._stage_decision

    async def observe(service, decision, actor_profile_id, resource_context=None):
        await original(service, decision, actor_profile_id, resource_context)
        if decision.action_id is not None and decision.action_id.value.startswith(
            "contribution.policy."
        ):
            payload = {
                "resource_context": resource_context.model_dump(mode="json", exclude_none=True)
            }
            encoded = json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
            ).encode("utf-8")
            captured[str(decision.decision_id)] = (
                decision,
                "sha256:" + hashlib.sha256(encoded).hexdigest(),
            )

    monkeypatch.setattr(AuthorizationService, "_stage_decision", observe)
    return captured
