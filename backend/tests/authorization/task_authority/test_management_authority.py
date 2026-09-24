"""Fresh scoped manager authority, including receipt replay after revocation."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.modules.authorization.models import AdminRoleGrant
from app.modules.tasks.models import TaskCommandReceipt, WorkstreamTask
from tests.project_create_fixtures import grant_fixture_admin_role
from tests.test_tasks import (
    task_database_env as task_database_env,
    task_client as task_client,
    auth_headers,
    create_active_project,
    create_draft_task,
    complete_task_payload,
    set_dev_actor,
)


@pytest.mark.parametrize("operation", ["create", "screen", "release"])
async def test_manager_scope_and_revocation_govern_new_and_replayed_commands(
    task_client, monkeypatch, operation
):
    own = await create_active_project(task_client, slug="manager-own")
    foreign = await create_active_project(task_client, slug="manager-foreign")
    own_task = await create_draft_task(task_client, own["id"])
    foreign_task = await create_draft_task(task_client, foreign["id"])
    if operation == "release":
        for task in (own_task, foreign_task):
            response = await task_client.post(
                f"/api/v1/tasks/{task['id']}/screen", headers=auth_headers()
            )
            assert response.status_code == 200, response.text
    set_dev_actor(monkeypatch, roles="viewer", subject="scoped-task-manager")
    admitted = await task_client.get("/api/v1/actors/me", headers=auth_headers())
    assert admitted.status_code == 200, admitted.text
    actor_id = admitted.json()["actor_profile_id"]
    async with db_session.get_session_factory()() as session, session.begin():
        grant = await grant_fixture_admin_role(session, actor_id, project_id=own["id"])
        grant_id = grant.id
    paths = [
        f"/api/v1/projects/{project['id']}/tasks"
        if operation == "create"
        else f"/api/v1/tasks/{task['id']}/{operation}"
        for project, task in ((own, own_task), (foreign, foreign_task))
    ]
    payload = complete_task_payload() if operation == "create" else {"reason": "Manager release"}
    headers = auth_headers()
    denied = await task_client.post(paths[1], headers=headers, json=payload)
    assert denied.status_code == 403, denied.text
    allowed = await task_client.post(paths[0], headers=headers, json=payload)
    assert allowed.status_code == (201 if operation == "create" else 200), allowed.text
    async with db_session.get_session_factory()() as session, session.begin():
        grant = await session.get(AdminRoleGrant, grant_id, with_for_update=True)
        grant.status, grant.version = "revoked", 2
        grant.revoked_by_actor_profile_id = grant.granted_by_actor_profile_id
        grant.revoked_by_admin_role_grant_id = grant.granted_by_admin_role_grant_id
        grant.revoked_reason = "Withdraw management authority"
        grant.revoked_at = datetime.now(UTC)
    for retry_headers in (headers, auth_headers()):
        denied = await task_client.post(paths[0], headers=retry_headers, json=payload)
        assert denied.status_code == 403, denied.text
    async with db_session.get_session_factory()() as session:
        receipts = list(
            await session.scalars(
                select(TaskCommandReceipt).where(TaskCommandReceipt.actor_profile_id == actor_id)
            )
        )
        assert len(receipts) == 1 and receipts[0].status == "committed"
        unchanged = await session.get(WorkstreamTask, foreign_task["id"])
        assert unchanged.status == ("screening" if operation == "release" else "draft")
