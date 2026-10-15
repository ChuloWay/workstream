"""Periodic, bounded discovery of retained routed failures missing expiry coverage."""

from uuid import UUID

from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.tasks import scan_task_revision_sources
from app.db.session import get_database_url
from app.workers.async_runner import run_async_task
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)
SCAN_TASK = "workstream.tasks.scan_retained_revisions"


@celery_app.task(name=SCAN_TASK)
def scan_retained_revisions(after=None):
    """Walk one stable page; the next page advances even past stale sources."""
    try:
        cursor = UUID(after) if after is not None else None
        if cursor is not None and str(cursor) != after:
            raise ValueError("noncanonical cursor")
    except (TypeError, ValueError):
        return {"status": "scan_rejected"}
    try:
        recovered, next_after = run_async_task(lambda: _scan_page(cursor))
    except Exception:
        logger.warning("retained revision discovery unavailable")
        raise
    if next_after is not None:
        scan_retained_revisions.apply_async(args=(str(next_after),))
    return {"recovered": recovered, "next_after": str(next_after) if next_after else None}


async def _scan_page(after):
    """Recover one bounded page and always dispose the per-task DB pool."""
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        return await scan_task_revision_sources(factory, after)
    finally:
        await engine.dispose()
