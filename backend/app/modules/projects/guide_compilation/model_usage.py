"""PROJECTS-owned currentness for shared setup model-use operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.modules.model_usage.api import (
    ModelCallUnavailable,
    ModelProfileSelector,
    SetupModelOwnerProfile,
    SetupModelUsageSlotKey,
)
from app.modules.projects.guide_compilation.models import ProjectGuideCompilationAttempt


class SetupModelUsageCurrent:
    """Lock the exact compilation attempt before any shared MODEL-USAGE lock."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def require_setup_current(self, key: SetupModelUsageSlotKey) -> SetupModelOwnerProfile:
        key = SetupModelUsageSlotKey.model_validate(key)
        attempt = await self._session.scalar(
            select(ProjectGuideCompilationAttempt)
            .where(
                ProjectGuideCompilationAttempt.id == key.compilation_attempt_id,
                ProjectGuideCompilationAttempt.project_id == str(key.project_id),
                ProjectGuideCompilationAttempt.guide_id == str(key.guide_id),
                ProjectGuideCompilationAttempt.source_snapshot_id == str(key.source_snapshot_id),
                ProjectGuideCompilationAttempt.setup_run_id == str(key.setup_run_id),
                ProjectGuideCompilationAttempt.setup_generation == key.setup_generation,
                ProjectGuideCompilationAttempt.runtime_configuration_hash
                == key.runtime_configuration_hash,
                ProjectGuideCompilationAttempt.status == "compilation_reserved",
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if attempt is None:
            raise ModelCallUnavailable("setup_model_owner_unavailable")
        try:
            configuration = ProjectGuideRuntimeConfiguration.model_validate(
                attempt.runtime_configuration
            )
            selector = ModelProfileSelector(
                profile_id=configuration.model_profile_id,
                profile_version=configuration.model_profile_version,
                profile_digest=configuration.model_profile_digest,
            )
        except ValueError as exc:
            raise ModelCallUnavailable("setup_model_owner_unavailable") from exc
        if selector != ModelProfileSelector(
            profile_id=key.profile_id,
            profile_version=key.profile_version,
            profile_digest=key.profile_digest,
        ):
            raise ModelCallUnavailable("setup_model_owner_unavailable")
        return SetupModelOwnerProfile(
            selector=selector,
            provider=configuration.model_provider,
            api=configuration.model_api,
            model_snapshot=configuration.model,
        )


__all__ = ("SetupModelUsageCurrent",)
