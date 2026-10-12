"""Real predecessor upgrade proof for the false-only second-review invariant."""

import asyncio
from pathlib import Path
import runpy

from alembic import command
from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import session as db_session
from tests.conftest import _drop_test_database_schema
from tests.historical_submission_fixtures import restore_archived_snapshot
from tests.migration_fixtures import _config, current_schema_revision

pytestmark = pytest.mark.postgres_schema_contract


def _upgrade(connection) -> None:
    migration = runpy.run_path(
        str(
            Path(__file__).resolve().parents[3]
            / "alembic/versions/0024_require_second_review_false.py"
        )
    )
    with Operations.context(MigrationContext.configure(connection)):
        migration["upgrade"]()


async def _snapshot(connection) -> dict[str, object]:
    return {
        "policies": list(
            await connection.scalars(
                text(
                    "select to_jsonb(p) from public.review_policies p "
                    "order by policy_generation,id"
                )
            )
        ),
        "selectors": list(
            await connection.scalars(
                text(
                    "select jsonb_build_object("
                    "'id',id,'policy_id',selected_review_policy_id,"
                    "'generation',selected_review_policy_generation,"
                    "'hash',selected_review_policy_hash) "
                    "from public.project_guides order by id"
                )
            )
        ),
        "version": await connection.scalar(
            text("select version_num from public.alembic_version")
        ),
    }


async def test_upgrade_refuses_retained_true_without_changing_its_lineage(
    isolated_database_env,
    migration_lock,
) -> None:
    await db_session.dispose_engine()
    with migration_lock():
        await _drop_test_database_schema(isolated_database_env)
        await asyncio.to_thread(
            command.upgrade, _config(), "0023_remove_task_payment_policy"
        )
        await restore_archived_snapshot(
            isolated_database_env,
            snapshot_name="0023_review_policy_second_review_true",
        )
        async with db_session.get_engine().connect() as connection, connection.begin():
            before = await _snapshot(connection)
            assert before["policies"][0]["requires_second_review"] is True
            with pytest.raises(
                IntegrityError,
                match="retained requires_second_review=true policy",
            ):
                async with connection.begin_nested():
                    await connection.run_sync(_upgrade)
            assert await _snapshot(connection) == before


async def test_upgrade_installs_false_guard_without_changing_hash_or_lineage(
    isolated_database_env,
    migration_lock,
) -> None:
    await db_session.dispose_engine()
    with migration_lock():
        await _drop_test_database_schema(isolated_database_env)
        await asyncio.to_thread(
            command.upgrade, _config(), "0023_remove_task_payment_policy"
        )
        await restore_archived_snapshot(
            isolated_database_env,
            snapshot_name="0023_review_policy_second_review_false",
        )
        async with db_session.get_engine().connect() as connection:
            before = await _snapshot(connection)
            await connection.rollback()
        await db_session.dispose_engine()
        await asyncio.to_thread(command.upgrade, _config(), "head")
        async with db_session.get_engine().connect() as connection:
            after = await _snapshot(connection)
            constraint = await connection.scalar(
                text(
                    "select pg_get_constraintdef(oid) from pg_constraint "
                    "where conrelid='public.review_policies'::regclass "
                    "and conname="
                    "'ck_review_policies_review_policy_second_review_disabled'"
                )
            )
        assert before["policies"] == after["policies"]
        assert before["selectors"] == after["selectors"]
        assert before["version"] == "0023_remove_task_payment_policy"
        assert after["version"] == current_schema_revision()
        assert constraint == "CHECK ((NOT requires_second_review))"
