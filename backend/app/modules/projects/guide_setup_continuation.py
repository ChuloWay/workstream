"""Project-owned continuation from a closed verified-guide capability."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.projects.models import ProjectSetupRun
from app.modules.projects.setup_queue import (
    retryable_compilation_dispatch_predicate,
    dispatch_project_guide_compilation_after_commit,
)

PrepareGeneration = Callable[..., Awaitable[bool]]


async def retryable_source_snapshot_ids(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    page_size: int,
) -> list[UUID]:
    """Return a bounded project-owned continuation candidate set."""
    async with session_factory() as session:
        values = (
            await session.scalars(
                select(ProjectSetupRun.source_snapshot_id)
                .where(
                    retryable_compilation_dispatch_predicate(),
                )
                .order_by(ProjectSetupRun.created_at, ProjectSetupRun.id)
                .limit(page_size)
            )
        ).all()
    return [UUID(value) for value in values]


async def retryable_setup_run_for_snapshot(
    session_factory: async_sessionmaker[AsyncSession],
    source_snapshot_id: UUID,
) -> ProjectSetupRun | None:
    """Return the latest retryable setup run for one declared source snapshot."""
    async with session_factory() as session:
        run = await session.scalar(
            select(ProjectSetupRun)
            .where(
                ProjectSetupRun.source_snapshot_id == str(source_snapshot_id),
                retryable_compilation_dispatch_predicate(),
            )
            .order_by(ProjectSetupRun.setup_generation.desc())
            .limit(1)
        )
        if run is None:
            return None
        latest_generation = await session.scalar(
            select(func.max(ProjectSetupRun.setup_generation)).where(
                ProjectSetupRun.guide_id == run.guide_id
            )
        )
        return run if latest_generation == run.setup_generation else None


async def continue_setup_after_verified_guide_item(
    verification_job_id: UUID,
    source_snapshot_id: UUID,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    prepare_generation: PrepareGeneration,
) -> None:
    """Prepare and dispatch one latest retryable setup through a closed ART port."""
    run = await retryable_setup_run_for_snapshot(session_factory, source_snapshot_id)
    if run is None:
        return
    ready = await prepare_generation(
        project_id=UUID(run.project_id),
        guide_id=UUID(run.guide_id),
        source_snapshot_id=UUID(run.source_snapshot_id),
        setup_run_id=UUID(run.id),
        setup_generation=run.setup_generation,
    )
    if not ready:
        return
    async with session_factory() as session:
        await dispatch_project_guide_compilation_after_commit(
            session,
            project_id=run.project_id,
            guide_id=run.guide_id,
            source_snapshot_id=run.source_snapshot_id,
            setup_run_id=run.id,
            setup_generation=run.setup_generation,
            verification_job_id=str(verification_job_id),
        )
