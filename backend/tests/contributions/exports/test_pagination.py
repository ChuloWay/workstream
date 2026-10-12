"""Real public pages freeze visible membership and reauthorize continuation."""

import asyncio
import csv

import pytest
from io import StringIO

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.identifiers import new_record_id
from app.modules.contributions.records.models import ContributionExportMembership, ContributionExportMember
from app.modules.authorization.repository import AdminAuthorizationRepository
from tests.contributions.records.support import authorized_submitter_source, rows
from tests.tasks.post_submit_routing.support import completed_sibling_source
from tests.tasks.post_submit_routing.outcome_support import apply_outcome, invoked_completion
from .support import export_path


async def sibling_ready(h):
    """Use real Submission/checker completion and authorized acceptance inputs."""
    sibling = await completed_sibling_source(h)
    async with h.factory() as session, session.begin():
        await session.execute(text(
            "UPDATE public.task_assignments SET accepted_at=clock_timestamp() "
            "WHERE id=:id AND accepted_at IS NULL"
        ), {"id": sibling.request.assignment_id})
    sibling.envelope = await invoked_completion(sibling)
    return sibling


async def test_public_pages_exclude_pre_snapshot_uncommitted_record_after_it_commits(
    tmp_path, auth_database_env, admin_access, live_acceptance_lifecycle, monkeypatch,
):
    async with authorized_submitter_source(tmp_path, auth_database_env, paid=True) as h:
        signed_access = admin_access.signed
        reader = admin_access.target
        path = export_path(h.submitter_record.project_id)
        grant = await signed_access.grant(admin_access.admin, reader, role="project_manager",
                                  project_id=h.submitter_record.project_id)
        second = await sibling_ready(h)
        async with h.factory() as session, session.begin():
            second_outcome = await apply_outcome(session, second, 2)
        late = await sibling_ready(h)
        established, proceed = asyncio.Event(), asyncio.Event()
        original = AdminAuthorizationRepository.lock_project
        name = "pilot10-fixed-membership-first"

        async def before_project_lock(repository, project_id):
            if asyncio.current_task().get_name() == name:
                assert await repository._session.scalar(text("SHOW transaction_isolation")) == "repeatable read"
                established.set()
                await proceed.wait()
            return await original(repository, project_id)

        # Use project read so the existing AUTH locks establish the RR snapshot
        # before waiting for the producer's project lock. The producer already
        # inserted its real record before the first export starts.
        monkeypatch.setattr(AdminAuthorizationRepository, "lock_project", before_project_lock)
        async with h.factory() as producer:
            await producer.begin()
            late_outcome = await apply_outcome(producer, late, 2)
            task = asyncio.create_task(signed_access.client.get(
                path, params={"page_size": 1}, headers=reader.headers,
            ), name=name)
            try:
                await asyncio.wait_for(established.wait(), 30)
                await producer.commit()
                proceed.set()
                first = await asyncio.wait_for(task, 30)
            finally:
                proceed.set()
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            assert first.status_code == 200, first.text
        export_id, retained_facts = await _assert_membership_guards(h, reader, late_outcome)
        cursor, ids = await _assert_cursor_membership(
            h, admin_access, reader, path, first, second_outcome, late_outcome,
        )
        await _assert_expired_cleanup_and_csv(
            h, reader, path, signed_access, export_id, retained_facts, ids, late_outcome,
        )
        revoked = await signed_access.client.post(
            f"/api/v1/admin-role-grants/{grant}/revoke",
            headers=admin_access.admin.headers | {"Idempotency-Key": str(new_record_id())},
            json={"reason": "Reauthorize every contribution continuation"},
        )
        assert revoked.status_code == 200, revoked.text
        denied = await signed_access.client.get(
            path, params={"page_size": 1, "cursor": cursor}, headers=reader.headers,
        )
        assert denied.status_code == 404, denied.text


async def _assert_membership_guards(h, reader, late_outcome):
    """Protect sealed membership and refuse incomplete private exports."""
    # The installed guards must protect the original selection even when a
    # later real contribution now exists and would match the same query.
    async with h.factory() as session:
        membership = await session.scalar(select(ContributionExportMembership).where(
            ContributionExportMembership.actor_profile_id == str(reader.id),
            ContributionExportMembership.project_id == h.submitter_record.project_id,
            ContributionExportMembership.page_size == 1,
        ).order_by(ContributionExportMembership.exported_at.desc()).limit(1))
        assert membership is not None and membership.sealed and membership.member_count == 2
        export_id = membership.id
        retained_facts = {table: await rows(session, table) for table in (
            "contribution_records", "compensation_awards", "final_acceptances",
        )}
        assert await session.scalar(select(func.count()).select_from(ContributionExportMember).where(
            ContributionExportMember.export_id == export_id,
        )) == 2
    for statement, parameters in (
        ("UPDATE contribution_export_memberships SET page_size=2 WHERE id=:export", {}),
        ("DELETE FROM contribution_export_memberships WHERE id=:export", {}),
        ("UPDATE contribution_export_members SET recorded_at=recorded_at + interval '1 second' "
         "WHERE export_id=:export", {}),
        ("DELETE FROM contribution_export_members WHERE export_id=:export", {}),
        ("INSERT INTO contribution_export_members (export_id, contribution_id, recorded_at) "
         "SELECT :export, id, created_at FROM contribution_records WHERE id=:late",
         {"late": late_outcome.economic.contribution_record_id}),
    ):
        async with h.factory() as session:
            with pytest.raises(IntegrityError) as rejected:
                async with session.begin():
                    await session.execute(text(statement), {"export": export_id} | parameters)
            assert rejected.value.orig.sqlstate == "23514"
    async with h.factory() as session:
        assert await session.scalar(select(func.count()).select_from(ContributionExportMember).where(
            ContributionExportMember.export_id == export_id,
        )) == 2
    async with h.factory() as session:
        await session.begin()
        await session.execute(text(
            "INSERT INTO contribution_export_memberships "
            "(id, actor_profile_id, audience, project_id, output_format, page_size, "
            "contribution_type, recorded_from, recorded_before, member_count, sealed, "
            "query_digest, exported_at, expires_at) "
            "SELECT :new, actor_profile_id, audience, project_id, output_format, page_size, "
            "contribution_type, recorded_from, recorded_before, 3, false, "
            "query_digest, exported_at, expires_at "
            "FROM contribution_export_memberships WHERE id=:export"
        ), {"new": new_record_id(), "export": export_id})
        with pytest.raises(IntegrityError) as unsealed:
            await session.commit()
        assert unsealed.value.orig.sqlstate == "23514"
        await session.rollback()
    return export_id, retained_facts


async def _assert_cursor_membership(h, admin_access, reader, path, first, second_outcome, late_outcome):
    """Bind continuations to query, authority and original visible records."""
    signed_access = admin_access.signed
    cursor = first.json()["next_cursor"]
    assert cursor is not None
    for changed in ({"page_size": 2}, {"format": "csv"}, {"contribution_type": "completed_review"}):
        invalid = await signed_access.client.get(
            path, params={"page_size": 1, "cursor": cursor} | changed, headers=reader.headers,
        )
        assert invalid.status_code == 422, invalid.text
        assert invalid.json()["error"]["code"] == "contribution_export_invalid_cursor"
    other = await signed_access.actor("other-membership-reader")
    await signed_access.grant(admin_access.admin, other, role="project_manager",
                              project_id=h.submitter_record.project_id)
    crossed = await signed_access.client.get(
        path, params={"page_size": 1, "cursor": cursor}, headers=other.headers,
    )
    assert crossed.status_code == 422, crossed.text
    ungranted = await signed_access.actor("ungranted-membership-reader")
    concealed = await signed_access.client.get(
        path, params={"page_size": 1, "cursor": cursor}, headers=ungranted.headers,
    )
    assert concealed.status_code == 404, concealed.text
    next_page = await signed_access.client.get(
        path, params={"page_size": 1, "cursor": cursor}, headers=reader.headers,
    )
    assert next_page.status_code == 200, next_page.text
    assert next_page.json()["next_cursor"] is None
    assert next_page.json()["exported_at"] == first.json()["exported_at"]
    ids = [row["contribution_id"] for page in (first, next_page) for row in page.json()["items"]]
    assert set(ids) == {str(h.submitter_record.id), str(second_outcome.economic.contribution_record_id)}
    assert str(late_outcome.economic.contribution_record_id) not in ids
    assert all(len(row["awards"]) == 2 for page in (first, next_page) for row in page.json()["items"])
    return cursor, ids


async def _assert_expired_cleanup_and_csv(h, reader, path, signed_access, export_id, retained_facts, ids, late_outcome):
    """Clean expired selections without changing facts and preserve CSV pages."""
    # Construct only private expiry metadata around the same real immutable
    # facts; no economic row or clock is changed. The next public first page
    # must remove this nonempty expired selection through its native cascade.
    expired_id = new_record_id()
    async with h.factory() as session, session.begin():
        await session.execute(text(
            "INSERT INTO contribution_export_memberships "
            "(id, actor_profile_id, audience, project_id, output_format, page_size, "
            "contribution_type, recorded_from, recorded_before, member_count, sealed, "
            "query_digest, exported_at, expires_at) "
            "SELECT :new, actor_profile_id, audience, project_id, output_format, page_size, "
            "contribution_type, recorded_from, recorded_before, 3, false, query_digest, "
            "exported_at - interval '16 minutes', expires_at - interval '16 minutes' "
            "FROM contribution_export_memberships WHERE id=:export"
        ), {"new": expired_id, "export": export_id})
        await session.execute(text(
            "INSERT INTO contribution_export_members (export_id, contribution_id, recorded_at) "
            "SELECT :export, id, created_at FROM contribution_records WHERE project_id=:project"
        ), {"export": expired_id, "project": h.submitter_record.project_id})
        await session.execute(text(
            "UPDATE contribution_export_memberships SET sealed=true WHERE id=:export"
        ), {"export": expired_id})
    fresh = await signed_access.client.get(path, headers=reader.headers)
    assert fresh.status_code == 200
    async with h.factory() as session:
        assert await session.get(ContributionExportMembership, expired_id) is None
        assert {table: await rows(session, table) for table in retained_facts} == retained_facts
        assert await session.scalar(select(func.count()).select_from(ContributionExportMember).where(
            ContributionExportMember.export_id == expired_id,
        )) == 0
    assert {row["contribution_id"] for row in fresh.json()["items"]} == set(ids) | {
        str(late_outcome.economic.contribution_record_id),
    }
    csv_rows, csv_origin, csv_cursor = [], None, None
    for page_number in range(3):
        params = {"page_size": 1, "format": "csv"}
        if csv_cursor is not None:
            params["cursor"] = csv_cursor
        csv_page = await signed_access.client.get(path, params=params, headers=reader.headers)
        assert csv_page.status_code == 200, csv_page.text
        if csv_origin is None:
            csv_origin = csv_page.headers["X-Workstream-Exported-At"]
        assert csv_page.headers["X-Workstream-Exported-At"] == csv_origin
        csv_rows.extend(csv.DictReader(StringIO(csv_page.text, newline="")))
        csv_cursor = csv_page.headers.get("X-Workstream-Next-Cursor")
        assert (csv_cursor is None) is (page_number == 2)
    assert {row["contribution_id"] for row in csv_rows} == {
        row["contribution_id"] for row in fresh.json()["items"]
    }
    assert len(csv_rows) == 6
    async with h.factory() as session:
        assert await session.scalar(select(func.count()).select_from(ContributionExportMembership)) >= 2
