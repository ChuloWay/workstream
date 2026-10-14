"""Real late-commit visibility and public grant revocation at the response fence."""

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.modules.authorization.admin_service import AdminRoleGrantService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.contributions.records.read_service import ContributionReadService
from app.modules.contributions.records.read_repository import ContributionReadRepository
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.contributions.records.support import (
    authorized_submitter_source, reviewer_contribution_source, insert_record,
)
from tests.tasks.post_submit_routing.outcome_support import authorized_routing_source, apply_outcome
from .support import export_path, export_audits, prepared_reviewer_sibling


async def test_two_session_fifth_slot_race_returns_one_page_and_generic_capacity(
    tmp_path, auth_database_env, admin_access, monkeypatch,
):
    """A sixth first page waits for the actor fence, then cannot take slot five."""
    async with reviewer_contribution_source(tmp_path, auth_database_env) as h:
        async with h.factory() as session, session.begin():
            await insert_record(session, h.reviewer_record)
        sibling = await prepared_reviewer_sibling(h)
        async with h.factory() as session, session.begin():
            await insert_record(session, sibling)
        project = h.reviewer_record.project_id
        reader = await admin_access.signed.actor("five-slot-project-reader")
        await admin_access.signed.grant(admin_access.admin, reader,
                                       role="project_manager", project_id=project)
        path = export_path(project)
        for _ in range(4):
            page = await admin_access.signed.client.get(
                path, params={"limit": 1}, headers=reader.headers,
            )
            assert page.status_code == 200 and page.json()["next_cursor"], page.text

        identity = "contribution-slot-race-" + uuid4().hex
        held, release = asyncio.Event(), asyncio.Event()
        pids = {}
        original = ContributionReadRepository._load_records

        def named_transaction(session, transaction, connection):
            name = asyncio.current_task().get_name()
            if name in {identity + "-fifth", identity + "-sixth"}:
                connection.execute(text("select set_config('application_name',:name,true)"), {"name": name})
                pids[name] = connection.scalar(text("select pg_backend_pid()"))

        async def hold_fifth(repository, request, ids):
            if asyncio.current_task().get_name() == identity + "-fifth":
                held.set()
                await release.wait()
            return await original(repository, request, ids)

        tasks = []
        with monkeypatch.context() as patch:
            patch.setattr(ContributionReadRepository, "_load_records", hold_fifth)
            event.listen(Session, "after_begin", named_transaction)
            try:
                tasks.append(asyncio.create_task(admin_access.signed.client.get(
                    path, params={"limit": 1}, headers=reader.headers,
                ), name=identity + "-fifth"))
                await asyncio.wait_for(held.wait(), 30)
                tasks.append(asyncio.create_task(admin_access.signed.client.get(
                    path, params={"limit": 1}, headers=reader.headers,
                ), name=identity + "-sixth"))
                await asyncio.wait_for(wait_for_named_database_lock(
                    auth_database_env, identity + "-sixth",
                    expected_blocker_pid=pids[identity + "-fifth"],
                ), 15)
                release.set()
                fifth, sixth = await asyncio.wait_for(asyncio.gather(*tasks), 30)
            finally:
                release.set()
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                event.remove(Session, "after_begin", named_transaction)

        assert fifth.status_code == 200 and fifth.json()["next_cursor"], fifth.text
        assert sixth.status_code == 429, sixth.text
        assert sixth.json()["error"]["code"] == "contribution_export_at_capacity"
        assert 1 <= int(sixth.headers["Retry-After"]) <= 3600
        async with h.factory() as session:
            count = await session.scalar(text("""
                SELECT count(*) FROM public.contribution_export_snapshots
                WHERE actor_profile_id=:actor
            """), {"actor": str(reader.id)})
        assert count == 5
        continuation = await admin_access.signed.client.get(
            path, params={"limit": 1, "cursor": fifth.json()["next_cursor"]},
            headers=reader.headers,
        )
        assert continuation.status_code == 200, continuation.text
        assert [item["contribution_id"] for item in continuation.json()["items"]] == [str(sibling.id)]
        assert continuation.json()["next_cursor"] is None


async def test_late_commit_after_first_auth_snapshot_never_enters_fixed_traversal(
    tmp_path, auth_database_env, admin_access, monkeypatch,
):
    """A live timestamp keyset would expose L on page three after A and B."""
    async with reviewer_contribution_source(tmp_path, auth_database_env) as h:
        async with h.factory() as session, session.begin():
            await insert_record(session, h.reviewer_record)
        second = await prepared_reviewer_sibling(h)
        async with h.factory() as session, session.begin():
            await insert_record(session, second)
        late = await prepared_reviewer_sibling(h)
        project = h.reviewer_record.project_id
        reader = await admin_access.signed.actor("late-commit-cursor-reader")
        await admin_access.signed.grant(admin_access.admin, reader,
                                       role="project_manager", project_id=project)

        reached, proceed = asyncio.Event(), asyncio.Event()
        original = AdminAuthorizationRepository.lock_project

        async def after_first_auth_sql(repository, project_id):
            if asyncio.current_task().get_name() == "contribution-fixed-first-page":
                # Actor/link and selected grant SQL have fixed this attempt's RR snapshot.
                reached.set()
                await proceed.wait()
            return await original(repository, project_id)

        monkeypatch.setattr(AdminAuthorizationRepository, "lock_project", after_first_auth_sql)
        async with h.factory() as producer:
            await producer.begin()
            await insert_record(producer, late)
            first_task = asyncio.create_task(admin_access.signed.client.get(
                export_path(project), params={"limit": 1}, headers=reader.headers,
            ), name="contribution-fixed-first-page")
            try:
                await asyncio.wait_for(reached.wait(), 30)
                await producer.commit()
                proceed.set()
                first = await asyncio.wait_for(first_task, 30)
            finally:
                proceed.set()
                if not first_task.done():
                    first_task.cancel()
                await asyncio.gather(first_task, return_exceptions=True)

        assert first.status_code == 200, first.text
        assert [item["contribution_id"] for item in first.json()["items"]] == [str(h.reviewer_record.id)]
        cursor = first.json()["next_cursor"]
        assert cursor
        second_page = await admin_access.signed.client.get(
            export_path(project), params={"limit": 1, "cursor": cursor}, headers=reader.headers,
        )
        assert second_page.status_code == 200, second_page.text
        assert [item["contribution_id"] for item in second_page.json()["items"]] == [str(second.id)]
        assert second_page.json()["next_cursor"] is None
        fresh = await admin_access.signed.client.get(
            export_path(project), params={"limit": 3}, headers=reader.headers,
        )
        assert fresh.status_code == 200, fresh.text
        assert [item["contribution_id"] for item in fresh.json()["items"]] == [
            str(h.reviewer_record.id), str(second.id), str(late.id)
        ]


async def test_first_auth_snapshot_excludes_source_committed_before_owner_projection(
    tmp_path, auth_database_env, admin_access, live_acceptance_lifecycle, monkeypatch,
):
    """A real staged acceptance commits after AUTH's snapshot but before CON selects."""
    async with authorized_routing_source(tmp_path, auth_database_env, contribution_awards=("money",)) as h:
        project = h.request.project_id
        await admin_access.signed.grant(admin_access.admin, admin_access.target,
                                       role="project_manager", project_id=project)
        reached, proceed = asyncio.Event(), asyncio.Event()
        original = AdminAuthorizationRepository.lock_project
        observed = []
        rr_statements = []

        def record_rr_sql(connection, cursor, statement, parameters, context, executemany):
            if (asyncio.current_task().get_name() == "pilot10-late-source-read"
                    and connection.get_execution_options().get("isolation_level") == "REPEATABLE READ"):
                rr_statements.append(statement)

        async def before_project_lock(repository, project_id):
            if asyncio.current_task().get_name() == "pilot10-late-source-read":
                # Actor/grant AUTH SQL has already established this same transaction's snapshot.
                observed.append(await repository._session.scalar(text("SHOW transaction_isolation")))
                reached.set()
                await proceed.wait()
            return await original(repository, project_id)

        monkeypatch.setattr(AdminAuthorizationRepository, "lock_project", before_project_lock)
        async with h.factory() as producer:
            await producer.begin()
            outcome = await apply_outcome(producer, h, 2)
            event.listen(Engine, "before_cursor_execute", record_rr_sql)
            read = asyncio.create_task(admin_access.signed.client.get(
                export_path(project), headers=admin_access.target.headers,
            ), name="pilot10-late-source-read")
            try:
                await asyncio.wait_for(reached.wait(), 30)
                await producer.commit()
                proceed.set()
                response = await asyncio.wait_for(read, 30)
            finally:
                proceed.set()
                if not read.done():
                    read.cancel()
                await asyncio.gather(read, return_exceptions=True)
                event.remove(Engine, "before_cursor_execute", record_rr_sql)
            assert observed == ["repeatable read"]
            assert "actor_profiles" in rr_statements[0] and "FOR UPDATE" in rr_statements[0]
            assert "actor_identity_links" in rr_statements[1] and "FOR UPDATE" in rr_statements[1]
            assert response.status_code == 200, response.text
            assert response.json()["items"] == []
            fresh = await admin_access.signed.client.get(export_path(project), headers=admin_access.target.headers)
            assert fresh.status_code == 200, fresh.text
            item, = fresh.json()["items"]
            assert item["contribution_id"] == str(outcome.economic.contribution_record_id)
            assert len(item["awards"]) == 1


@pytest.mark.parametrize("first", ["read", "revoke"])
async def test_public_export_serializes_with_revocation_and_reauthorizes_next_request(
    tmp_path, auth_database_env, admin_access, live_acceptance_lifecycle, monkeypatch, first,
):
    """Observed PostgreSQL blockers prove locks survive the complete owner projection."""
    async with authorized_submitter_source(tmp_path, auth_database_env) as h:
        project = h.submitter_record.project_id
        grant = await admin_access.signed.grant(admin_access.admin, admin_access.target,
                                              role="project_manager", project_id=project)
        identity = "pilot10-fence-" + uuid4().hex
        held, release = asyncio.Event(), asyncio.Event()
        pids = {}
        original_read = ContributionReadService.read
        original_revoke = AdminRoleGrantService.complete_revoke

        def named_transaction(session, transaction, connection):
            name = asyncio.current_task().get_name()
            if name in {identity + "-read", identity + "-revoke"}:
                connection.execute(text("select set_config('application_name',:name,true)"), {"name": name})
                pids[name] = connection.scalar(text("select pg_backend_pid()"))

        async def hold(name, result):
            if first == name:
                held.set()
                await release.wait()
            return result

        async def paused_read(service, selected):
            return await hold("read", await original_read(service, selected))

        async def paused_revoke(service, *args, **kwargs):
            return await hold("revoke", await original_revoke(service, *args, **kwargs))

        async def invoke(name):
            if name == "read":
                return await admin_access.signed.client.get(
                    export_path(project), params={"format": "csv"}, headers=admin_access.target.headers,
                )
            return await admin_access.signed.revoke(admin_access.admin, grant)

        second = "revoke" if first == "read" else "read"
        tasks = []
        serialization_errors = []

        def capture_serialization(error_context):
            code = getattr(error_context.original_exception, "sqlstate", None)
            if code == "40001":
                serialization_errors.append(code)
        with monkeypatch.context() as patch:
            patch.setattr(ContributionReadService, "read", paused_read)
            patch.setattr(AdminRoleGrantService, "complete_revoke", paused_revoke)
            event.listen(Session, "after_begin", named_transaction)
            event.listen(Engine, "handle_error", capture_serialization)
            try:
                tasks.append(asyncio.create_task(invoke(first), name=identity + "-" + first))
                await asyncio.wait_for(held.wait(), 30)
                tasks.append(asyncio.create_task(invoke(second), name=identity + "-" + second))
                await asyncio.wait_for(wait_for_named_database_lock(
                    auth_database_env, identity + "-" + second,
                    expected_blocker_pid=pids[identity + "-" + first],
                ), 15)
                assert not tasks[1].done()
                release.set()
                responses = await asyncio.wait_for(asyncio.gather(*tasks), 30)
            finally:
                release.set()
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                event.remove(Session, "after_begin", named_transaction)
                event.remove(Engine, "handle_error", capture_serialization)
        assert serialization_errors == (["40001"] if first == "revoke" else [])
        results = dict(zip((first, second), responses, strict=True))
        assert results["revoke"].status_code == 200, results["revoke"].text
        assert results["read"].status_code == (200 if first == "read" else 404), results["read"].text
        fresh = await admin_access.signed.client.get(export_path(project), headers=admin_access.target.headers)
        assert fresh.status_code == 404, fresh.text
        evidence = await export_audits(h.factory)
        assert len(evidence) == 2
        assert evidence[0]["after_facts"]["allowed"] is (first == "read")
        assert evidence[1]["after_facts"]["allowed"] is False
        assert evidence[1]["target_ref_id"] is evidence[1]["project_id"] is None
