"""Current PostgreSQL proof for the two-role v0.1 authority vocabulary."""

import asyncio

import asyncpg
import pytest

from app.core.identifiers import new_record_id


pytestmark = pytest.mark.postgres_schema_contract


async def _value(database_url: str, statement: str, *arguments):
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        return await connection.fetchval(statement, *arguments)
    finally:
        await connection.close()


async def _definitions(database_url: str) -> tuple[str, ...]:
    connection = await asyncpg.connect(database_url.replace("+asyncpg", ""))
    try:
        rows = await connection.fetch(
            "select pg_get_constraintdef(c.oid) as definition "
            "from pg_constraint c join pg_class t on t.oid=c.conrelid "
            "where (t.relname,c.conname) in "
            "(('project_role_grants','ck_project_role_grants_role'),"
            "('project_role_qualification_snapshots',"
            "'ck_project_role_qualification_snapshots_role')) "
            "order by c.conname"
        )
        functions = [
            await connection.fetchval("select pg_get_functiondef(to_regprocedure($1))", signature)
            for signature in (
                "authority_event_facts_are_safe(text,json,json,text)",
                "validate_linked_authority_event()",
            )
        ]
        return tuple(row["definition"] for row in rows) + tuple(functions)
    finally:
        await connection.close()


def test_project_role_database_accepts_only_current_role_audit_facts(
    isolated_database_env: str,
) -> None:
    project = str(new_record_id())
    statement = (
        "select authority_event_facts_are_safe('ProjectRoleGrantIssued',null,"
        "json_build_object('status','active','role',$1::text,'scope_type','project',"
        "'scope_id',$2::text,'effective',true),$2::text)"
    )
    assert asyncio.run(_value(isolated_database_env, statement, "submitter", project)) is True
    assert asyncio.run(_value(isolated_database_env, statement, "reviewer", project)) is True
    assert asyncio.run(_value(isolated_database_env, statement, "adjudicator", project)) is False
    assert all(
        "adjudicator" not in definition
        for definition in asyncio.run(_definitions(isolated_database_env))
    )


@pytest.mark.parametrize("search_path", ("", "pg_temp,public,pg_catalog"))
@pytest.mark.parametrize("event_name", ("ActorProfileProvisioned", "ProjectRoleGrantIssued"))
def test_audit_facts_restore_with_safe_helpers(
    isolated_database_env: str, search_path: str, event_name: str
) -> None:
    """COPY validates both audit helper paths under restore and caller namespaces."""
    import json

    project = str(new_record_id()) if event_name == "ProjectRoleGrantIssued" else None
    valid = (
        {
            "status": "active",
            "subject_kind": "human",
            "provisioning_method": "automatic_first_access",
        }
        if project is None
        else {
            "status": "active",
            "role": "submitter",
            "scope_type": "project",
            "scope_id": project,
            "effective": True,
        }
    )
    invalid = {**valid, "private_material": "must not persist"}
    if project is not None:
        invalid = {**valid, "role": "unregistered_role"}

    async def copy_facts() -> None:
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        try:
            # Use the actual audit fact predicate, without unrelated audit parent setup.
            await connection.execute(
                "CREATE TEMP TABLE restore_audit_facts (event_name text, before_facts json, "
                "after_facts json, project_id text, CONSTRAINT restore_fact_bounds CHECK ("
                "public.authority_event_facts_are_safe(event_name,before_facts,after_facts,project_id)))"
            )
            await connection.execute(
                "CREATE FUNCTION pg_temp.authority_facts_are_safe(json) RETURNS boolean "
                "LANGUAGE sql AS 'SELECT true'; "
                "CREATE FUNCTION pg_temp.authority_grant_facts_are_safe(json,text[],text,boolean,text) "
                "RETURNS boolean LANGUAGE sql AS 'SELECT true'"
            )
            await connection.execute(
                "SELECT pg_catalog.set_config('search_path',$1,false)", search_path
            )
            if project is not None:
                # The grant helper is also a callable contract, independently of the event wrapper.
                statement = (
                    "SELECT public.authority_grant_facts_are_safe("
                    "$1::json,ARRAY['submitter','reviewer'],'active',true,$2::text)"
                )
                assert await connection.fetchval(statement, json.dumps(valid), project) is True
                assert await connection.fetchval(statement, json.dumps(invalid), project) is False
            await connection.copy_records_to_table(
                "restore_audit_facts",
                schema_name="pg_temp",
                records=[(event_name, None, json.dumps(valid), project)],
            )
            with pytest.raises(asyncpg.CheckViolationError, match="restore_fact_bounds"):
                await connection.copy_records_to_table(
                    "restore_audit_facts",
                    schema_name="pg_temp",
                    records=[(event_name, None, json.dumps(invalid), project)],
                )
            rows = await connection.fetch("SELECT after_facts FROM pg_temp.restore_audit_facts")
            assert [json.loads(row["after_facts"]) for row in rows] == [valid]
        finally:
            await connection.close()

    asyncio.run(copy_facts())
