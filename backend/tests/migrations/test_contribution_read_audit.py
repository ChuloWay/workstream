"""Exact contribution-read audit vocabulary under the forward migration."""

from __future__ import annotations

import asyncio
from alembic import command
import asyncpg
import pytest

from app.core.identifiers import new_record_id
from app.db import session as db_session
from tests.conftest import _drop_test_database_schema
from tests.migration_fixtures import _config as config


pytestmark = pytest.mark.postgres_schema_contract
EVIDENCE_CONSTRAINT = "ck_audit_events_authorization_action_evidence"
REGISTRY_CONSTRAINT = "ck_audit_events_authority_registries"
ACTIONS = ("contribution.read_self", "contribution.read_project")


async def _clone(
    database_url: str,
    *,
    source: str,
    identity: str,
    action: str,
    permission: str,
) -> None:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        await connection.execute(
            """insert into public.audit_events
            select (jsonb_populate_record(null::public.audit_events,
              to_jsonb(value) || jsonb_build_object(
                'id',$2::text,'entity_id',$2::text,
                'action_id',$3::text,'permission_id',$4::text))).*
            from public.audit_events value where value.id=$1::uuid""",
            source,
            identity,
            action,
            permission,
        )
    finally:
        await connection.close()


async def _seed_template(database_url: str) -> str:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        return str(
            await connection.fetchval(
                """insert into public.audit_events(
                id,entity_type,entity_id,event_type,actor_id,actor_roles,claim_snapshot,
                auth_source,is_dev_auth,event_payload,event_domain,event_version,actor_ref_kind,
                request_id,correlation_id,permission_id,action_id,reason,project_id,resource_type,
                resource_id,after_facts,matched_grant_id,target_ref_kind,target_ref_id,denial_code)
                select $1::uuid,'authorization_decision',$1::uuid,
                'SensitiveAuthorizationDenied',gen_random_uuid()::text,'[]','{}',
                'local_authority',false,'{}','authority',1,'actor_profile',
                gen_random_uuid(),gen_random_uuid(),'project.read','project.read',
                'authorization_evaluation',null,null,null,
                jsonb_build_object('allowed',false,'resource_context_digest',
                  'sha256:'||repeat('a',64)),null,null,null,'permission_not_granted'
                returning id""",
                str(new_record_id()),
            )
        )
    finally:
        await connection.close()


async def _definition(database_url: str, name: str) -> str:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        return await connection.fetchval(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid='public.audit_events'::regclass and conname=$1",
            name,
        )
    finally:
        await connection.close()


async def _audit_snapshot(database_url: str):
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        return (
            await connection.fetchval("select version_num from public.alembic_version"),
            await connection.fetch("select to_jsonb(r)::text from public.audit_events r order by id"),
        )
    finally:
        await connection.close()


def test_contribution_read_upgrade_closes_exact_pairs_and_preserves_predecessors(
    isolated_database_env: str,
    migration_lock,
) -> None:
    with migration_lock():
        asyncio.run(db_session.dispose_engine())
        asyncio.run(_drop_test_database_schema(isolated_database_env))
        command.upgrade(config(), "0032_checker_remediation")
        before_evidence = asyncio.run(_definition(isolated_database_env, EVIDENCE_CONSTRAINT))
        before_registry = asyncio.run(_definition(isolated_database_env, REGISTRY_CONSTRAINT))
        assert all(action not in before_evidence for action in ACTIONS)

        template = asyncio.run(_seed_template(isolated_database_env))
        command.upgrade(config(), "0033_contribution_reads")
        after_evidence = asyncio.run(_definition(isolated_database_env, EVIDENCE_CONSTRAINT))
        after_registry = asyncio.run(_definition(isolated_database_env, REGISTRY_CONSTRAINT))
        for token in (
            "artifact.task_import_source.declare",
            "checker.registry.register",
            "task.post_submit.route",
        ):
            assert before_evidence.count(token) == after_evidence.count(token)
        for action in ACTIONS:
            assert after_evidence.count(action) == 4
            asyncio.run(
                _clone(
                    isolated_database_env,
                    source=template,
                    identity=str(new_record_id()),
                    action=action,
                    permission=action,
                )
            )
            for permission in ({*ACTIONS, "project.read"} - {action}):
                with pytest.raises(asyncpg.CheckViolationError) as failure:
                    asyncio.run(
                        _clone(
                            isolated_database_env,
                            source=template,
                            identity=str(new_record_id()),
                            action=action,
                            permission=permission,
                        )
                    )
                assert failure.value.constraint_name == EVIDENCE_CONSTRAINT
        assert after_registry == before_registry

        retained = asyncio.run(_audit_snapshot(isolated_database_env))
        assert retained[0] == "0033_contribution_reads"
        with pytest.raises(RuntimeError, match="retained evidence"):
            command.downgrade(config(), "0032_checker_remediation")
        assert asyncio.run(_audit_snapshot(isolated_database_env)) == retained
