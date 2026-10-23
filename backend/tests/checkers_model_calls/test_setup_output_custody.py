"""Owner-order and exact-identity proofs for setup ART reservations."""

from types import SimpleNamespace

import pytest

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.model_usage.api import (
    ModelCallUnavailable,
    ModelProfileSelector,
    SetupModelOutputSelector,
    SetupModelOwnerProfile,
    SetupModelUsageSlotKey,
)
from app.modules.model_usage.output_custody import SetupModelOutputReservations


def sha(label: str) -> str:
    return canonical_json_hash({"label": label})


def selector(*, role: str = "model_request") -> SetupModelOutputSelector:
    key = SetupModelUsageSlotKey(
        compilation_attempt_id=new_record_id(),
        project_id=new_record_id(),
        guide_id=new_record_id(),
        source_snapshot_id=new_record_id(),
        setup_run_id=new_record_id(),
        setup_generation=2,
        runtime_configuration_hash=sha("runtime"),
        profile_id=new_record_id(),
        profile_version=3,
        profile_digest=sha("profile"),
        phase="review",
        call_index=1,
    )
    return SetupModelOutputSelector(
        slot_key=key,
        model_call_slot_id=new_record_id(),
        model_call_attempt_id=new_record_id(),
        role=role,
        content_sha256=sha(role),
    )


class Owner:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    async def require_setup_current(self, key):
        self.calls.append("owner")
        return SetupModelOwnerProfile(
            selector=ModelProfileSelector(
                profile_id=key.profile_id,
                profile_version=key.profile_version,
                profile_digest=key.profile_digest,
            ),
            provider="provider",
            api="api.v1",
            model_snapshot="model-2026-10-01",
        )


class Repository:
    def __init__(self, selected: SetupModelOutputSelector, calls: list[str]) -> None:
        self.selected = selected
        self.calls = calls
        key = selected.slot_key
        self.envelope = SimpleNamespace(id=str(new_record_id()))
        self.slot = SimpleNamespace(
            id=str(selected.model_call_slot_id),
            envelope_id=self.envelope.id,
            compilation_attempt_id=str(key.compilation_attempt_id),
            project_id=str(key.project_id),
            guide_id=str(key.guide_id),
            source_snapshot_id=str(key.source_snapshot_id),
            setup_run_id=str(key.setup_run_id),
            setup_generation=key.setup_generation,
            runtime_configuration_hash=key.runtime_configuration_hash,
            profile_id=str(key.profile_id),
            profile_version=key.profile_version,
            profile_digest=key.profile_digest,
            phase=key.phase,
            call_index=key.call_index,
        )
        self.effect = SimpleNamespace(
            setup_slot_id=self.slot.id,
            request_sha256=selected.content_sha256,
            response_content_sha256=None,
            state="dispatching",
        )
        self.profile = SimpleNamespace(
            project_id=str(key.project_id),
            maximum_request_bytes=10_000,
            maximum_response_bytes=20_000,
        )

    async def lock_setup_envelope_scope(self, _key):
        self.calls.append("envelope-scope")

    async def setup_envelope(self, _key, *, lock):
        assert lock
        self.calls.append("envelope")
        return self.envelope

    async def lock_setup_slot_scope(self, _key):
        self.calls.append("slot-scope")

    async def setup_slot(self, _key, *, lock):
        assert lock
        self.calls.append("slot")
        return self.slot

    async def attempt(self, _attempt_id, *, lock):
        assert lock
        self.calls.append("effect")
        return self.effect

    async def profile_exact(self, *_identity):
        self.calls.append("profile")
        return self.profile


async def resolve(monkeypatch, selected):
    calls: list[str] = []
    service = SetupModelOutputReservations(object(), owner=Owner(calls))
    service._repo = Repository(selected, calls)
    monkeypatch.setattr(
        "app.modules.model_usage.output_custody.require_model_call_transaction",
        lambda _session: None,
    )
    return await service.resolve(selected), calls


@pytest.mark.asyncio
async def test_request_checks_owner_before_canonical_model_lock_order(monkeypatch) -> None:
    reservation, calls = await resolve(monkeypatch, selector())

    assert reservation.slot.maximum_bytes == 10_000
    assert calls == [
        "owner",
        "envelope-scope",
        "envelope",
        "slot-scope",
        "slot",
        "effect",
        "profile",
    ]


@pytest.mark.asyncio
async def test_response_uses_retained_effect_without_projects_callback(monkeypatch) -> None:
    selected = selector(role="model_response")
    reservation, calls = await resolve(monkeypatch, selected)

    assert reservation.slot.maximum_bytes == 20_000
    assert "owner" not in calls
    assert calls[:2] == ["envelope-scope", "envelope"]


@pytest.mark.asyncio
async def test_substituted_response_hash_is_rejected(monkeypatch) -> None:
    selected = selector(role="model_response")
    calls: list[str] = []
    service = SetupModelOutputReservations(object(), owner=Owner(calls))
    repository = Repository(selected, calls)
    repository.effect.response_content_sha256 = sha("different-response")
    service._repo = repository
    monkeypatch.setattr(
        "app.modules.model_usage.output_custody.require_model_call_transaction",
        lambda _session: None,
    )

    with pytest.raises(ModelCallUnavailable, match="response_conflict"):
        await service.resolve(selected)
