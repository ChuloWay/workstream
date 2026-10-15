"""Actual predecessor upgrade refuses retained rows before destructive reshaping."""

import asyncio
import json

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.identifiers import new_record_id
from tests.migration_fixtures import _config, current_schema_revision
from tests.historical_submission_fixtures import historical_material_fixture

pytestmark = pytest.mark.postgres_schema_contract


async def test_migration_refuses_retained_history(tmp_path, isolated_database_env, migration_lock):
    import asyncpg
    from app.db import session as db_session

    url = isolated_database_env.replace("+asyncpg", "")
    await db_session.dispose_engine()
    with migration_lock():
        conn = await asyncpg.connect(url)
        try:
            await conn.execute("drop schema public cascade; create schema public")
        finally:
            await conn.close()
        await asyncio.to_thread(command.upgrade, _config(), "0007_checker_output_custody")
        async with historical_material_fixture(tmp_path, isolated_database_env) as h:
            async with h.factory() as session, session.begin():
                source = await session.scalar(
                    text("select to_jsonb(s) from submissions s where id=:id"),
                    {"id": h.request["submission_id"]},
                )
                values = {
                    key: value
                    for key, value in source.items()
                    if key.startswith("locked_")
                    and key
                    in {
                        "locked_guide_version",
                        "locked_post_submit_checker_policy_id",
                        "locked_post_submit_checker_policy_version",
                        "locked_post_submit_checker_policy_hash",
                        "locked_post_submit_checker_policy_body",
                        "locked_review_policy_id",
                        "locked_review_policy_generation",
                        "locked_review_policy_hash",
                        "locked_revision_policy_id",
                        "locked_revision_policy_generation",
                        "locked_revision_policy_hash",
                        "locked_payment_policy_version",
                    }
                }
                values.update(
                    id=str(new_record_id()),
                    task_id=source["task_id"],
                    submission_id=source["id"],
                    submission_version=source["version"],
                    trigger_source="retained_test_evidence",
                    status="queued",
                    routing_recommendation="not_evaluated",
                    outcome_source="none",
                    triggered_by="fixture",
                    triggered_by_subject="fixture",
                    triggered_by_issuer="fixture",
                    trigger_auth_source="test",
                    attempt_number=1,
                    is_current_for_submission=True,
                    package_hash=h.request["content_sha256"],
                    artifact_hash_manifest=source["artifact_hash_manifest"],
                    artifact_manifest_hash=h.archived_material["semantic_manifest_sha256"],
                    passed_count=0,
                    warning_count=0,
                    failed_count=0,
                    blocking_count=0,
                )
                parameters = {
                    key: json.dumps(value) if isinstance(value, (dict, list)) else value
                    for key, value in values.items()
                }
                selectors = [
                    f"cast(:{key} as json)" if isinstance(value, (dict, list)) else f":{key}"
                    for key, value in values.items()
                ]
                await session.execute(
                    text(
                        "insert into checker_runs ("
                        + ",".join(values)
                        + ") values ("
                        + ",".join(selectors)
                        + ")"
                    ),
                    parameters,
                )

            async def snapshot():
                async with h.factory() as session:
                    rows = list(
                        (
                            await session.execute(
                                text("select to_jsonb(r) from checker_runs r order by id")
                            )
                        ).scalars()
                    )
                    columns = list(
                        (
                            await session.execute(
                                text(
                                    "select table_name,column_name,data_type,is_nullable from information_schema.columns where table_schema='public' order by table_name,ordinal_position"
                                )
                            )
                        ).all()
                    )
                    version = await session.scalar(text("select version_num from alembic_version"))
                    return rows, columns, version

            before = await snapshot()
            assert before[0] and before[2] == "0007_checker_output_custody"
            with pytest.raises(
                IntegrityError,
                match="retained checker history requires an explicit preservation design",
            ):
                await asyncio.to_thread(command.upgrade, _config(), "head")
            assert await snapshot() == before


async def test_empty_database_installs_execution_custody(isolated_database_env, migration_lock):
    import asyncpg
    from app.db import session as db_session

    await db_session.dispose_engine()
    url = isolated_database_env.replace("+asyncpg", "")
    with migration_lock():
        conn = await asyncpg.connect(url)
        try:
            await conn.execute("drop schema public cascade; create schema public")
        finally:
            await conn.close()
        await asyncio.to_thread(command.upgrade, _config(), "head")
        conn = await asyncpg.connect(url)
        try:
            assert (
                await conn.fetchval("select version_num from alembic_version")
                == current_schema_revision()
            )
            assert await conn.fetchval("select count(*) from checker_submission_fences") == 0
            columns = set(
                await conn.fetchval(
                    "select array_agg(column_name) from information_schema.columns where table_schema='public' and table_name='checker_runs'"
                )
            )
            assert {
                "evaluation_request_id",
                "request_digest",
                "worker_lease_id",
                "result_digest",
                "completion_event_id",
            } <= columns
            assert {
                "is_current_for_submission",
                "attempt_number",
                "trigger_auth_source",
            }.isdisjoint(columns)
        finally:
            await conn.close()


_V1_RESULT = '{"schema_version":"external_checker_result.v1"}'


def _retained_v1_row(table, column, value):
    """Insert one row carrying a v1 marker with every other required column filled.

    Only this owned database's guards on that table are lifted: the row's owners
    are not the claim, the marker is.
    """
    return f"""
    DO $$ DECLARE c record; cols text; vals text; BEGIN
      FOR c IN SELECT conname FROM pg_constraint
        WHERE conrelid='public.{table}'::regclass AND contype IN ('f','c') LOOP
        EXECUTE format('ALTER TABLE public.{table} DROP CONSTRAINT %I', c.conname);
      END LOOP;
      EXECUTE 'ALTER TABLE public.{table} DISABLE TRIGGER USER';
      SELECT string_agg(quote_ident(column_name), ','), string_agg(CASE
          WHEN column_name='{column}' THEN quote_literal('{value}')
          WHEN data_type='uuid' THEN 'gen_random_uuid()'
          WHEN data_type IN ('smallint','integer','bigint','numeric') THEN '0'
          WHEN data_type='boolean' THEN 'false'
          WHEN data_type LIKE 'timestamp%' THEN 'now()'
          WHEN data_type IN ('json','jsonb') THEN quote_literal('{{}}')
          ELSE quote_literal('x') END, ',')
        INTO cols, vals FROM information_schema.columns
        WHERE table_schema='public' AND table_name='{table}' AND is_generated='NEVER'
          AND ((is_nullable='NO' AND column_default IS NULL) OR column_name='{column}');
      EXECUTE format('INSERT INTO public.{table} (%s) VALUES (%s)', cols, vals);
      EXECUTE 'ALTER TABLE public.{table} ENABLE TRIGGER USER';
    END $$"""


@pytest.mark.parametrize(("table", "column", "value"), [
    ("checker_results", "definition_version", "external_checker_result.v1"),
    ("checker_runs", "result_json", _V1_RESULT),
    ("selected_pre_submit_runs", "terminal_json", _V1_RESULT),
])
async def test_result_contract_upgrade_refuses_retained_v1_results(
    isolated_database_env, migration_lock, table, column, value,
):
    """0048 stops before any DDL when v1 result evidence would lose its contract."""
    import asyncpg
    from app.db import session as db_session

    await db_session.dispose_engine()
    url = isolated_database_env.replace("+asyncpg", "")
    with migration_lock():
        conn = await asyncpg.connect(url)
        try:
            await conn.execute("drop schema public cascade; create schema public")
        finally:
            await conn.close()
        await asyncio.to_thread(command.upgrade, _config(), "0047_revision_recovery")
        conn = await asyncpg.connect(url)
        try:
            await conn.execute(_retained_v1_row(table, column, value))
            schema = "select count(*) from information_schema.tables where table_schema='public'"
            tables = await conn.fetchval(schema)
            with pytest.raises(
                IntegrityError,
                match="retained external checker v1 results require an explicit preservation design",
            ):
                await asyncio.to_thread(command.upgrade, _config(), "head")
            assert await conn.fetchval("select version_num from alembic_version") == "0047_revision_recovery"
            assert await conn.fetchval(schema) == tables
        finally:
            await conn.close()
