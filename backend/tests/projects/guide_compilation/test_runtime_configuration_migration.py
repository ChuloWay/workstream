"""Retained attempts survive the additive configuration migration unchanged."""

import asyncio
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import insert, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.modules.projects.guide_compilation.models import ProjectGuideCompilationAttempt
from .helpers import context, identity, seed_database

pytestmark = pytest.mark.postgres_schema_contract


async def test_upgrade_preserves_unconfigured_attempt_and_refuses_dispatch(isolated_database_env, migration_lock):
    def migrate(target, *, downgrade=False):
        with migration_lock():
            (command.downgrade if downgrade else command.upgrade)(Config("alembic.ini"), target)
    await asyncio.to_thread(migrate, "0013_compilation_request_origin", downgrade=True)
    values = await seed_database(isolated_database_env)
    attempt_identity = identity(context(values))
    row = attempt_identity.model_dump(mode="json") | {
        "id": uuid4(), "provider_idempotency_key": attempt_identity.provider_idempotency_key(),
        "status": "compilation_reserved",
    }
    engine = create_async_engine(isolated_database_env)
    try:
        async with engine.begin() as connection:
            await connection.execute(insert(ProjectGuideCompilationAttempt).values(**row))
            before = await connection.scalar(text("select to_jsonb(a) from project_guide_compilation_attempts a"))
        await asyncio.to_thread(migrate, "head")
        async with engine.connect() as connection:
            after = await connection.scalar(text("select to_jsonb(a) from project_guide_compilation_attempts a"))
        assert after == before | {"runtime_configuration": None, "runtime_configuration_hash": None}
        async with engine.begin() as connection:
            with pytest.raises(DBAPIError, match="compilation runtime configuration unavailable") as error:
                await connection.execute(text("update project_guide_compilation_attempts set status='compilation_provider_uncertain',provider_uncertain_at=now() where id=:id"), {"id": row["id"]})
            assert error.value.orig.sqlstate == "23514"
        async with engine.connect() as connection:
            assert await connection.scalar(text("select to_jsonb(a) from project_guide_compilation_attempts a")) == after
    finally:
        await engine.dispose()
