"""The actual predecessor upgrade preserves queued work and refuses invented receipts."""

import asyncio

import asyncpg
import pytest
from alembic import command
from sqlalchemy.exc import IntegrityError

from app.db import session as db_session
from tests.migration_fixtures import _config
from tests.checkers.execution.predecessor_support import predecessor_lease
from tests.checkers.execution.test_material_migration import retained_snapshot
from tests.checkers.execution.support import reserve
from tests.post_submit_materialization_helpers import material_fixture

pytestmark = pytest.mark.postgres_schema_contract


@pytest.mark.parametrize("unprovable_receipt", [False, True])
async def test_actual_upgrade_preserves_or_refuses_without_repair(tmp_path, isolated_database_env, migration_lock, unprovable_receipt):
    with migration_lock():
        await db_session.dispose_engine()
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        try:
            await connection.execute("drop schema public cascade; create schema public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0009_checker_material_lineage")
        async with material_fixture(tmp_path, isolated_database_env, provision_checker=False) as h:
            await reserve(h)
            if unprovable_receipt:
                await predecessor_lease(h)
            before = await retained_snapshot(h.factory)
            if unprovable_receipt:
                with pytest.raises(IntegrityError, match="retained checker authorization receipts are unprovable"):
                    await asyncio.to_thread(command.upgrade, _config(), "head")
                assert await retained_snapshot(h.factory) == before
            else:
                await asyncio.to_thread(command.upgrade, _config(), "head")
                after = await retained_snapshot(h.factory)
                assert after[0] == before[0]
                assert after[1] == "0010_post_submit_authority"
