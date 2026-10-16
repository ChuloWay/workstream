"""Signed keyset pages: stable order, no gaps or duplicates, exact updated_since."""

from sqlalchemy import func, select, text

from app.db import session as db_session
from tests.submission_fixtures import seed_retained_submission
from tests.test_tasks import (
    admit_and_grant_project_submitter, auth_headers, complete_submission_payload, create_active_project,
    set_dev_actor,
)
from .support import ME, MANAGER, OWNER, get_ok, start_another, submitted_case


async def _walk(client, path, key, **params):
    """Follow every continuation at page size one and return the ordered rows."""
    rows, cursor = [], None
    while True:
        page = await get_ok(client, path, limit=1, **params, **({"cursor": cursor} if cursor else {}))
        rows.extend(page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            return rows
        assert len(page["items"]) == 1, key


async def _clock():
    async with db_session.get_session_factory()() as session:
        return await session.scalar(select(func.clock_timestamp()))


async def _touch(table, ids):
    """A committed no-op update moves only the DB-maintained stamp."""
    async with db_session.get_session_factory()() as session, session.begin():
        await session.execute(text(f"UPDATE public.{table} SET status=status WHERE id = ANY(CAST(:ids AS uuid[]))"),
                              {"ids": ids})


async def _owner_tasks(client, monkeypatch, count):
    project, first, _submission = await submitted_case(client, monkeypatch)
    tasks = [first]
    for _ in range(count - 1):
        tasks.append(await start_another(client, monkeypatch, project))
    return project, tasks


async def test_assignment_pages_are_complete_ordered_and_exactly_incremental(task_client, monkeypatch):
    _project, tasks = await _owner_tasks(task_client, monkeypatch, 4)
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    rows = await _walk(task_client, f"{ME}/assignments", "assignment_id")
    assert sorted(row["task_id"] for row in rows) == sorted(tasks)
    assert len({row["assignment_id"] for row in rows}) == 4
    assert [row["updated_at"] for row in rows] == sorted(row["updated_at"] for row in rows)
    since = await _clock()
    changed = [rows[0]["assignment_id"], rows[2]["assignment_id"]]
    await _touch("task_assignments", changed)
    later = await _walk(task_client, f"{ME}/assignments", "assignment_id", updated_since=since.isoformat())
    assert sorted(row["assignment_id"] for row in later) == sorted(changed)


async def test_submission_pages_are_complete_ordered_and_exactly_incremental(task_client, monkeypatch):
    _project, tasks = await _owner_tasks(task_client, monkeypatch, 3)
    for index, task in enumerate(tasks[1:]):
        set_dev_actor(monkeypatch, roles="", subject=OWNER)
        await seed_retained_submission(task, complete_submission_payload(f"sha256:page-{index}"))
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    rows = await _walk(task_client, f"{ME}/submissions", "submission_id")
    assert sorted(row["task_id"] for row in rows) == sorted(tasks)
    assert [(row["updated_at"], row["submission_id"]) for row in rows] == sorted(
        (row["updated_at"], row["submission_id"]) for row in rows)
    since = await _clock()
    await _touch("submissions", [rows[1]["submission_id"]])
    later = await _walk(task_client, f"{ME}/submissions", "submission_id", updated_since=since.isoformat())
    assert [row["submission_id"] for row in later] == [rows[1]["submission_id"]]
    assert (await get_ok(task_client, f"{ME}/submissions", task_id=tasks[0]))["items"][0]["task_id"] == tasks[0]


async def test_cursor_is_bound_to_its_actor_and_filters(task_client, monkeypatch):
    project, _tasks = await _owner_tasks(task_client, monkeypatch, 2)
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    cursor = (await get_ok(task_client, f"{ME}/assignments", limit=1))["next_cursor"]
    assert cursor is not None
    for params in ({"state": "active"}, {"project_id": project}, {"limit": 2}):
        response = await task_client.get(
            f"{ME}/assignments", params={"limit": 1, "cursor": cursor} | params, headers=auth_headers(),
        )
        assert response.status_code == 422, (params, response.text)
        assert response.json()["error"]["code"] == "contributor_read_cursor_invalid"
    submissions = await task_client.get(f"{ME}/submissions", params={"limit": 1, "cursor": cursor},
                                        headers=auth_headers())
    assert submissions.status_code == 422


async def test_project_pages_follow_exact_grants(task_client, monkeypatch):
    first, _task, _submission = await submitted_case(task_client, monkeypatch)
    set_dev_actor(monkeypatch, roles="project_manager", subject=MANAGER)
    second = await create_active_project(task_client, slug="second-contributor-project")
    await admit_and_grant_project_submitter(task_client, monkeypatch, second["id"], OWNER)
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    rows = await _walk(task_client, f"{ME}/projects", "project_id")
    assert [row["project_id"] for row in rows] == [first, second["id"]]


async def test_active_assignment_changes_with_its_task(task_client, monkeypatch):
    _project, tasks = await _owner_tasks(task_client, monkeypatch, 2)
    set_dev_actor(monkeypatch, roles="", subject=OWNER)
    since = await _clock()
    await _touch("workstream_tasks", [tasks[1]])
    later = await _walk(task_client, f"{ME}/assignments", "assignment_id", updated_since=since.isoformat())
    assert [row["task_id"] for row in later] == [tasks[1]]
