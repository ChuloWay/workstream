"""Cleanup for test-owned AUTH rows in real PostgreSQL transactions."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def restore_actor_lifecycle_triggers(session: AsyncSession) -> None:
    """Validate deferred FK events before DDL, without splitting the transaction."""
    await session.execute(text("set constraints all immediate"))
    await session.execute(text("alter table actor_identity_links enable trigger user"))
    await session.execute(text("alter table actor_profiles enable trigger user"))
