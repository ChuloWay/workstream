"""Real public pages freeze visible membership and reauthorize continuation."""

import asyncio

from sqlalchemy import func, select, text

from app.core.identifiers import new_record_id
from app.modules.contributions.records.export_models import ContributionExportMembership
from app.modules.authorization.repository import AdminAuthorizationRepository
from tests.contributions.records.support import authorized_submitter_source
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
        fresh = await signed_access.client.get(path, headers=reader.headers)
        assert fresh.status_code == 200
        assert {row["contribution_id"] for row in fresh.json()["items"]} == set(ids) | {
            str(late_outcome.economic.contribution_record_id),
        }
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(ContributionExportMembership)) >= 2
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
