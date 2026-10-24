"""The catalogue action extends only the public audit CHECK under hostile search_path."""

import asyncio

from alembic import command
import asyncpg
import pytest

from app.core.identifiers import new_record_id
from app.db import session as db_session
from tests.conftest import _drop_test_database_schema
from tests.migration_fixtures import _config


pytestmark = pytest.mark.postgres_schema_contract
NAME = "ck_audit_events_authorization_action_evidence"


async def _prepare_shadow(url):
    connection = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        role, database = await connection.fetchrow("select current_user, current_database()")
        assert role.startswith("workstream_role_") and database.startswith("workstream_test_")
        await connection.execute("create schema shadow")
        await connection.execute(
            "create table shadow.audit_events (like public.audit_events including constraints)"
        )
        before_public = await connection.fetchval(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='public.audit_events'::regclass and conname=$1",
            NAME,
        )
        before_shadow = await connection.fetchval(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='shadow.audit_events'::regclass and conname=$1",
            NAME,
        )
        assert before_public == before_shadow
        await connection.execute(
            f'alter role "{role}" in database "{database}" set search_path=shadow,public'
        )
        return before_public, before_shadow
    finally:
        await connection.close()


async def _definitions(url):
    connection = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        return tuple(
            [
                await connection.fetchval(
                    "select pg_get_constraintdef(oid) from pg_constraint "
                    "where conrelid=$1::regclass and conname=$2",
                    table,
                    NAME,
                )
                for table in ("public.audit_events", "shadow.audit_events")
            ]
        )
    finally:
        await connection.close()


async def _restore_role_search_path(url):
    connection = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        role, database = await connection.fetchrow("select current_user, current_database()")
        assert role.startswith("workstream_role_") and database.startswith("workstream_test_")
        await connection.execute(f'alter role "{role}" in database "{database}" reset search_path')
    finally:
        await connection.close()


async def _assert_closed_pair(url):
    connection = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        valid_id = str(new_record_id())
        await connection.execute(
            """insert into public.audit_events(
            id,entity_type,entity_id,event_type,actor_id,actor_roles,claim_snapshot,
            auth_source,is_dev_auth,event_payload,event_domain,event_version,actor_ref_kind,
            request_id,correlation_id,permission_id,action_id,reason,project_id,resource_type,
            resource_id,after_facts,matched_grant_id,target_ref_kind,target_ref_id,denial_code)
            values($1,'authorization_decision',$1,'SensitiveAuthorizationDenied',$2,'[]','{}',
            'local_authority',false,'{}','authority',1,'actor_profile',$3,$4,
            'project.read','project.catalogue.list','authorization_evaluation',
            null,null,null,jsonb_build_object('allowed',false,'resource_context_digest',
            'sha256:'||repeat('a',64)),null,null,null,'permission_not_granted')""",
            valid_id,
            str(new_record_id()),
            str(new_record_id()),
            str(new_record_id()),
        )
        crossed_id = str(new_record_id())
        with pytest.raises(asyncpg.CheckViolationError) as error:
            await connection.execute(
                """insert into public.audit_events select
                (jsonb_populate_record(null::public.audit_events,
                to_jsonb(value) || jsonb_build_object(
                  'id',$2::text,'entity_id',$2::text,
                  'permission_id','project.create'))).*
                from public.audit_events value where value.id=$1::uuid""",
                valid_id,
                crossed_id,
            )
        assert error.value.constraint_name == NAME
        assert (
            await connection.fetchval(
                "select count(*) from public.audit_events where id=$1::uuid",
                valid_id,
            )
            == 1
        )
        assert (
            await connection.fetchval(
                "select count(*) from public.audit_events where id=$1::uuid",
                crossed_id,
            )
            == 0
        )
    finally:
        await connection.close()


def test_upgrade_qualifies_public_constraint_under_shadowed_search_path(
    isolated_database_env,
    migration_lock,
):
    with migration_lock():
        asyncio.run(db_session.dispose_engine())
        asyncio.run(_drop_test_database_schema(isolated_database_env))
        command.upgrade(_config(), "0060_audit_restore_path")
        before_public, before_shadow = asyncio.run(_prepare_shadow(isolated_database_env))
        try:
            command.upgrade(_config(), "0061_project_catalogue_read")
            after_public, after_shadow = asyncio.run(_definitions(isolated_database_env))
            assert before_public.count("project.catalogue.list") == 0
            assert after_public.count("project.catalogue.list") == 2
            assert after_shadow == before_shadow
            asyncio.run(_assert_closed_pair(isolated_database_env))
        finally:
            asyncio.run(_restore_role_search_path(isolated_database_env))
