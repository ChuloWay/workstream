"""Exact hidden provenance projections and retained management HTTP behavior."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.tasks import task_service
from app.core.config import get_settings
from app.db import session as db_session
from app.main import create_app
from app.modules.checkers.api.post_submit_catalogue import CompiledPostSubmitPolicy
from app.modules.tasks import schemas
from app.modules.tasks.models import WorkstreamTask
from app.modules.tasks.schemas import (
    AuditTaskLockedContext, ManagementTaskLockedContext,
    OperationalTaskLockedContext, PostSubmitPolicyBodySummary,
)
from app.modules.tasks.service import TaskLockedContextInvalid, TaskNotFound, TaskService
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.test_tasks import (
    task_database_env as task_database_env, task_client as task_client,
    auth_headers, create_active_project, create_draft_task, create_ready_task,
)

READS = (
    ("read_management_task_locked_context", ManagementTaskLockedContext),
    ("read_operational_task_locked_context", OperationalTaskLockedContext),
    ("read_audit_task_locked_context", AuditTaskLockedContext),
)
REFERENCE_FIELDS = {
    "task_id", "project_id", "locked_guide_version", "locked_guide_source_snapshot_id",
    "locked_guide_source_snapshot_hash", "locked_effective_project_submission_artifact_policy_id",
    "locked_effective_project_submission_artifact_policy_hash", "locked_pre_submit_checker_policy_id",
    "locked_pre_submit_checker_bundle_hash", "locked_post_submit_checker_policy_id",
    "locked_post_submit_checker_policy_version", "locked_post_submit_checker_policy_hash",
    "locked_review_policy_id", "locked_review_policy_generation", "locked_review_policy_hash",
    "locked_revision_policy_id", "locked_revision_policy_generation", "locked_revision_policy_hash",
    "locked_contribution_policy_version_id",
}
SUMMARY = "locked_post_submit_checker_policy_body_summary"
SUMMARY_FIELDS = {
    "schema_version", "default_checkers", "required_checkers", "warning_checkers",
    "execution_checkers", "blocking_severities",
}


def test_locked_context_contracts():
    values = {
        field: (new_record_id() if field.endswith("_id") else 1 if field.endswith("_generation")
                else "sha256:" + "1" * 64 if field.endswith("_hash") else "guide")
        for field in REFERENCE_FIELDS
    }
    summary = PostSubmitPolicyBodySummary(schema_version="1", default_checkers=(),
                                         required_checkers=("check_acceptance_criteria_present",),
                                         warning_checkers=(), execution_checkers=(), blocking_severities=("high",))
    for _, cls in READS:
        kwargs = {**values, **({SUMMARY: summary} if cls is ManagementTaskLockedContext else {})}
        result = cls(**kwargs)
        assert set(result.model_dump()) == REFERENCE_FIELDS | ({SUMMARY} if cls is ManagementTaskLockedContext else set())
        for field in REFERENCE_FIELDS:
            bad = " " if field.endswith("_version") else "bad" if field.endswith(("_id", "_hash")) else 0
            with pytest.raises(ValidationError):
                cls(**{**kwargs, field: bad})
        for extra in ({"source_ref": "private"}, {"base_amount": 99}, {"actor_id": new_record_id()}):
            with pytest.raises(ValidationError, match="extra_forbidden"):
                cls(**kwargs, **extra)
        with pytest.raises(ValidationError, match="frozen_instance"):
            result.task_id = new_record_id()
        if cls is not ManagementTaskLockedContext:
            with pytest.raises(ValidationError, match="extra_forbidden"):
                cls(**values, **{SUMMARY: summary})
    with pytest.raises(ValidationError, match="frozen_instance"):
        summary.required_checkers = ()
    with pytest.raises(ValidationError, match="tuple_type"):
        PostSubmitPolicyBodySummary(**{**summary.model_dump(), "required_checkers": ["mutable"]})


async def test_locked_context_invalid_selectors_before_sql():
    session = MagicMock(spec=AsyncSession)
    service = task_service(session, settings=get_settings())
    service._repo.lock_project_task = AsyncMock()
    service._load_locked_task_context = AsyncMock()
    for method, _ in READS:
        for invalid in (None, "bad", str(new_record_id()), 1, True):
            for project, task in ((invalid, new_record_id()), (new_record_id(), invalid)):
                with pytest.raises(ValueError, match="selectors are invalid"):
                    await getattr(service, method)(project, task)
    service._repo.lock_project_task.assert_not_awaited()
    service._load_locked_task_context.assert_not_awaited()
    session.scalar.assert_not_called()
    session.execute.assert_not_called()


async def test_locked_context_exact_scope_and_fields(task_client):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    async with factory() as session:
        stored = await session.get(WorkstreamTask, task["id"])
        expected = {field: str(getattr(stored, "id" if field == "task_id" else field))
                    if field.endswith("_id") else getattr(stored, field) for field in REFERENCE_FIELDS}
        compiled = CompiledPostSubmitPolicy.model_validate_json(json.dumps(stored.locked_post_submit_checker_policy_body))
        expected_summary = {field: getattr(compiled, field) for field in SUMMARY_FIELDS}
        expected_summary["blocking_severities"] = list(compiled.blocking_severities)
    for method, cls in READS:
        async with factory() as session:
            service = task_service(session, settings=get_settings())
            result = await getattr(service, method)(UUID(project["id"]), UUID(task["id"]))
            assert type(result) is cls
            body = result.model_dump(mode="json")
            assert set(body) == REFERENCE_FIELDS | ({SUMMARY} if cls is ManagementTaskLockedContext else set())
            assert {field: body[field] for field in REFERENCE_FIELDS} == expected
            if cls is ManagementTaskLockedContext:
                assert body[SUMMARY] == expected_summary
            with patch.object(service, "_load_locked_task_context", wraps=service._load_locked_task_context) as resolve:
                for project_id, task_id in ((new_record_id(), UUID(task["id"])), (UUID(project["id"]), new_record_id())):
                    with pytest.raises(TaskNotFound, match="task not found"):
                        await getattr(service, method)(project_id, task_id)
                resolve.assert_not_awaited()
    response = await task_client.get(f"/api/v1/tasks/{task['id']}/locked-context", headers=auth_headers())
    assert response.status_code == 200, response.text
    assert response.json() == {**expected, SUMMARY: expected_summary}


async def test_locked_context_invalid_custody(task_client):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    draft = await create_draft_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    for method, cls in READS:
        async with factory() as session:
            service = task_service(session, settings=get_settings())
            assert type(await getattr(service, method)(UUID(project["id"]), UUID(task["id"]))) is cls
            with pytest.raises(TaskLockedContextInvalid, match="incomplete"):
                await getattr(service, method)(UUID(project["id"]), UUID(draft["id"]))
    async with factory() as session, session.begin():
        row = await session.get(WorkstreamTask, task["id"])
        row.locked_post_submit_checker_policy_body = {**row.locked_post_submit_checker_policy_body, "blocking_severities": []}
    for method, _ in READS:
        async with factory() as session:
            row = await session.get(WorkstreamTask, task["id"])
            assert row.locked_post_submit_checker_policy_body["blocking_severities"] == []
            with pytest.raises(TaskLockedContextInvalid, match="custody is invalid") as error:
                await getattr(task_service(session, settings=get_settings()), method)(UUID(project["id"]), UUID(task["id"]))
            assert error.value.code == "task_locked_context_invalid"


async def test_locked_context_preserves_caller_transaction(task_client):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    for method, _ in READS:
        pending_id = str(new_record_id())
        async with factory() as session, session.begin():
            row = await session.get(WorkstreamTask, task["id"])
            original = row.title
            row.title = "caller-uncommitted-marker"
            await session.flush()
            pending = WorkstreamTask(id=pending_id, project_id=project["id"])
            session.add(pending)
            result = await getattr(task_service(session, settings=get_settings()), method)(UUID(project["id"]), UUID(task["id"]))
            assert result.task_id == UUID(task["id"])
            assert pending in session.new and session.in_transaction()
            assert row.title == "caller-uncommitted-marker"
            await session.rollback()
        async with factory() as observer:
            assert (await observer.get(WorkstreamTask, task["id"])).title == original
            assert await observer.get(WorkstreamTask, pending_id) is None


async def test_locked_context_waits_for_task_before_projects(task_client):
    project = await create_active_project(task_client)
    task = await create_ready_task(task_client, project["id"])
    factory = db_session.get_session_factory()
    name = "locked-context-" + new_record_id().hex
    async with factory() as writer, factory() as reader:
        stored = await reader.get(WorkstreamTask, task["id"])
        original_body = stored.locked_post_submit_checker_policy_body.copy()
        await reader.execute(text("select set_config('application_name', :name, true)"), {"name": name})
        reader_pid = await reader.scalar(text("select pg_backend_pid()"))
        row = await writer.scalar(select(WorkstreamTask).where(WorkstreamTask.id == task["id"]).with_for_update())
        writer_pid = await writer.scalar(text("select pg_backend_pid()"))
        row.locked_post_submit_checker_policy_body = {**original_body, "blocking_severities": []}
        await writer.flush()
        service = task_service(reader, settings=get_settings())
        with patch.object(service._project_contexts, "lock_locked_policy_context", wraps=service._project_contexts.lock_locked_policy_context) as resolve:
            pending = asyncio.create_task(service.read_management_task_locked_context(UUID(project["id"]), UUID(task["id"])))
            try:
                await asyncio.wait_for(wait_for_named_database_lock(
                    get_settings().database_url, name, expected_waiter_pid=reader_pid,
                    expected_blocker_pid=writer_pid,
                ), timeout=10)
                resolve.assert_not_awaited()
                assert not pending.done() and stored.locked_post_submit_checker_policy_body == original_body
                await writer.commit()
                with pytest.raises(TaskLockedContextInvalid, match="custody is invalid"):
                    await asyncio.wait_for(pending, timeout=10)
                resolve.assert_awaited_once()
                assert stored.locked_post_submit_checker_policy_body["blocking_severities"] == []
            finally:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)


def test_locked_context_public_surface_and_removed_symbols():
    schema = create_app().openapi()
    operation = schema["paths"]["/api/v1/tasks/{task_id}/locked-context"]["get"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ManagementTaskLockedContext",
    }
    assert "OperationalTaskLockedContext" not in schema["components"]["schemas"]
    assert "AuditTaskLockedContext" not in schema["components"]["schemas"]
    assert "TaskLockedContextResponse" not in schema["components"]["schemas"]
    assert not hasattr(schemas, "TaskLockedContextResponse")
    assert not hasattr(TaskService, "_locked_context_response")
    assert set(schema["components"]["schemas"]["ManagementTaskLockedContext"]["properties"]) == REFERENCE_FIELDS | {SUMMARY}
