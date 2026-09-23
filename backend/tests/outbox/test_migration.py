"""Forward-only custody migration preserves data or refuses unprovable attempts."""

import asyncio
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import asyncpg
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.outbox.service import OutboxService
from project_create_fixtures import seed_historical_project
from tests.test_outbox import _event

pytestmark = pytest.mark.postgres_schema_contract
REVISION = "0027_outbox_delivery_custody"
PREDECESSOR = "0026_outbox_dispatch_identity"


def config():
    return Config(Path(__file__).resolve().parents[2] / "alembic.ini")


async def seed(url, state):
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    project = uuid4()
    event = _event(project)
    try:
        async with factory() as session, session.begin():
            await seed_historical_project(
                session,
                project_id=str(project),
                name="Migration outbox",
                slug=f"outbox-{project}",
                status="active",
            )
            await OutboxService(session).append(event)
        connection = await asyncpg.connect(url.replace("+asyncpg", ""))
        try:
            if state not in ("pending", "unattempted_cancelled"):
                await connection.execute(
                    "update outbox_events set delivery_state='claimed',attempt_count=1,claim_generation=1,"
                    "next_attempt_at=null,claim_owner='worker',claimed_at=statement_timestamp(),"
                    "last_attempt_at=statement_timestamp(),claim_expires_at=statement_timestamp()+interval '30 seconds' "
                    "where event_id=$1",
                    event.event_id,
                )
            if state == "unattempted_cancelled":
                await connection.execute(
                    "update outbox_events set delivery_state='cancelled',next_attempt_at=null,"
                    "finalized_at=statement_timestamp() where event_id=$1",
                    event.event_id,
                )
            elif state not in ("pending", "claimed"):
                await connection.execute(
                    "update outbox_events set delivery_state=$2::text,claim_owner=null,claimed_at=null,claim_expires_at=null,"
                    "next_attempt_at=case when $2::text='retryable' then statement_timestamp()+interval '1 second' else null end,"
                    "last_error_code='RETRY_REQUESTED',"
                    "finalized_at=case when $2::text='retryable' then null else statement_timestamp() end where event_id=$1",
                    event.event_id,
                    state,
                )
        finally:
            await connection.close()
    finally:
        await engine.dispose()


async def snapshot(url):
    connection = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        return {
            "revision": await connection.fetchval("select version_num from alembic_version"),
            "events": await connection.fetchval(
                "select jsonb_agg(to_jsonb(e) order by event_id)::text from outbox_events e"
            ),
            "attempt_table": await connection.fetchval(
                "select to_regclass('public.outbox_delivery_attempts')::text"
            ),
            "functions": await connection.fetchval(
                "select count(*) from pg_proc where proname='outbox_delivery_outcome_valid'"
            ),
        }
    finally:
        await connection.close()


@pytest.mark.parametrize("state", ["pending", "unattempted_cancelled"])
def test_unattempted_events_preserved_without_fabricated_attempts(
    isolated_database_env, migration_lock, migration_schema_at, state
):
    with migration_lock():
        migration_schema_at(PREDECESSOR)
        asyncio.run(seed(isolated_database_env, state))
        before = asyncio.run(snapshot(isolated_database_env))
        assert before["revision"] == PREDECESSOR and before["attempt_table"] is None
        command.upgrade(config(), REVISION)
        after = asyncio.run(snapshot(isolated_database_env))
        assert after["events"] == before["events"]
        assert (
            after["revision"] == REVISION and after["attempt_table"] == "outbox_delivery_attempts"
        )

        async def count():
            connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
            try:
                return await connection.fetchval("select count(*) from outbox_delivery_attempts")
            finally:
                await connection.close()

        assert asyncio.run(count()) == 0
        command.upgrade(config(), "head")
        assert asyncio.run(snapshot(isolated_database_env)) == after


@pytest.mark.parametrize(
    "state", ["claimed", "retryable", "acknowledged", "dead_letter", "cancelled"]
)
def test_attempted_events_refuse_unprovable_migration(
    isolated_database_env, migration_lock, migration_schema_at, state
):
    with migration_lock():
        migration_schema_at(PREDECESSOR)
        asyncio.run(seed(isolated_database_env, state))
        before = asyncio.run(snapshot(isolated_database_env))
        assert before["revision"] == PREDECESSOR and before["attempt_table"] is None
        with pytest.raises(Exception, match="outbox attempts require provable delivery custody"):
            command.upgrade(config(), REVISION)
        assert asyncio.run(snapshot(isolated_database_env)) == before
