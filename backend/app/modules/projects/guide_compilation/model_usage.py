"""PROJECTS-owned currentness for shared setup model-use operations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.model_usage.api import ModelCallUnavailable, SetupModelUsageSlotKey
from app.modules.projects.guide_compilation.models import ProjectGuideCompilationAttempt


class SetupModelUsageCurrent:
    """Lock the exact compilation attempt before any shared MODEL-USAGE lock."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def require_setup_current(self, key: SetupModelUsageSlotKey) -> None:
        key = SetupModelUsageSlotKey.model_validate(key)
        attempt_id = await self._session.scalar(
            select(ProjectGuideCompilationAttempt.id)
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
        if attempt_id is None:
            raise ModelCallUnavailable("setup_model_owner_unavailable")


__all__ = ("SetupModelUsageCurrent",)
