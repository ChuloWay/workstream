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
