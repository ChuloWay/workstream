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
