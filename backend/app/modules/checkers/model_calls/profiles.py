"""Authority-neutral exact reads of immutable project model profiles."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.checkers.api.model_calls import (
    ModelCallUnavailable,
    ModelGenerationSettings,
    ModelPricing,
    ModelProfileSelector,
    ProjectModelProfile,
    ProjectModelProfileSpec,
)
from app.modules.checkers.model_calls.models import CheckerModelProfile


def stored_model_profile(row: CheckerModelProfile) -> ProjectModelProfile:
    """Decode one immutable row through the strict public profile contract."""
    pricing = ModelPricing(
        pricing_policy_id=UUID(row.pricing_policy_id),
        pricing_policy_version=row.pricing_policy_version,
        pricing_policy_digest=row.pricing_policy_digest,
        uncached_input_nanodollars_per_token=row.uncached_input_rate,
        cached_input_nanodollars_per_token=row.cached_input_rate,
        output_nanodollars_per_token=row.output_rate,
    )
    spec = ProjectModelProfileSpec(
        project_id=UUID(row.project_id),
        profile_version=row.profile_version,
        registry_entry_id=UUID(row.registry_entry_id),
        registry_entry_digest=row.registry_entry_digest,
        provider=row.provider,
        api=row.api,
        model_snapshot=row.model_snapshot,
        settings=ModelGenerationSettings.model_validate(row.generation_settings),
        maximum_request_bytes=row.maximum_request_bytes,
        maximum_output_bytes=row.maximum_output_bytes,
        maximum_response_bytes=row.maximum_response_bytes,
        maximum_input_tokens=row.maximum_input_tokens,
        maximum_output_tokens=row.maximum_output_tokens,
        deadline_ms=row.deadline_ms,
        call_slots=row.call_slots,
        pricing=pricing,
    )
    return ProjectModelProfile(
        profile_id=UUID(row.id),
        operation_id=UUID(row.operation_id),
        actor_profile_id=UUID(row.actor_profile_id),
        spec=spec,
        profile_digest=row.profile_digest,
        authorization_evidence_id=UUID(row.authorization_evidence_id),
        created_at=row.created_at,
    )


class ModelProfileReader:
    """Read exact immutable metadata without profile-mutation authority."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind exact profile reads to the caller-owned database session."""
        self._session = session

    def _require_root_transaction(self) -> None:
        """Reject reads outside an active root transaction or inside a savepoint."""
        transaction = self._session.sync_session.get_transaction()
        if (
            transaction is None
            or not transaction.is_active
            or self._session.in_nested_transaction()
        ):
            raise ModelCallUnavailable("model_profile_unavailable")

    async def read_exact(
        self,
        selector: ModelProfileSelector,
        *,
        project_id: UUID,
        registry_entry_id: UUID,
        registry_entry_digest: str,
    ) -> ProjectModelProfile:
        """Require the complete selector plus exact project and registry custody."""
        self._require_root_transaction()
        try:
            selector = ModelProfileSelector.model_validate(selector)
        except ValueError as exc:
            raise ModelCallUnavailable("model_profile_unavailable") from exc
        row = await self._session.scalar(
            select(CheckerModelProfile).where(
                CheckerModelProfile.id == str(selector.profile_id),
                CheckerModelProfile.profile_version == selector.profile_version,
                CheckerModelProfile.profile_digest == selector.profile_digest,
                CheckerModelProfile.project_id == str(project_id),
                CheckerModelProfile.registry_entry_id == str(registry_entry_id),
                CheckerModelProfile.registry_entry_digest == registry_entry_digest,
            )
        )
        if row is None:
            raise ModelCallUnavailable("model_profile_unavailable")
        return stored_model_profile(row)


__all__ = ("ModelProfileReader", "stored_model_profile")
