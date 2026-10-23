"""MODEL-USAGE-owned setup output custody for the shared ART pipeline."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.model_usage.api import (
    ModelProfileSelector,
    ModelCallUnavailable,
    SetupModelOutputReservation,
    SetupModelOutputSelector,
    SetupModelOutputSlot,
    SetupModelUsageOwnerPort,
)
from app.modules.model_usage.repository import (
    ModelCallRepository,
    require_model_call_transaction,
)


class SetupModelOutputReservations:
    """Requests require current PROJECTS custody; responses retain paid effects."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        owner: SetupModelUsageOwnerPort,
    ) -> None:
        self._repo = ModelCallRepository(session)
        self._owner = owner
        self._session = session

    async def resolve(
        self, selector: SetupModelOutputSelector
    ) -> SetupModelOutputReservation:
        """Resolve one exact setup role without MODEL-to-PROJECTS lock backedges."""
        require_model_call_transaction(self._session)
        selector = SetupModelOutputSelector.model_validate(selector)
        key = selector.slot_key
        if selector.role == "model_request":
            owner_profile = await self._owner.require_setup_current(key)
            if owner_profile.selector != ModelProfileSelector(
                profile_id=key.profile_id,
                profile_version=key.profile_version,
                profile_digest=key.profile_digest,
            ):
                raise ModelCallUnavailable("setup_model_output_owner_unavailable")

        await self._repo.lock_setup_envelope_scope(key)
        envelope = await self._repo.setup_envelope(key, lock=True)
        await self._repo.lock_setup_slot_scope(key)
        slot = await self._repo.setup_slot(key, lock=True)
        effect = await self._repo.attempt(selector.model_call_attempt_id, lock=True)
        profile = await self._repo.profile_exact(
            key.profile_id, key.profile_version, key.profile_digest
        )
        if (
            envelope is None
            or slot is None
            or effect is None
            or profile is None
            or slot.envelope_id != envelope.id
            or slot.id != str(selector.model_call_slot_id)
            or effect.setup_slot_id != slot.id
            or profile.project_id != str(key.project_id)
            or (
                slot.compilation_attempt_id,
                slot.project_id,
                slot.guide_id,
                slot.source_snapshot_id,
                slot.setup_run_id,
                slot.setup_generation,
                slot.runtime_configuration_hash,
                slot.profile_id,
                slot.profile_version,
                slot.profile_digest,
                slot.phase,
                slot.call_index,
            )
            != (
                str(key.compilation_attempt_id),
                str(key.project_id),
                str(key.guide_id),
                str(key.source_snapshot_id),
                str(key.setup_run_id),
                key.setup_generation,
                key.runtime_configuration_hash,
                str(key.profile_id),
                key.profile_version,
                key.profile_digest,
                key.phase,
                key.call_index,
            )
        ):
            raise ModelCallUnavailable("setup_model_output_unavailable")
        if selector.role == "model_request":
            if effect.request_sha256 != selector.content_sha256:
                raise ModelCallUnavailable("setup_model_output_request_conflict")
            maximum = profile.maximum_request_bytes
        else:
            if effect.state not in {"dispatching", "uncertain", "completed", "known_failed"}:
                raise ModelCallUnavailable("setup_model_output_effect_unavailable")
            if effect.response_content_sha256 not in {None, selector.content_sha256}:
                raise ModelCallUnavailable("setup_model_output_response_conflict")
            maximum = profile.maximum_response_bytes
        return SetupModelOutputReservation(
            selector=selector,
            slot=SetupModelOutputSlot(key=selector.role, maximum_bytes=maximum),
        )


__all__ = ("SetupModelOutputReservations",)
