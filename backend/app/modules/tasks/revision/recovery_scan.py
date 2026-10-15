"""Page current TASK revision sources and recover missing expiry coverage."""

import logging
from uuid import UUID

from app.modules.tasks.repository import TaskRepository

logger = logging.getLogger(__name__)


async def scan_current_revision_sources(factory, recovery_factory, after: UUID | None):
    """Bound one page; each source gets its own atomic recovery transaction."""
    async with factory() as session:
        page = await TaskRepository(session).list_current_revision_sources(
            after=after, limit=100,
        )
    recovered = 0
    for manifest_id in page:
        try:
            async with factory() as session, session.begin():
                recovered += bool(await recovery_factory(session).recover(manifest_id))
        except Exception as exc:
            origin = getattr(exc, "orig", None)
            logger.warning(
                "retained revision recovery unavailable for %s: %s sqlstate=%s constraint=%s",
                manifest_id, type(exc).__name__,
                getattr(origin, "sqlstate", None),
                getattr(origin, "constraint_name", None),
            )
    return recovered, page[-1] if len(page) == 100 else None
