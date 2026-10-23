"""Public project catalogue proofs against current PostgreSQL authority."""

import asyncio
import json
import os
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.modules.authorization.models import AdminRoleGrant
from app.modules.projects.project_summaries import ProjectSummaryReader
from app.modules.tasks.models import AuditEvent
from tests.project_create_fixtures import grant_fixture_admin_role
from tests.test_tasks import actor_id, auth_headers, set_dev_actor


pytest_plugins = ("tests.test_tasks",)


PATH = "/api/v1/projects"
MANAGER = "project-manager-subject"


async def _project(client, slug):
    response = await client.post(PATH, headers=auth_headers(), json={
        "name": f"Catalogue {slug}", "slug": slug, "description": "Catalogue fixture",
    })
    assert response.status_code == 201, response.text
    return response.json()


async def _admit_and_grant(client, monkeypatch, subject, role, *, scope="system", project_id=None):
    set_dev_actor(monkeypatch, roles="", subject=subject)
    admission = await client.get("/api/v1/actors/me", headers=auth_headers())
    assert admission.status_code == 200, admission.text
    async with db_session.get_session_factory()() as session, session.begin():
        return await grant_fixture_admin_role(
            session, await actor_id(subject), role=role, scope=scope, project_id=project_id,
        )


@pytest.mark.parametrize("role", ["project_manager", "operator", "finance_authority", "audit_authority"])
async def test_each_existing_system_project_reader_sees_only_minimal_identity(
    task_client, monkeypatch, role,
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
        decisions = (await session.scalars(select(AuditEvent).where(
            AuditEvent.actor_id == reader_id,
            AuditEvent.action_id == "project.catalogue.list",
        ))).all()
    assert len(decisions) == 1
    assert decisions[0].event_type == "SensitiveAuthorizationAllowed"
    assert decisions[0].permission_id == "project.read"
    assert decisions[0].matched_grant_id == str(grant.id)
    assert decisions[0].resource_type is None and decisions[0].resource_id is None
    assert decisions[0].project_id is None
    assert decisions[0].after_facts["resource_context_digest"].startswith("sha256:")


async def test_exact_project_grant_and_access_administrator_alone_do_not_enumerate(
    task_client, monkeypatch,
):
    project = await _project(task_client, "catalogue-exact-negative")
    for role, scope in (("project_manager", "project"), ("access_administrator", "system")):
        await _admit_and_grant(
            task_client, monkeypatch, f"catalogue-negative-{role}", role,
            scope=scope, project_id=project["id"] if scope == "project" else None,
        )
        if scope == "project":
            own = await task_client.get("/api/v1/actors/me/projects", headers=auth_headers())
            assert own.status_code == 200, own.text
            assert [item["project_id"] for item in own.json()["items"]] == [project["id"]]
        response = await task_client.get(PATH, headers=auth_headers())
        assert response.status_code == 404, response.text
        assert response.json()["error"]["code"] == "project_authorization_resource_not_found"


async def test_page_cursor_is_actor_and_query_bound_and_authority_is_refreshed(
    task_client, monkeypatch,
):
    projects = [await _project(task_client, f"catalogue-page-{index}") for index in range(3)]
    first = await task_client.get(PATH, params={"limit": 1}, headers=auth_headers())
    assert first.status_code == 200, first.text
    cursor = first.json()["next_cursor"]
    assert cursor is not None
    ids = [first.json()["items"][0]["project_id"]]
    while cursor is not None:
        response = await task_client.get(PATH, params={"limit": 1, "cursor": cursor}, headers=auth_headers())
        assert response.status_code == 200, response.text
        ids.extend(row["project_id"] for row in response.json()["items"])
        cursor = response.json()["next_cursor"]
    assert ids == [row["id"] for row in projects]
    bad_limit = await task_client.get(PATH, params={"limit": 2, "cursor": first.json()["next_cursor"]},
                                      headers=auth_headers())
    assert bad_limit.status_code == 422
    assert bad_limit.json()["error"]["code"] == "project_catalogue_cursor_invalid"
    tampered = first.json()["next_cursor"]
    middle = len(tampered) // 2
    tampered = tampered[:middle] + ("A" if tampered[middle] != "A" else "B") + tampered[middle + 1:]
    forged = await task_client.get(PATH, params={"limit": 1, "cursor": tampered},
                                   headers=auth_headers())
    assert forged.status_code == 422

    await _admit_and_grant(task_client, monkeypatch, "catalogue-second-reader", "audit_authority")
    other = await task_client.get(PATH, params={"limit": 1, "cursor": first.json()["next_cursor"]},
                                  headers=auth_headers())
    assert other.status_code == 422
    set_dev_actor(monkeypatch, roles="", subject=MANAGER)
    async with db_session.get_session_factory()() as session, session.begin():
        grant = await session.scalar(select(AdminRoleGrant).where(
            AdminRoleGrant.target_actor_profile_id == await actor_id(MANAGER),
            AdminRoleGrant.role == "project_manager", AdminRoleGrant.scope_type == "system",
            AdminRoleGrant.status == "active",
        ))
        assert grant is not None
        grant.status = "revoked"
        grant.version = 2
        grant.revoked_by_actor_profile_id = grant.granted_by_actor_profile_id
        grant.revoked_by_admin_role_grant_id = grant.granted_by_admin_role_grant_id
        grant.revoked_reason = "Catalogue test revocation"
        from datetime import UTC, datetime
        grant.revoked_at = datetime.now(UTC)
    refused = await task_client.get(PATH, params={"limit": 1, "cursor": first.json()["next_cursor"]},
                                    headers=auth_headers())
    assert refused.status_code == 404, refused.text


async def test_in_flight_page_holds_matched_grant_until_response_transaction_commits(
    task_client, monkeypatch,
):
    await _project(task_client, "catalogue-locking")
    manager_id = await actor_id(MANAGER)
    async with db_session.get_session_factory()() as session:
        grant_id = await session.scalar(select(AdminRoleGrant.id).where(
            AdminRoleGrant.target_actor_profile_id == manager_id,
            AdminRoleGrant.role == "project_manager", AdminRoleGrant.scope_type == "system",
            AdminRoleGrant.status == "active",
        ))
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
        return (SimpleNamespace(
            project_id=UUID(project["id"]), name="Invalid projection",
            status="not-a-project-status", created_at=None,
        ),), False

    monkeypatch.setattr(ProjectSummaryReader, "read_project_catalogue", invalid_read)
    response = await task_client.get(PATH, headers=auth_headers())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "project_catalogue_unavailable"
    async with db_session.get_session_factory()() as session:
        count = (await session.scalars(select(AuditEvent.id).where(
            AuditEvent.action_id == "project.catalogue.list",
        ))).all()
    assert count == []


async def test_built_cli_reads_actual_public_api_and_postgresql(task_client):
    """The native command is exercised against the real ASGI/PG owner, not a mock HTTP body."""
    executable = Path(os.environ["WORKSTREAM_CLI_EXECUTABLE"])
    assert executable.is_file()
    project = await _project(task_client, "catalogue-native-cli")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    server = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port),
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        async with httpx.AsyncClient(base_url=origin) as client:
            last_status = None
            for _ in range(600):
                if server.returncode is not None:
                    raise AssertionError(f"API process exited before readiness: {server.returncode}")
                try:
                    response = await client.get("/api/v1/health")
                    last_status = response.status_code
                    if response.status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                await asyncio.sleep(0.1)
            else:
                raise AssertionError(f"API readiness timed out; last status={last_status}")
        env = dict(os.environ, WORKSTREAM_API_URL=origin, WORKSTREAM_TOKEN="task-token")
        command = await asyncio.create_subprocess_exec(
            str(executable), "--output", "json", "project", "list", "--limit", "1",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
        )
        stdout, stderr = await asyncio.wait_for(command.communicate(), 20)
        assert command.returncode == 0, stderr.decode()
        page = json.loads(stdout)
        assert page["next_cursor"] is None
        assert page["items"] == [{
            "project_id": project["id"], "name": project["name"], "status": "draft",
        }]
        assert b"task-token" not in stdout + stderr
    finally:
        if server.returncode is None:
            server.terminate()
        await asyncio.wait_for(server.wait(), 20)
