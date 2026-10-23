"""Public project catalogue proofs against current PostgreSQL authority."""

import asyncio
import base64
import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.config import decode_pagination_cursor_hmac_secret, get_settings
from app.core.hashing import canonical_json_hash
from app.db import session as db_session
from app.modules.authorization.models import AdminRoleGrant
from app.modules.authorization.pagination import AuthorizationIdCursorCodec
from app.modules.projects.project_summaries import ProjectSummaryReader
from app.modules.tasks.models import AuditEvent
from tests.project_create_fixtures import grant_fixture_admin_role
from tests.test_tasks import actor_id, auth_headers, set_dev_actor


pytest_plugins = ("tests.test_tasks",)


PATH = "/api/v1/projects"
MANAGER = "project-manager-subject"


async def _project(client, slug):
    response = await client.post(
        PATH,
        headers=auth_headers(),
        json={
            "name": f"Catalogue {slug}",
            "slug": slug,
            "description": "Catalogue fixture",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _admit_and_grant(client, monkeypatch, subject, role, *, scope="system", project_id=None):
    set_dev_actor(monkeypatch, roles="", subject=subject)
    admission = await client.get("/api/v1/actors/me", headers=auth_headers())
    assert admission.status_code == 200, admission.text
    async with db_session.get_session_factory()() as session, session.begin():
        return await grant_fixture_admin_role(
            session,
            await actor_id(subject),
            role=role,
            scope=scope,
            project_id=project_id,
        )


@pytest.mark.parametrize(
    "role", ["project_manager", "operator", "finance_authority", "audit_authority"]
)
async def test_each_existing_system_project_reader_sees_only_minimal_identity(
    task_client,
    monkeypatch,
    role,
):
    first = await _project(task_client, f"catalogue-first-{role.replace('_', '-')}")
    second = await _project(task_client, f"catalogue-second-{role.replace('_', '-')}")
    subject = f"catalogue-{role}"
    grant = await _admit_and_grant(task_client, monkeypatch, subject, role)
    response = await task_client.get(PATH, headers=auth_headers())
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["next_cursor"] is None
    assert {row["project_id"] for row in page["items"]} == {first["id"], second["id"]}
    assert all(set(row) == {"project_id", "name", "status"} for row in page["items"])
    reader_id = await actor_id(subject)
    async with db_session.get_session_factory()() as session:
        decisions = (
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.actor_id == reader_id,
                    AuditEvent.action_id == "project.catalogue.list",
                )
            )
        ).all()
    assert len(decisions) == 1
    assert decisions[0].event_type == "SensitiveAuthorizationAllowed"
    assert decisions[0].permission_id == "project.read"
    assert decisions[0].matched_grant_id == str(grant.id)
    assert decisions[0].resource_type is None and decisions[0].resource_id is None
    assert decisions[0].project_id is None
    assert decisions[0].after_facts["resource_context_digest"].startswith("sha256:")
    own = await task_client.get("/api/v1/actors/me/projects", headers=auth_headers())
    assert own.status_code == 200 and own.json()["items"] == []
    if role == "project_manager":
        await _admit_and_grant(
            task_client,
            monkeypatch,
            subject,
            role,
            scope="project",
            project_id=first["id"],
        )
        overlap = await task_client.get(PATH, headers=auth_headers())
        assert overlap.status_code == 200
        assert [row["project_id"] for row in overlap.json()["items"]] == sorted(
            [first["id"], second["id"]]
        )
        own = await task_client.get("/api/v1/actors/me/projects", headers=auth_headers())
        assert [row["project_id"] for row in own.json()["items"]] == [first["id"]]


async def test_exact_project_grant_and_access_administrator_alone_do_not_enumerate(
    task_client,
    monkeypatch,
):
    project = await _project(task_client, "catalogue-exact-negative")
    for role, scope in (("project_manager", "project"), ("access_administrator", "system")):
        await _admit_and_grant(
            task_client,
            monkeypatch,
            f"catalogue-negative-{role}",
            role,
            scope=scope,
            project_id=project["id"] if scope == "project" else None,
        )
        if scope == "project":
            own = await task_client.get("/api/v1/actors/me/projects", headers=auth_headers())
            assert own.status_code == 200, own.text
            assert [item["project_id"] for item in own.json()["items"]] == [project["id"]]
        response = await task_client.get(PATH, headers=auth_headers())
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "project_authorization_resource_not_found"


@pytest.mark.parametrize("role", ["submitter", "reviewer", None])
async def test_contributor_or_unrelated_actor_cannot_enumerate(task_client, monkeypatch, role):
    project = await _project(task_client, f"catalogue-contributor-{role or 'none'}")
    subject = f"catalogue-contributor-{role or 'none'}"
    set_dev_actor(monkeypatch, roles="viewer", subject=subject)
    admission = await task_client.get("/api/v1/actors/me", headers=auth_headers())
    assert admission.status_code == 200
    if role is not None:
        set_dev_actor(monkeypatch, roles="project_manager", subject=MANAGER)
        issued = await task_client.post(
            f"/api/v1/projects/{project['id']}/role-grants",
            headers=auth_headers(),
            json={
                "target_actor_profile_id": admission.json()["actor_profile_id"],
                "role": role,
                "qualification": {
                    "skills_snapshot": {
                        "availability": "unavailable",
                        "reference_ids": [],
                        "unavailable_reason": "no_record",
                    },
                    "reputation_snapshot": {
                        "availability": "unavailable",
                        "reference_ids": [],
                        "unavailable_reason": "no_record",
                    },
                    "prior_project_work_refs": [],
                    "external_expertise_refs": [],
                },
                "reason": "Exact contributor role is not system catalogue authority",
            },
        )
        assert issued.status_code == 201, issued.text
        set_dev_actor(monkeypatch, roles="viewer", subject=subject)
    response = await task_client.get(PATH, headers=auth_headers())
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "project_authorization_resource_not_found"


async def test_page_cursor_is_actor_and_query_bound_and_authority_is_refreshed(
    task_client,
    monkeypatch,
):
    projects = [await _project(task_client, f"catalogue-page-{index}") for index in range(3)]
    first = await task_client.get(PATH, params={"limit": 1}, headers=auth_headers())
    assert first.status_code == 200, first.text
    cursor = first.json()["next_cursor"]
    assert cursor is not None
    ids = [first.json()["items"][0]["project_id"]]
    while cursor is not None:
        response = await task_client.get(
            PATH, params={"limit": 1, "cursor": cursor}, headers=auth_headers()
        )
        assert response.status_code == 200, response.text
        ids.extend(row["project_id"] for row in response.json()["items"])
        cursor = response.json()["next_cursor"]
    assert ids == sorted(row["id"] for row in projects)
    envelope = json.loads(
        base64.urlsafe_b64decode(
            first.json()["next_cursor"] + "=" * (-len(first.json()["next_cursor"]) % 4),
        )
    )
    assert set(envelope) == {"p", "s"}
    assert set(envelope["p"]) == {"v", "q", "id"}
    assert envelope["p"]["id"] == ids[0]
    assert "created_at" not in json.dumps(envelope)

    other_action_digest = canonical_json_hash(
        {
            "action_id": "project.read",
            "actor_profile_id": str(await actor_id(MANAGER)),
            "limit": 1,
            "order": "id_asc",
        }
    )
    secret = get_settings().pagination_cursor_hmac_secret
    assert secret is not None
    foreign_action_cursor = AuthorizationIdCursorCodec(
        decode_pagination_cursor_hmac_secret(secret),
    ).encode(query_digest=other_action_digest, resource_id=UUID(ids[0]))

    async def forbidden_read(self, *, after, limit):
        raise AssertionError("cursor decoding must precede project reads")

    with monkeypatch.context() as patched:
        patched.setattr(ProjectSummaryReader, "read_project_catalogue", forbidden_read)
        wrong_action = await task_client.get(
            PATH,
            params={"limit": 1, "cursor": foreign_action_cursor},
            headers=auth_headers(),
        )
    assert wrong_action.status_code == 422
    assert wrong_action.json()["error"]["code"] == "project_catalogue_cursor_invalid"
    bad_limit = await task_client.get(
        PATH, params={"limit": 2, "cursor": first.json()["next_cursor"]}, headers=auth_headers()
    )
    assert bad_limit.status_code == 422
    assert bad_limit.json()["error"]["code"] == "project_catalogue_cursor_invalid"
    tampered = first.json()["next_cursor"]
    middle = len(tampered) // 2
    tampered = (
        tampered[:middle] + ("A" if tampered[middle] != "A" else "B") + tampered[middle + 1 :]
    )
    forged = await task_client.get(
        PATH, params={"limit": 1, "cursor": tampered}, headers=auth_headers()
    )
    assert forged.status_code == 422

    await _admit_and_grant(task_client, monkeypatch, "catalogue-second-reader", "audit_authority")
    other = await task_client.get(
        PATH, params={"limit": 1, "cursor": first.json()["next_cursor"]}, headers=auth_headers()
    )
    assert other.status_code == 422
    set_dev_actor(monkeypatch, roles="", subject=MANAGER)
    async with db_session.get_session_factory()() as session, session.begin():
        grant = await session.scalar(
            select(AdminRoleGrant).where(
                AdminRoleGrant.target_actor_profile_id == await actor_id(MANAGER),
                AdminRoleGrant.role == "project_manager",
                AdminRoleGrant.scope_type == "system",
                AdminRoleGrant.status == "active",
            )
        )
        assert grant is not None
        grant.status = "revoked"
        grant.version = 2
        grant.revoked_by_actor_profile_id = grant.granted_by_actor_profile_id
        grant.revoked_by_admin_role_grant_id = grant.granted_by_admin_role_grant_id
        grant.revoked_reason = "Catalogue test revocation"
        from datetime import UTC, datetime

        grant.revoked_at = datetime.now(UTC)
    refused = await task_client.get(
        PATH, params={"limit": 1, "cursor": first.json()["next_cursor"]}, headers=auth_headers()
    )
    assert refused.status_code == 404, refused.text


async def test_in_flight_page_holds_matched_grant_until_response_transaction_commits(
    task_client,
    monkeypatch,
):
    await _project(task_client, "catalogue-locking")
    manager_id = await actor_id(MANAGER)
    async with db_session.get_session_factory()() as session:
        grant_id = await session.scalar(
            select(AdminRoleGrant.id).where(
                AdminRoleGrant.target_actor_profile_id == manager_id,
                AdminRoleGrant.role == "project_manager",
                AdminRoleGrant.scope_type == "system",
                AdminRoleGrant.status == "active",
            )
        )
    assert grant_id is not None
    entered, release = asyncio.Event(), asyncio.Event()
    original = ProjectSummaryReader.read_project_catalogue

    async def held_read(self, *, after, limit):
        entered.set()
        await release.wait()
        return await original(self, after=after, limit=limit)

    monkeypatch.setattr(ProjectSummaryReader, "read_project_catalogue", held_read)
    first = asyncio.create_task(task_client.get(PATH, headers=auth_headers()))
    await asyncio.wait_for(entered.wait(), 20)

    async def revoke():
        async with db_session.get_session_factory()() as session, session.begin():
            grant = await session.get(AdminRoleGrant, grant_id, with_for_update=True)
            assert grant is not None
            grant.status = "revoked"
            grant.version = 2
            grant.revoked_by_actor_profile_id = grant.granted_by_actor_profile_id
            grant.revoked_by_admin_role_grant_id = grant.granted_by_admin_role_grant_id
            grant.revoked_reason = "Catalogue lock regression"
            from datetime import UTC, datetime

            grant.revoked_at = datetime.now(UTC)

    revocation = asyncio.create_task(revoke())
    try:
        await asyncio.sleep(0.2)
        assert not revocation.done(), "revocation committed before the read released its grant"
    finally:
        release.set()
    assert (await asyncio.wait_for(first, 20)).status_code == 200
    await asyncio.wait_for(revocation, 20)
    refused = await task_client.get(PATH, headers=auth_headers())
    assert refused.status_code == 404


async def test_invalid_owner_projection_rolls_back_authorization_evidence(task_client, monkeypatch):
    project = await _project(task_client, "catalogue-invalid-projection")

    async def invalid_read(self, *, after, limit):
        return (
            SimpleNamespace(
                project_id=UUID(project["id"]),
                name="Invalid projection",
                status="not-a-project-status",
            ),
        ), False

    monkeypatch.setattr(ProjectSummaryReader, "read_project_catalogue", invalid_read)
    response = await task_client.get(PATH, headers=auth_headers())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "project_catalogue_unavailable"
    async with db_session.get_session_factory()() as session:
        count = (
            await session.scalars(
                select(AuditEvent.id).where(
                    AuditEvent.action_id == "project.catalogue.list",
                )
            )
        ).all()
    assert count == []
