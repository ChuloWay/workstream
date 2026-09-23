"""Actual predecessor rows prove refusal without fictional authority backfill."""

import asyncio
import json
from uuid import UUID

from alembic import command
import asyncpg
import pytest

from app.modules.outbox.api import OutboxClaim, FinalizationCause, DeliveryOptions
from app.modules.outbox.delivery import _outcome, _encode
from app.core.hashing import canonical_json_hash
from tests.outbox.test_migration import config, seed

pytestmark = pytest.mark.postgres_schema_contract
PREDECESSOR = "0027_outbox_delivery_custody"
REVISION = "0028_outbox_dispatch_authority"


async def predecessor_attempt(url, state):
    await seed(url, "pending")
    connection = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        async with connection.transaction():
            row = await connection.fetchrow("""
                update outbox_events set delivery_state='claimed',claim_generation=1,attempt_count=1,
                  next_attempt_at=null,claim_owner='migration-worker',claimed_at=statement_timestamp(),
                  last_attempt_at=statement_timestamp(),claim_expires_at=statement_timestamp()+interval '1 hour'
                returning *
            """)
            await connection.execute(
                """
                insert into outbox_delivery_attempts(event_id,claim_generation,project_id,payload_digest,
                  claim_owner,claimed_at,claim_expires_at,stage)
                values($1,1,$2,$3,$4,$5,$6,'claimed')
            """,
                row["event_id"],
                row["project_id"],
                row["payload_digest"],
                row["claim_owner"],
                row["claimed_at"],
                row["claim_expires_at"],
            )
        if state == "claimed":
            return
        async with connection.transaction():
            invoked = await connection.fetchval("""
                update outbox_delivery_attempts set stage='invoked',invoked_at=clock_timestamp()
                returning invoked_at
            """)
        if state == "invoked":
            return
        now = await connection.fetchval("select clock_timestamp()")
        claim = OutboxClaim(
            **{
                key: UUID(str(row[key])) if key in {"event_id", "project_id"} else row[key]
                for key in OutboxClaim.model_fields
            }
        )
        outcome = _outcome(claim, invoked, FinalizationCause.ACKNOWLEDGE, now, DeliveryOptions())
        async with connection.transaction():
            await connection.execute(
                """
                update outbox_delivery_attempts set stage='completed',outcome_json=$1,outcome_digest=$2
            """,
                _encode(outcome),
                canonical_json_hash(outcome),
            )
            await connection.execute(
                """
                update outbox_events set delivery_state='acknowledged',claim_owner=null,
                  claimed_at=null,claim_expires_at=null,finalized_at=$1
            """,
                now,
            )
    finally:
        await connection.close()


async def snapshot(url):
    connection = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        rows = {}
        for table in (
            "outbox_events",
            "outbox_delivery_attempts",
            "audit_events",
            "actor_profiles",
            "actor_identity_links",
        ):
            values = await connection.fetch(f"select to_jsonb(t)::text as value from {table} t")
            rows[table] = sorted(row["value"] for row in values)
        return {
            "revision": await connection.fetchval("select version_num from alembic_version"),
            "rows": rows,
            "columns": [
                tuple(row)
                for row in await connection.fetch(
                    "select table_name,column_name,is_nullable,data_type from information_schema.columns "
                    "where table_schema='public' order by table_name,ordinal_position"
                )
            ],
            "constraints": [
                tuple(row)
                for row in await connection.fetch(
                    "select conrelid::regclass::text,conname,pg_get_constraintdef(oid) from pg_constraint "
                    "where connamespace='public'::regnamespace order by conrelid::regclass::text,conname"
                )
            ],
            "functions": [
                tuple(row)
                for row in await connection.fetch(
                    "select proname,prosrc from pg_proc where pronamespace='public'::regnamespace order by proname,prosrc"
                )
            ],
        }
    finally:
        await connection.close()


@pytest.mark.parametrize("state", ["pending", "unattempted_cancelled"])
def test_dispatch_activation_preserves_unattempted_rows(
    isolated_database_env, migration_lock, migration_schema_at, state
):
    with migration_lock():
        migration_schema_at(PREDECESSOR)
        asyncio.run(seed(isolated_database_env, state))
        before = asyncio.run(snapshot(isolated_database_env))
        assert before["revision"] == PREDECESSOR
        command.upgrade(config(), REVISION)
        after = asyncio.run(snapshot(isolated_database_env))
        assert after["revision"] == REVISION and after["rows"] == before["rows"]
        assert after["rows"]["outbox_delivery_attempts"] == []
        command.upgrade(config(), "head")
        assert asyncio.run(snapshot(isolated_database_env)) == after


@pytest.mark.parametrize("state", ["claimed", "invoked", "completed"])
def test_dispatch_activation_refuses_unauthorized_attempts(
    isolated_database_env, migration_lock, migration_schema_at, state
):
    with migration_lock():
        migration_schema_at(PREDECESSOR)
        asyncio.run(predecessor_attempt(isolated_database_env, state))
        before = asyncio.run(snapshot(isolated_database_env))
        assert before["revision"] == PREDECESSOR
        attempts = before["rows"]["outbox_delivery_attempts"]
        assert len(attempts) == 1 and json.loads(attempts[0])["stage"] == state
        assert "claim_decision_event_id" not in json.loads(attempts[0])
        with pytest.raises(
            Exception, match="outbox attempts without phase authority prevent activation"
        ):
            command.upgrade(config(), REVISION)
        assert asyncio.run(snapshot(isolated_database_env)) == before


def test_activation_blocks_service_relabel_until_new_guard_commits(
    isolated_database_env, migration_lock, migration_schema_at
):
    """A concurrent writer cannot use the old guard during actual Alembic upgrade."""
    from threading import Event
    from uuid import uuid4

    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    entered, release = Event(), Event()

    def pause_before_guard(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("CREATE OR REPLACE FUNCTION PUBLIC.GUARD_ACTOR_PROFILE_HISTORY"):
            entered.set()
            assert release.wait(30), "migration barrier was not released"

    async def exercise():
        url = isolated_database_env.replace("+asyncpg", "")
        writer = await asyncpg.connect(url)
        observer = await asyncpg.connect(url)
        actor_id = str(uuid4())
        upgrade = mutation = None
        try:
            async with writer.transaction():
                await writer.execute("""
                    insert into actor_profiles(id,actor_kind,status,provisioning_method,service_identity,created_by)
                    values($1,'service','active','manual_service_provisioning','workstream.project.setup',$1)
                """, actor_id)
                await writer.execute("""
                    insert into actor_identity_links(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by)
                    values($1,$2,'configured-provider',$3,'service','active',$2)
                """, str(uuid4()), actor_id, str(uuid4()))
            upgrade = asyncio.create_task(asyncio.to_thread(command.upgrade, config(), REVISION))
            assert await asyncio.to_thread(entered.wait, 30), "upgrade did not reach guard replacement"
            pid = await writer.fetchval("select pg_backend_pid()")
            mutation = asyncio.create_task(writer.execute(
                "update actor_profiles set service_identity='workstream.outbox.dispatcher' where id=$1", actor_id
            ))
            blocked = False
            for _ in range(100):
                blocked = await observer.fetchval("""
                    select exists(select 1 from pg_locks where relation='actor_profiles'::regclass
                        and mode='AccessExclusiveLock' and granted
                        and pid=any(pg_blocking_pids($1)))
                """, pid)
                if blocked or mutation.done():
                    break
                await asyncio.sleep(0.02)
            assert blocked, "service relabel must wait behind migration's actor lock"
            release.set()
            await asyncio.wait_for(upgrade, 30)
            with pytest.raises(asyncpg.ObjectNotInPrerequisiteStateError,
                               match="actor profile identity is immutable"):
                await asyncio.wait_for(mutation, 30)
            assert await writer.fetchval(
                "select service_identity from actor_profiles where id=$1", actor_id
            ) == "workstream.project.setup"
            assert await writer.fetchval("select count(*) from outbox_delivery_attempts") == 0
            assert await writer.fetchval("select count(*) from audit_events") == 0
        finally:
            release.set()
            pending = [task for task in (upgrade, mutation) if task is not None]
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            await writer.close()
            await observer.close()

    with migration_lock():
        migration_schema_at(PREDECESSOR)
        event.listen(Engine, "before_cursor_execute", pause_before_guard)
        try:
            asyncio.run(exercise())
        finally:
            release.set()
            event.remove(Engine, "before_cursor_execute", pause_before_guard)
