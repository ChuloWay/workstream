"""Public guide/policy replay admission against current PostgreSQL authority."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.authorization.models import AdminRoleGrant
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.projects.models import (
    GuideMutationIdempotencyRecord,
    PolicyMutationIdempotencyRecord,
    ProjectGuide,
    ReviewPolicy,
    RevisionPolicy,
)
from app.modules.projects.guide_mutation_repository import GuideMutationRepository
from app.modules.projects.policy_mutation_replay_repository import (
    PolicyMutationReplayRepository,
)
from app.modules.projects.policy_mutation_service import policy_selector_etag
from app.modules.tasks.models import AuditEvent
from projects.client_fixtures import (
    auth_headers,
    ensure_access_administrator_bootstrap,
    project_client as project_client,
    project_database_env as project_database_env,
)
from projects.guide_fixtures import complete_guide_payload, create_guide, create_project


async def _selected_policies(guide_id: str) -> tuple[ReviewPolicy, RevisionPolicy]:
    async with db_session.get_session_factory()() as session:
        guide = await session.get(ProjectGuide, guide_id)
        assert guide is not None
        review = await session.get(ReviewPolicy, guide.selected_review_policy_id)
        revision = await session.get(RevisionPolicy, guide.selected_revision_policy_id)
        assert review is not None and revision is not None
        return review, revision


async def _product_counts(project_id: str, guide_id: str) -> tuple[int, int, int, int]:
    async with db_session.get_session_factory()() as session:
        return (
            await session.scalar(
                select(func.count())
                .select_from(GuideMutationIdempotencyRecord)
                .where(
                    GuideMutationIdempotencyRecord.project_id == project_id,
                    GuideMutationIdempotencyRecord.resource_id == guide_id,
                    GuideMutationIdempotencyRecord.action_id == "project.guide.update",
                )
            ),
            await session.scalar(
                select(func.count())
                .select_from(PolicyMutationIdempotencyRecord)
                .where(
                    PolicyMutationIdempotencyRecord.project_id == project_id,
                    PolicyMutationIdempotencyRecord.guide_id == guide_id,
                )
            ),
            await session.scalar(
                select(func.count())
                .select_from(ReviewPolicy)
                .where(
                    ReviewPolicy.project_id == project_id,
                )
            ),
            await session.scalar(
                select(func.count())
                .select_from(RevisionPolicy)
                .where(
                    RevisionPolicy.project_id == project_id,
                )
            ),
        )


async def _request(client, case, *, key=None, project_id=None, if_match=None):
    headers = auth_headers() | {"Idempotency-Key": str(key or case["key"])}
    if case["if_match"] is not None:
        headers["If-Match"] = if_match or case["if_match"]
    path = case["path"].replace(case["project_id"], project_id or case["project_id"])
    return await getattr(client, case["method"])(path, headers=headers, json=case["body"])


async def test_exact_guide_and_policy_receipts_require_current_actor_link_and_project_grant(
    project_client,
) -> None:
    project = await create_project(project_client)
    foreign = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    review, revision = await _selected_policies(guide["id"])
    cases = [
        {
            "method": "patch",
            "project_id": project["id"],
            "path": f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
            "body": {"change_summary": "Exact old draft edit"},
            "if_match": None,
            "key": uuid4(),
        },
        {
            "method": "put",
            "project_id": project["id"],
            "path": f"/api/v1/projects/{project['id']}/guides/{guide['id']}/review-policy",
            "body": {
                "review_preference_window_seconds": 4200,
                "review_lease_duration_seconds": 1800,
            },
            "if_match": policy_selector_etag(
                review.id, review.policy_generation, review.policy_hash
            ),
            "key": uuid4(),
        },
        {
            "method": "put",
            "project_id": project["id"],
            "path": f"/api/v1/projects/{project['id']}/guides/{guide['id']}/revision-policy",
            "body": {"max_revision_rounds": 5, "revision_deadline_hours": 72},
            "if_match": policy_selector_etag(
                revision.id, revision.policy_generation, revision.policy_hash
            ),
            "key": uuid4(),
        },
    ]
    for case in cases:
        response = await _request(project_client, case)
        assert response.status_code == 200, response.text
        case["receipt"] = response.json()
        exact = await _request(project_client, case)
        assert exact.status_code == 200 and exact.json() == case["receipt"]
        wrong_project = await _request(project_client, case, project_id=foreign["id"])
        assert wrong_project.status_code == 409

    review_successor = await _request(
        project_client,
        cases[1],
        key=uuid4(),
        if_match=policy_selector_etag(
            cases[1]["receipt"]["id"],
            cases[1]["receipt"]["policy_generation"],
            cases[1]["receipt"]["policy_hash"],
        ),
    )
    revision_successor = await _request(
        project_client,
        cases[2],
        key=uuid4(),
        if_match=policy_selector_etag(
            cases[2]["receipt"]["id"],
            cases[2]["receipt"]["policy_generation"],
            cases[2]["receipt"]["policy_hash"],
        ),
    )
    guide_successor = await _request(project_client, cases[0], key=uuid4())
    assert all(
        response.status_code == 200
        for response in (review_successor, revision_successor, guide_successor)
    )
    for case in cases:
        exact = await _request(project_client, case)
        assert exact.status_code == 200 and exact.json() == case["receipt"]
    original_counts = await _product_counts(project["id"], guide["id"])

    actor_id, link_id, access_grant_id = await ensure_access_administrator_bootstrap()
    async with db_session.get_session_factory()() as session:
        grants = list(
            (
                await session.scalars(
                    select(AdminRoleGrant).where(
                        AdminRoleGrant.target_actor_profile_id == str(actor_id),
                        AdminRoleGrant.role == "project_manager",
                        AdminRoleGrant.status == "active",
                    )
                )
            ).all()
        )
        assert len(grants) >= 2
        for grant in grants:
            grant.status = "revoked"
            grant.version = 2
            grant.revoked_by_actor_profile_id = str(actor_id)
            grant.revoked_by_admin_role_grant_id = access_grant_id
            grant.revoked_reason = "Replay authorization regression"
            grant.revoked_at = datetime.now(UTC)
        await session.commit()
    for case in cases:
        denied = await _request(project_client, case)
        assert denied.status_code == 403, denied.text
        assert denied.json()["error"]["code"] == "permission_not_granted"
    async with db_session.get_session_factory()() as session:
        denials = (
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.event_type == "SensitiveAuthorizationDenied",
                    AuditEvent.project_id == project["id"],
                    AuditEvent.denial_code == "permission_not_granted",
                    AuditEvent.action_id.in_(
                        (
                            "project.guide.update",
                            "project.review_policy.update",
                            "project.revision_policy.update",
                        )
                    ),
                )
            )
        ).all()
        assert {denial.action_id for denial in denials} == {
            "project.guide.update",
            "project.review_policy.update",
            "project.revision_policy.update",
        }
    current_etags = [
        None,
        policy_selector_etag(
            review_successor.json()["id"],
            review_successor.json()["policy_generation"],
            review_successor.json()["policy_hash"],
        ),
        policy_selector_etag(
            revision_successor.json()["id"],
            revision_successor.json()["policy_generation"],
            revision_successor.json()["policy_hash"],
        ),
    ]
    for case, current_etag in zip(cases, current_etags, strict=True):
        denied = await _request(project_client, case, key=uuid4(), if_match=current_etag)
        assert denied.status_code == 403, denied.text

    async with db_session.get_session_factory()() as session:
        session.add(
            AdminRoleGrant(
                id=new_record_id(),
                target_actor_profile_id=str(actor_id),
                role="project_manager",
                scope_type="project",
                scope_project_id=foreign["id"],
                status="active",
                version=1,
                granted_by_actor_profile_id=str(actor_id),
                granted_by_admin_role_grant_id=access_grant_id,
                grant_reason="Test-only foreign project authority",
            )
        )
        await session.commit()
    for case in cases:
        denied = await _request(project_client, case)
        assert denied.status_code == 403, denied.text

    async with db_session.get_session_factory()() as session:
        session.add(
            AdminRoleGrant(
                id=new_record_id(),
                target_actor_profile_id=str(actor_id),
                role="project_manager",
                scope_type="project",
                scope_project_id=project["id"],
                status="active",
                version=1,
                granted_by_actor_profile_id=str(actor_id),
                granted_by_admin_role_grant_id=access_grant_id,
                grant_reason="Test-only restored exact project authority",
            )
        )
        profile = await session.get(ActorProfile, str(actor_id))
        assert profile is not None
        profile.status = "suspended"
        profile.suspended_by = str(actor_id)
        profile.suspended_at = datetime.now(UTC)
        profile.suspension_reason = "Replay authorization regression"
        await session.commit()
    for case in cases:
        denied = await _request(project_client, case)
        assert denied.status_code == 403, denied.text

    async with db_session.get_session_factory()() as session:
        profile = await session.get(ActorProfile, str(actor_id))
        link = await session.get(ActorIdentityLink, str(link_id))
        assert profile is not None and link is not None
        profile.status = "active"
        profile.suspended_by = None
        profile.suspended_at = None
        profile.suspension_reason = None
        profile.reactivated_by = str(actor_id)
        profile.reactivated_at = datetime.now(UTC)
        profile.reactivation_reason = "Replay authorization regression"
        link.status = "revoked"
        link.revoked_by = str(actor_id)
        link.revoked_at = datetime.now(UTC)
        link.revoked_reason = "Replay authorization regression"
        await session.commit()
    for case in cases:
        denied = await _request(project_client, case)
        assert denied.status_code == 403, denied.text
    assert await _product_counts(project["id"], guide["id"]) == original_counts


async def test_concurrent_same_key_policy_put_preserves_one_receipt(
    project_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    review, _revision = await _selected_policies(guide["id"])
    case = {
        "method": "put",
        "project_id": project["id"],
        "path": f"/api/v1/projects/{project['id']}/guides/{guide['id']}/review-policy",
        "body": {"review_preference_window_seconds": 4800, "review_lease_duration_seconds": 1900},
        "if_match": policy_selector_etag(review.id, review.policy_generation, review.policy_hash),
        "key": uuid4(),
    }
    both_at_reservation = asyncio.Event()
    release_reservations = asyncio.Event()
    original_reserve = PolicyMutationReplayRepository.reserve
    reservation_calls = 0

    async def overlap_reservations(self, **kwargs):
        nonlocal reservation_calls
        if kwargs["idempotency_key"] == case["key"]:
            reservation_calls += 1
            if reservation_calls == 2:
                both_at_reservation.set()
            await release_reservations.wait()
        return await original_reserve(self, **kwargs)

    monkeypatch.setattr(PolicyMutationReplayRepository, "reserve", overlap_reservations)
    first_task = asyncio.create_task(_request(project_client, case))
    second_task = asyncio.create_task(_request(project_client, case))
    try:
        await asyncio.wait_for(both_at_reservation.wait(), timeout=5)
    finally:
        release_reservations.set()
    first, second = await asyncio.gather(first_task, second_task)
    assert reservation_calls == 2
    assert first.status_code == second.status_code == 200, (first.text, second.text)
    assert first.json() == second.json()
    async with db_session.get_session_factory()() as session:
        record_count = await session.scalar(
            select(func.count())
            .select_from(PolicyMutationIdempotencyRecord)
            .where(
                PolicyMutationIdempotencyRecord.action_id == "project.review_policy.update",
                PolicyMutationIdempotencyRecord.idempotency_key == case["key"],
            )
        )
        version_count = await session.scalar(
            select(func.count())
            .select_from(ReviewPolicy)
            .where(
                ReviewPolicy.id == first.json()["id"],
            )
        )
        assert record_count == version_count == 1


@pytest.mark.parametrize("kind", ("review", "revision"))
async def test_policy_exact_replay_recovers_after_optimistic_miss_and_successor_commit(
    project_client, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    review, revision = await _selected_policies(guide["id"])
    predecessor = review if kind == "review" else revision
    case = {
        "method": "put",
        "project_id": project["id"],
        "path": f"/api/v1/projects/{project['id']}/guides/{guide['id']}/{kind}-policy",
        "body": (
            {
                "review_preference_window_seconds": 4800,
                "review_lease_duration_seconds": 1900,
            }
            if kind == "review"
            else {"max_revision_rounds": 5, "revision_deadline_hours": 72}
        ),
        "if_match": policy_selector_etag(
            predecessor.id, predecessor.policy_generation, predecessor.policy_hash
        ),
        "key": uuid4(),
    }
    original_find = PolicyMutationReplayRepository.find
    missed = asyncio.Event()
    release = asyncio.Event()
    second_task = None
    paused = False

    async def pause_after_miss(self, actor_profile_id, action_id, idempotency_key):
        nonlocal paused
        found = await original_find(self, actor_profile_id, action_id, idempotency_key)
        if asyncio.current_task() is second_task and found is None and not paused:
            paused = True
            missed.set()
            await release.wait()
        return found

    monkeypatch.setattr(PolicyMutationReplayRepository, "find", pause_after_miss)
    second_task = asyncio.create_task(_request(project_client, case))
    try:
        await asyncio.wait_for(missed.wait(), timeout=5)
        first = await _request(project_client, case)
        assert first.status_code == 200, first.text
        first_counts = await _product_counts(project["id"], guide["id"])
    finally:
        release.set()
    second = await asyncio.wait_for(second_task, timeout=5)
    assert second.status_code == 200 and second.json() == first.json(), second.text
    assert paused
    assert await _product_counts(project["id"], guide["id"]) == first_counts


async def test_guide_exact_replay_recovers_after_optimistic_miss_and_guide_lock(
    project_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    case = {
        "method": "patch",
        "project_id": project["id"],
        "path": f"/api/v1/projects/{project['id']}/guides/{guide['id']}",
        "body": {"change_summary": "One exact concurrent guide edit"},
        "if_match": None,
        "key": uuid4(),
    }
    original_find = GuideMutationRepository.find
    missed = asyncio.Event()
    release = asyncio.Event()
    second_task = None
    paused = False

    async def pause_after_miss(self, actor_profile_id, action_id, idempotency_key):
        nonlocal paused
        found = await original_find(self, actor_profile_id, action_id, idempotency_key)
        if asyncio.current_task() is second_task and found is None and not paused:
            paused = True
            missed.set()
            await release.wait()
        return found

    monkeypatch.setattr(GuideMutationRepository, "find", pause_after_miss)
    second_task = asyncio.create_task(_request(project_client, case))
    try:
        await asyncio.wait_for(missed.wait(), timeout=5)
        first = await _request(project_client, case)
        assert first.status_code == 200, first.text
        first_counts = await _product_counts(project["id"], guide["id"])
    finally:
        release.set()
    second = await asyncio.wait_for(second_task, timeout=5)
    assert second.status_code == 200 and second.json() == first.json(), second.text
    assert paused
    assert await _product_counts(project["id"], guide["id"]) == first_counts


async def test_policy_replay_waits_for_grant_revocation_then_denies(
    project_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    review, _revision = await _selected_policies(guide["id"])
    case = {
        "method": "put",
        "project_id": project["id"],
        "path": f"/api/v1/projects/{project['id']}/guides/{guide['id']}/review-policy",
        "body": {
            "review_preference_window_seconds": 4800,
            "review_lease_duration_seconds": 1900,
        },
        "if_match": policy_selector_etag(
            review.id, review.policy_generation, review.policy_hash
        ),
        "key": uuid4(),
    }
    created = await _request(project_client, case)
    assert created.status_code == 200, created.text
    original_counts = await _product_counts(project["id"], guide["id"])
    actor_id, _link_id, access_grant_id = await ensure_access_administrator_bootstrap()
    entered_actor_lock = asyncio.Event()
    entered_grant_query = asyncio.Event()
    original_lock = AdminAuthorizationRepository.lock_request_actor
    original_find = AdminAuthorizationRepository.find_effective_grant

    async def signal_actor_lock(self, identity_link_id, actor_profile_id, **kwargs):
        if actor_profile_id == actor_id:
            entered_actor_lock.set()
        return await original_lock(self, identity_link_id, actor_profile_id, **kwargs)

    async def signal_grant_query(self, actor_profile_id, permission_id, **kwargs):
        if (
            actor_profile_id == actor_id
            and str(kwargs.get("scope_project_id")) == project["id"]
            and kwargs.get("for_update")
        ):
            entered_grant_query.set()
        return await original_find(self, actor_profile_id, permission_id, **kwargs)

    monkeypatch.setattr(
        AdminAuthorizationRepository, "lock_request_actor", signal_actor_lock
    )
    monkeypatch.setattr(
        AdminAuthorizationRepository, "find_effective_grant", signal_grant_query
    )
    replay_task = None
    revocation_committed = False
    async with db_session.get_session_factory()() as revoker:
        grants = list(
            (
                await revoker.scalars(
                    select(AdminRoleGrant)
                    .where(
                        AdminRoleGrant.target_actor_profile_id == str(actor_id),
                        AdminRoleGrant.role == "project_manager",
                        AdminRoleGrant.status == "active",
                    )
                    .with_for_update()
                )
            ).all()
        )
        assert len(grants) >= 2
        for grant in grants:
            grant.status = "revoked"
            grant.version = 2
            grant.revoked_by_actor_profile_id = str(actor_id)
            grant.revoked_by_admin_role_grant_id = access_grant_id
            grant.revoked_reason = "Concurrent replay authorization regression"
            grant.revoked_at = datetime.now(UTC)
        await revoker.flush()
        try:
            replay_task = asyncio.create_task(_request(project_client, case))
            await asyncio.wait_for(entered_actor_lock.wait(), timeout=5)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(replay_task), timeout=0.1)
            await revoker.commit()
            revocation_committed = True
        finally:
            if not revocation_committed and replay_task is not None and not replay_task.done():
                await revoker.rollback()
                replay_task.cancel()
                await asyncio.gather(replay_task, return_exceptions=True)
    assert replay_task is not None
    denied = await asyncio.wait_for(replay_task, timeout=5)
    assert entered_grant_query.is_set()
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "permission_not_granted"
    assert await _product_counts(project["id"], guide["id"]) == original_counts
    async with db_session.get_session_factory()() as session:
        denials = (
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.event_type == "SensitiveAuthorizationDenied",
                    AuditEvent.action_id == "project.review_policy.update",
                    AuditEvent.project_id == project["id"],
                    AuditEvent.denial_code == "permission_not_granted",
                )
            )
        ).all()
        assert len(denials) == 1
