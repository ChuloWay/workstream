"""Async SQLAlchemy engine and session management."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.db import models  # noqa: F401 — register the complete runtime FK graph

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_database_url() -> str:
    """Return the configured database URL.

    Returns:
        Async SQLAlchemy database URL.

    Raises:
        RuntimeError: If ``WORKSTREAM_DATABASE_URL`` is not configured.
    """
    database_url = get_settings().database_url
    if not database_url:
        raise RuntimeError("WORKSTREAM_DATABASE_URL must be set before database access")
    return database_url


def get_engine() -> AsyncEngine:
    """Return the process-wide async SQLAlchemy engine.

    Returns:
        Lazily initialized async engine.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async session factory.

    Returns:
        Lazily initialized async session factory.
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield a database session for a FastAPI request.

    Yields:
        Async SQLAlchemy session.
    """
    async with get_session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    """Dispose cached database resources and reset lazy singletons."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
