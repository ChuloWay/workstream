"""Authority-neutral exact reads of immutable project model profiles."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.model_usage.api import (
    ModelCallUnavailable,
    ModelGenerationSettings,
    ModelPricing,
    ModelProfileSelector,
    ProjectModelProfile,
    ProjectModelProfileSpec,
)
from app.modules.model_usage.models import ModelUsageProfile


def stored_model_profile(row: ModelUsageProfile) -> ProjectModelProfile:
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
        provider=row.provider,
        api=row.api,
        model_snapshot=row.model_snapshot,
        settings=ModelGenerationSettings.model_validate(row.generation_settings),
        maximum_request_bytes=row.maximum_request_bytes,
        maximum_output_bytes=row.maximum_output_bytes,
        maximum_response_bytes=row.maximum_response_bytes,
        maximum_input_tokens=row.maximum_input_tokens,
        maximum_output_tokens=row.maximum_output_tokens,
        maximum_calls=row.maximum_calls,
        maximum_total_request_bytes=row.maximum_total_request_bytes,
        maximum_total_response_bytes=row.maximum_total_response_bytes,
        maximum_total_input_tokens=row.maximum_total_input_tokens,
        maximum_total_output_tokens=row.maximum_total_output_tokens,
        allowed_tools=tuple(row.allowed_tools),
        maximum_tool_calls=row.maximum_tool_calls,
        maximum_tool_output_bytes=row.maximum_tool_output_bytes,
        deadline_ms=row.deadline_ms,
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
    ) -> ProjectModelProfile:
        """Require the complete selector plus exact project custody."""
        self._require_root_transaction()
        try:
            selector = ModelProfileSelector.model_validate(selector)
        except ValueError as exc:
            raise ModelCallUnavailable("model_profile_unavailable") from exc
        row = await self._session.scalar(
            select(ModelUsageProfile).where(
                ModelUsageProfile.id == str(selector.profile_id),
                ModelUsageProfile.profile_version == selector.profile_version,
                ModelUsageProfile.profile_digest == selector.profile_digest,
                ModelUsageProfile.project_id == str(project_id),
            )
        )
        if row is None:
            raise ModelCallUnavailable("model_profile_unavailable")
        return stored_model_profile(row)

    async def read_latest_matching(
        self,
        *,
        project_id: UUID,
        provider: str,
        api: str,
        model_snapshot: str,
    ) -> ProjectModelProfile:
        """Select only the newest immutable version for this project and identity."""
        self._require_root_transaction()
        row = await self._session.scalar(
            select(ModelUsageProfile)
            .where(
                ModelUsageProfile.project_id == str(project_id),
                ModelUsageProfile.provider == provider,
                ModelUsageProfile.api == api,
                ModelUsageProfile.model_snapshot == model_snapshot,
            )
            .order_by(ModelUsageProfile.profile_version.desc())
            .limit(1)
        )
        if row is None:
            raise ModelCallUnavailable("model_profile_unavailable")
        return stored_model_profile(row)


__all__ = ("ModelProfileReader", "stored_model_profile")
