"""Each contributor read is one REPEATABLE READ snapshot; integrity gaps are retryable 503s."""

import dataclasses

from sqlalchemy import text

from app.modules.checkers.selected_pre_submit_reads import SelectedPreSubmitRunReader
from app.modules.tasks.contributor_reads import ContributorWorkReader
from app.modules.tasks.repository import TaskRepository
from tests.test_tasks import auth_headers
from .support import ME, OWNER, as_actor, preparations_path, submitted_case


def _observe(owner, name, observed):
    original = getattr(owner, name)

    async def observing(reader, *args, **kwargs):
        observed.append(await reader._session.scalar(text("SHOW transaction_isolation")))
        return await original(reader, *args, **kwargs)

    return observing


async def test_work_and_preparation_reads_run_in_one_repeatable_read_snapshot(task_client, monkeypatch):
    _project, task, _submission = await submitted_case(task_client, monkeypatch)
    observed = []
    monkeypatch.setattr(ContributorWorkReader, "read_assignments",
                        _observe(ContributorWorkReader, "read_assignments", observed))
    monkeypatch.setattr(SelectedPreSubmitRunReader, "read_contributor_runs",
                        _observe(SelectedPreSubmitRunReader, "read_contributor_runs", observed))
    await as_actor(task_client, monkeypatch, OWNER)
    for path in (f"{ME}/assignments", preparations_path(task)):
        response = await task_client.get(path, headers=auth_headers())
        assert response.status_code == 200, response.text
    assert observed == ["repeatable read", "repeatable read"]


async def _unavailable(client, path):
    response = await client.get(path, headers=auth_headers())
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "contributor_read_unavailable"


async def test_assignment_without_locked_terms_is_a_retryable_unavailable_read(task_client, monkeypatch):
    await submitted_case(task_client, monkeypatch)

    async def no_terms(repository, project_id, version_ids):
        return {}

    monkeypatch.setattr(TaskRepository, "locked_compensation", no_terms)
    await as_actor(task_client, monkeypatch, OWNER)
    await _unavailable(task_client, f"{ME}/assignments")


async def test_completed_preparation_without_execution_facts_is_unavailable(task_client, monkeypatch):
    _project, task, _submission = await submitted_case(task_client, monkeypatch)
    original = SelectedPreSubmitRunReader.read_contributor_runs

    async def without_execution(reader, **kwargs):
        views, more = await original(reader, **kwargs)
        return tuple(dataclasses.replace(view, status="completed", terminal=None) for view in views), more

    monkeypatch.setattr(SelectedPreSubmitRunReader, "read_contributor_runs", without_execution)
    await as_actor(task_client, monkeypatch, OWNER)
    await _unavailable(task_client, preparations_path(task))
