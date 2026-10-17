"""Project Manager task-list filters select exact owner facts under the same signed pages."""

from sqlalchemy import func, select, text

from app.db import session as db_session
from tests.tasks.test_task_import_batches import _batch_path, _verified_source
from tests.tasks.test_task_import_contract import document
from tests.test_task_import_sources import import_source_client as import_source_client, _project
from tests.test_tasks import (
    actor_id, auth_headers, complete_task_payload, create_active_project, create_draft_task,
    create_ready_task, create_started_task, set_dev_actor, task_client as task_client,
    task_database_env as task_database_env,
)


async def _ids(client, project, **params):
    response = await client.get(f"/api/v1/projects/{project}/tasks", params=params, headers=auth_headers())
    assert response.status_code == 200, response.text
    return sorted(item["task_id"] for item in response.json()["items"])


async def test_import_batch_filter_selects_native_membership_only(import_source_client):
    client = import_source_client
    project = await _project(client)
    source = await _verified_source(client, project, document())
    imported = await client.post(_batch_path(project), headers=auth_headers(), json={"source_id": source["source_id"]})
    assert imported.status_code == 201, imported.text
    batch = imported.json()
    spoofed = await client.post(f"/api/v1/projects/{project}/tasks", headers=auth_headers(),
                                json=complete_task_payload() | {"import_batch_id": batch["batch_id"]})
    assert spoofed.status_code == 201, spoofed.text
    selected = await _ids(client, project, import_batch_id=batch["batch_id"])
    assert selected == sorted(task["id"] for task in batch["tasks"])
    assert spoofed.json()["id"] not in selected


async def test_status_assignee_and_updated_since_filters_are_exact(task_client, monkeypatch):
    project = (await create_active_project(task_client))["id"]
    started = (await create_started_task(task_client, project, monkeypatch))["id"]
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    ready = (await create_ready_task(task_client, project))["id"]
    draft = (await create_draft_task(task_client, project))["id"]
    assert await _ids(task_client, project, status="ready") == [ready]
    assert await _ids(task_client, project, status="draft") == [draft]
    assert await _ids(task_client, project, assignee_actor_id=await actor_id("worker-one")) == [started]
    async with db_session.get_session_factory()() as session, session.begin():
        since = await session.scalar(select(func.clock_timestamp()))
    async with db_session.get_session_factory()() as session, session.begin():
        await session.execute(text("UPDATE public.workstream_tasks SET status=status WHERE id=:id"), {"id": draft})
    assert await _ids(task_client, project, updated_since=since.isoformat()) == [draft]
    invalid = await task_client.get(f"/api/v1/projects/{project}/tasks", params={"status": "finished"},
                                    headers=auth_headers())
    assert invalid.status_code == 422


async def test_filtered_cursor_is_bound_to_its_filters(task_client, monkeypatch):
    project = (await create_active_project(task_client))["id"]
    ready = sorted([(await create_ready_task(task_client, project))["id"] for _ in range(2)])
    path = f"/api/v1/projects/{project}/tasks"
    first = await task_client.get(path, params={"status": "ready", "limit": 1}, headers=auth_headers())
    assert first.status_code == 200, first.text
    cursor = first.json()["next_cursor"]
    second = await task_client.get(path, params={"status": "ready", "limit": 1, "cursor": cursor},
                                   headers=auth_headers())
    assert sorted(item["task_id"] for page in (first, second) for item in page.json()["items"]) == ready
    for params in ({}, {"status": "draft"}):
        moved = await task_client.get(path, params={"limit": 1, "cursor": cursor} | params, headers=auth_headers())
        assert moved.status_code == 422, (params, moved.text)
