"""Real forward migration preserves history and closes service vocabulary."""

import asyncio
import re
from uuid import uuid4

from alembic import command
import asyncpg
import pytest

from app.modules.actors.api import SERVICE_IDENTITY_VALUES
from tests.migrations.test_outbox_dispatch_identity import config, seed, snapshot
from tests.migration_fixtures import run_guarded_revision_downgrade

pytestmark = pytest.mark.postgres_schema_contract
REVISION = "0029_assignment_authority"
IDENTITY = "workstream.task.assignment_reconciler"


def test_reconciler_migration_preserves_records(isolated_database_env, migration_lock, migration_schema_at):
    with migration_lock():
        migration_schema_at("0028_outbox_dispatch_authority")
        asyncio.run(seed(isolated_database_env, "workstream.outbox.dispatcher"))
        before = asyncio.run(snapshot(isolated_database_env))
        with pytest.raises(asyncpg.CheckViolationError) as rejected:
            asyncio.run(seed(isolated_database_env, IDENTITY))
        assert rejected.value.constraint_name == "ck_actor_profiles_kind_service_identity"
        command.upgrade(config(), REVISION)
        after = asyncio.run(snapshot(isolated_database_env))
        assert (after["actors"], after["links"]) == (before["actors"], before["links"])
        removed = set(before["constraints"]) - set(after["constraints"])
        added = set(after["constraints"]) - set(before["constraints"])
        assert {name for name, _ in removed} == {name for name, _ in added} == {
            "ck_actor_profiles_kind_service_identity", "ck_audit_events_authority_registries",
            "ck_audit_events_authorization_action_evidence",
        }
        identity_constraint = next(value for name, value in added if name == "ck_actor_profiles_kind_service_identity")
        assert set(re.findall(r"workstream\.[a-z_]+\.[a-z_]+", identity_constraint)) == set(SERVICE_IDENTITY_VALUES)
        asyncio.run(seed(isolated_database_env, IDENTITY))
        with pytest.raises(asyncpg.CheckViolationError) as unknown:
            asyncio.run(seed(isolated_database_env, "workstream.task.foreign"))
        assert unknown.value.constraint_name == "ck_actor_profiles_kind_service_identity"
        with pytest.raises(asyncpg.UniqueViolationError):
            asyncio.run(seed(isolated_database_env, IDENTITY))
        stable = asyncio.run(snapshot(isolated_database_env))
        command.upgrade(config(), "head")
        head = asyncio.run(snapshot(isolated_database_env))
        assert (head["actors"], head["links"]) == (stable["actors"], stable["links"])
        command.upgrade(config(), "head")
        assert asyncio.run(snapshot(isolated_database_env)) == head
        with pytest.raises(RuntimeError, match="cannot be downgraded"):
            asyncio.run(run_guarded_revision_downgrade(isolated_database_env, REVISION))
        assert asyncio.run(snapshot(isolated_database_env)) == head


async def retained_release(url):
    connection = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        event_id = str(uuid4())
        await connection.execute(
            "insert into audit_events(id,entity_type,entity_id,event_type,actor_id,reason,actor_roles,claim_snapshot,is_dev_auth,auth_source,event_payload,external_subject,external_issuer) "
            "values($1,'task',$2,'TaskAssignmentAuthorityRevoked',$3,'lifecycle_state_changed','[]','{}',false,'local_lifecycle','{}','workstream:lifecycle-participant','workstream:internal')",
            event_id, str(uuid4()), str(uuid4()),
        )
        return await connection.fetchval("select to_jsonb(a)::text from audit_events a where id=$1", event_id)
    finally:
        await connection.close()


def test_reconciler_migration_refuses_unproven_release(isolated_database_env, migration_lock, migration_schema_at):
    with migration_lock():
        migration_schema_at("0028_outbox_dispatch_authority")
        retained = asyncio.run(retained_release(isolated_database_env))
        before = asyncio.run(snapshot(isolated_database_env))
        with pytest.raises(Exception, match="without exact service authority"):
            command.upgrade(config(), REVISION)
        assert asyncio.run(snapshot(isolated_database_env)) == before

        async def verify():
            connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
            try:
                assert await connection.fetchval("select to_jsonb(a)::text from audit_events a where event_type='TaskAssignmentAuthorityRevoked'") == retained
            finally:
                await connection.close()

        asyncio.run(verify())


def test_reconciler_migration_serializes_provisioning(isolated_database_env, migration_lock, migration_schema_at):
    with migration_lock():
        migration_schema_at("0028_outbox_dispatch_authority")

        async def race():
            url = isolated_database_env.replace("+asyncpg", "")
            writer = await asyncpg.connect(url)
            observer = await asyncpg.connect(url)
            transaction = writer.transaction()
            await transaction.start()
            actor_id = str(uuid4())
            await writer.execute(
                "insert into actor_profiles(id,actor_kind,status,provisioning_method,service_identity,created_by) "
                "values($1,'service','active','manual_service_provisioning','workstream.artifact.verifier',$1)", actor_id,
            )
            await writer.execute(
                "insert into actor_identity_links(id,actor_profile_id,issuer,subject,subject_kind,status,linked_by) "
                "values($1,$2,'workstream.internal','workstream.artifact.verifier','service','active','workstream:system:bootstrap')",
                str(uuid4()), actor_id,
            )
            upgrade = asyncio.create_task(asyncio.to_thread(command.upgrade, config(), REVISION))
            try:
                for _ in range(200):
                    waiting = await observer.fetchval(
                        "select exists(select 1 from pg_locks l join pg_stat_activity a on a.pid=l.pid "
                        "where a.datname=current_database() and l.relation='actor_profiles'::regclass "
                        "and l.mode='AccessExclusiveLock' and not l.granted)"
                    )
                    if waiting:
                        break
                    await asyncio.sleep(.02)
                assert waiting and not upgrade.done()
            finally:
                await transaction.commit()
                await asyncio.wait_for(upgrade, 20)
                await writer.close()
                await observer.close()
            connection = await asyncpg.connect(url)
            try:
                assert await connection.fetchval("select service_identity from actor_profiles where id=$1", actor_id) == "workstream.artifact.verifier"
            finally:
                await connection.close()
            await seed(isolated_database_env, IDENTITY)

        asyncio.run(race())
