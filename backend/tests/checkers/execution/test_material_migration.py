"""Actual 0008 upgrades preserve valid evidence and refuse unprovable custody."""

import asyncio

import asyncpg
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.db import session as db_session
from tests.migration_fixtures import add_current_art_seed_column, restore_predecessor_evidence_schema
from tests.migration_fixtures import _config
from tests.historical_submission_fixtures import historical_material_fixture
from types import SimpleNamespace

from .historical_execution import (
    seed_archived_checker_request,
    seed_archived_running_checker,
    archived_terminal_rows,
    seed_archived_terminal,
)

pytestmark = pytest.mark.postgres_schema_contract


async def predecessor_database(url):
    await db_session.dispose_engine()
    connection = await asyncpg.connect(url.replace("+asyncpg", ""))
    try:
        await connection.execute("drop schema public cascade; create schema public")
    finally:
        await connection.close()
    await asyncio.to_thread(command.upgrade, _config(), "0008_checker_execution")


async def retained_snapshot(factory):
    async with factory() as session:
        rows = list((await session.scalars(text("select to_jsonb(r) from checker_runs r order by id"))).all())
        version = await session.scalar(text("select version_num from alembic_version"))
        functions = list((await session.execute(text(
            "select p.proname,pg_get_functiondef(p.oid) from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
            "where n.nspname='public' and p.prokind='f' order by p.proname"
        ))).all())
        triggers = list((await session.execute(text(
            "select tgname,pg_get_triggerdef(oid) from pg_trigger where not tgisinternal order by tgname"
        ))).all())
        return rows, version, functions, triggers


@pytest.mark.parametrize("outcome", ["completed", "infrastructure_failed"])
@pytest.mark.parametrize("valid", [True, False])
async def test_retained_material_upgrade(
    tmp_path, isolated_database_env, migration_lock, outcome, valid
):
    with migration_lock():
        await predecessor_database(isolated_database_env)
        original_columns = await add_current_art_seed_column(isolated_database_env)
        async with historical_material_fixture(
            tmp_path, isolated_database_env, provision_checker=False
        ) as h:
            await restore_predecessor_evidence_schema(isolated_database_env, original_columns)
            await seed_archived_checker_request(h)
            lease = await seed_archived_running_checker(h)
            material = dict(h.archived_material)
            if not valid:
                # A real but wrong admission is covered separately in direct SQL
                # tests. This retained 0008 row proves no fabricated ID backfill.
                material["admission_id"] = h.request["submission_id"]
            rows = archived_terminal_rows(
                h, lease, outcome=outcome,
                members=h.archived_members if outcome == "completed" else (),
                counts=h.archived_counts if outcome == "completed" else dict(passed=0, warning=0, failed=0, blocking=0),
                routing_recommendation="allow_review" if outcome == "completed" else "not_evaluated",
                failure_code=None if outcome == "completed" else "implementation_unavailable",
                material=material,
            )
            async with h.factory() as session, session.begin():
                await seed_archived_terminal(session, rows)
            if valid:
                # Preserve superseded completed/failed history and a current
                # failure that never received material, plus later replica loss.
                successor = SimpleNamespace(**vars(h))
                request_body = {key: value for key, value in h.request.items() if key != "request_sha256"}
                request_body.update(evaluation_generation=2, evaluation_request_id=str(new_record_id()))
                successor.request = request_body | {"request_sha256": canonical_json_hash(request_body)}
                await seed_archived_checker_request(successor)
                next_lease = await seed_archived_running_checker(successor)
                empty = archived_terminal_rows(
                    successor, next_lease, outcome="infrastructure_failed", members=(),
                    counts=dict(passed=0, warning=0, failed=0, blocking=0),
                    routing_recommendation="not_evaluated", failure_code="material_unavailable", material=None,
                )
                async with h.factory() as session, session.begin():
                    await seed_archived_terminal(session, empty)
                    await session.execute(text(
                        "update artifact_replicas set availability_state='unavailable', "
                        "content_id=(select id from artifact_contents where id<>:content limit 1) where id=:id"
                    ), {"id": h.replica_id, "content": h.archived_material["content_id"]})
            before = await retained_snapshot(h.factory)
            assert before[1] == "0008_checker_execution"
            if valid:
                await asyncio.to_thread(command.upgrade, _config(), "0009_checker_material_lineage")
                after = await retained_snapshot(h.factory)
                assert after[0] == before[0]
                assert after[1] == "0009_checker_material_lineage"
            else:
                with pytest.raises(IntegrityError, match="retained checker material lacks canonical ART lineage"):
                    await asyncio.to_thread(command.upgrade, _config(), "0009_checker_material_lineage")
                assert await retained_snapshot(h.factory) == before


async def test_upgrade_excludes_writer_until_guard_is_installed(
    tmp_path,
    isolated_database_env,
    migration_lock,
    monkeypatch,
):
    import threading
    from alembic.operations import Operations

    with migration_lock():
        await predecessor_database(isolated_database_env)
        original_columns = await add_current_art_seed_column(isolated_database_env)
        async with historical_material_fixture(
            tmp_path, isolated_database_env, provision_checker=False
        ) as h:
            await restore_predecessor_evidence_schema(isolated_database_env, original_columns)
            await seed_archived_checker_request(h)
            lease = await seed_archived_running_checker(h)
            material = dict(h.archived_material) | {"admission_id": h.request["submission_id"]}
            rows = archived_terminal_rows(
                h, lease, outcome="completed", members=h.archived_members, counts=h.archived_counts,
                routing_recommendation="allow_review", failure_code=None, material=material,
            )
            scanned, resume = threading.Event(), threading.Event()
            execute = Operations.execute

            def paused_execute(operations, sql, *args, **kwargs):
                result = execute(operations, sql, *args, **kwargs)
                if isinstance(sql, str) and sql.lstrip().startswith("DO $$ BEGIN") and "retained checker material" in sql:
                    scanned.set()
                    assert resume.wait(20), "migration test did not release scan checkpoint"
                return result

            monkeypatch.setattr(Operations, "execute", paused_execute)
            migration = asyncio.create_task(asyncio.to_thread(command.upgrade, _config(), "0009_checker_material_lineage"))
            writer = None
            pid = asyncio.Queue()

            async def write():
                async with h.factory() as session, session.begin():
                    await pid.put(await session.scalar(text("select pg_backend_pid()")))
                    await seed_archived_terminal(session, rows)

            try:
                assert await asyncio.to_thread(scanned.wait, 10), "migration did not reach preflight"
                writer = asyncio.create_task(write())
                writer_pid = await asyncio.wait_for(pid.get(), 5)
                waiting = False
                async with h.factory() as observer:
                    for _ in range(100):
                        waiting = bool(await observer.scalar(text(
                            "select cardinality(pg_blocking_pids(:pid)) > 0"
                        ), {"pid": writer_pid}))
                        if waiting or writer.done():
                            break
                        await asyncio.sleep(0.02)
                assert waiting and not writer.done(), "writer entered the preflight/install gap"
                resume.set()
                await asyncio.wait_for(migration, 10)
                with pytest.raises(IntegrityError, match="checker material canonical ART lineage mismatch"):
                    await asyncio.wait_for(writer, 10)
                async with h.factory() as session:
                    assert await session.scalar(text("select status from checker_runs where id=:id"),
                                                {"id": rows["run"]["id"]}) == "running"
            finally:
                resume.set()
                await asyncio.gather(migration, *([writer] if writer is not None else []), return_exceptions=True)
