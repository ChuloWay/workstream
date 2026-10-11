"""Public atomic JSON-to-DRAFT import with native AUTH, ART and Task custody."""

import asyncio
import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.db import session as db_session
from app.modules.artifacts.models import ArtifactTaskImportSource, ArtifactReplica
from app.modules.artifacts.task_import_sources import ArtifactTaskImportSourceCommands
from app.modules.authorization.task_import_sources import PreparedTaskImportSourceAuthorization
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.models import (
    AuditEvent, TaskCommandReceipt, TaskImportBatch, TaskImportBatchCommandReceipt,
    TaskImportBatchMember, WorkstreamTask,
)
from app.modules.tasks.task_import_batches import TaskImportBatchCommands
from tests.test_task_import_sources import (
    import_source_client as import_source_client, _declare, _path, _project,
)
from tests.test_tasks import (
    auth_headers, complete_task_payload, create_active_project, set_dev_actor,
    task_database_env as task_database_env,
)
from tests.tasks.test_task_import_contract import document


async def _verified_source(client, project, value):
    """Retain actual bytes through the existing public declaration and upload."""
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    source = await _declare(client, project, raw)
    uploaded = await client.put(_path(project, source) + "/content", content=raw,
                                headers=auth_headers() | {"Content-Type": "application/json"})
    assert uploaded.status_code == 200 and uploaded.json()["status"] == "verified", uploaded.text
    return source


def _batch_path(project):
    """Address the sole project-scoped public import owner."""
    return f"/api/v1/projects/{project}/task-import-batches"


async def _counts(project):
    """Observe committed batch, membership, retry, Task and CREATE effects."""
    async with db_session.get_session_factory()() as session:
        counts = [await session.scalar(select(func.count()).select_from(owner).where(owner.project_id == project))
                  for owner in (TaskImportBatch, TaskImportBatchMember, TaskImportBatchCommandReceipt, WorkstreamTask)]
        counts.append(await session.scalar(select(func.count()).select_from(TaskCommandReceipt).join(
            WorkstreamTask, WorkstreamTask.id == TaskCommandReceipt.task_id,
        ).where(WorkstreamTask.project_id == project, TaskCommandReceipt.action_id == "project.task.create")))
        counts.append(await session.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.event_payload["references"]["project_id"].as_string() == project,
            AuditEvent.event_type == "TaskCreated",
        )))
        return tuple(counts)


async def test_200_rows_create_one_native_batch_and_exact_task_evidence(import_source_client):
    """A real 200-row UTF-8 file creates 200 ordered DRAFT Tasks in one batch."""
    client, value = import_source_client, document(200)
    value["tasks"][0]["difficulty"] = "x" * 80
    project = await _project(client)
    source = await _verified_source(client, project, value)
    headers = auth_headers()
    response = await client.post(_batch_path(project), headers=headers, json={"source_id": source["source_id"]})
    assert response.status_code == 201, response.text
    result = response.json()
    assert (result["project_id"], result["source_id"], result["sha256"], result["byte_count"], result["row_count"]) == (
        project, source["source_id"], source["sha256"], source["byte_count"], 200,
    )
    assert result["label"] == value["metadata"]["label"]
    assert len({row["id"] for row in result["tasks"]}) == 200
    assert [row["external_task_id"] for row in result["tasks"]] == [row["external_task_id"] for row in value["tasks"]]
    assert all(row["status"] == "draft" and row["source_type"] == "json_import"
               and row["source_ref"] == f"task-import-source:{source['source_id']}"
               and row["source_payload_hash"] == source["sha256"]
               and row["import_batch_id"] == result["batch_id"] for row in result["tasks"])
    for instructions, task in zip(value["tasks"], result["tasks"], strict=True):
        assert {field: task[field] for field in instructions} == instructions
    assert await _counts(project) == (1, 200, 1, 200, 200, 200)
    async with db_session.get_session_factory()() as session:
        members = list(await session.scalars(select(TaskImportBatchMember).where(
            TaskImportBatchMember.batch_id == result["batch_id"],
        ).order_by(TaskImportBatchMember.row_index)))
        assert [member.task_id for member in members] == [row["id"] for row in result["tasks"]]
        for member in members:
            receipt = await session.get(TaskCommandReceipt, member.task_command_receipt_id)
            decision = await session.get(AuditEvent, member.authorization_decision_id)
            event = (await session.scalars(select(AuditEvent).where(
                AuditEvent.entity_id == member.task_id, AuditEvent.event_type == "TaskCreated",
            ))).one()
            assert receipt.response == member.response and receipt.status == "committed"
            assert decision.action_id == "project.task.create" and decision.event_type == "SensitiveAuthorizationAllowed"
            assert event.event_payload["source_type"] == "json_import"
            assert event.event_payload["references"]["authorization_decision_id"] == decision.id
    repeated = await client.post(_batch_path(project), headers=headers, json={"source_id": source["source_id"]})
    recovered = await client.post(_batch_path(project), headers=auth_headers(), json={"source_id": source["source_id"]})
    assert repeated.status_code == recovered.status_code == 201
    assert repeated.json() == recovered.json() == result
    assert await _counts(project) == (1, 200, 2, 200, 200, 200)


async def test_replay_keeps_original_facts_after_advancement_without_provider_or_parser(import_source_client, monkeypatch):
    """Committed replay reads native ancestry; current Tasks remain separate facts."""
    client = import_source_client
    project = (await create_active_project(client, slug="batch-advance-" + uuid4().hex))["id"]
    source = await _verified_source(client, project, document(2))
    headers = auth_headers()
    imported = await client.post(_batch_path(project), headers=headers, json={"source_id": source["source_id"]})
    assert imported.status_code == 201, imported.text
    result = imported.json()
    first = result["tasks"][0]["id"]
    for action in ("screen", "release"):
        advanced = await client.post(f"/api/v1/tasks/{first}/{action}", headers=auth_headers(), json={})
        assert advanced.status_code == 200, advanced.text
    async with db_session.get_session_factory()() as session, session.begin():
        header = await session.get(TaskImportBatch, result["batch_id"])
        replica = await session.get(ArtifactReplica, header.replica_id)
        replica.availability_state = "unavailable"

    def forbidden(*args, **kwargs):
        raise AssertionError("committed batch replay cannot read provider bytes or reinterpret JSON")

    monkeypatch.setattr(ArtifactTaskImportSourceCommands, "open", forbidden)
    monkeypatch.setattr("app.modules.tasks.task_import_batches.parse_task_import", forbidden)
    for request_headers in (headers, auth_headers()):
        replay = await client.post(_batch_path(project), headers=request_headers, json={"source_id": source["source_id"]})
        assert replay.status_code == 201 and replay.json() == result, replay.text
    status = await client.get(_batch_path(project) + "/" + result["batch_id"], headers=auth_headers())
    assert status.status_code == 200, status.text
    assert status.json()["creation"] == result
    assert [row["status"] for row in status.json()["current_tasks"]] == ["ready", "draft"]
    assert await _counts(project) == (1, 2, 2, 2, 2, 2)


async def test_different_verified_selector_recovers_but_changed_key_selector_conflicts(import_source_client, monkeypatch):
    """Another actual verified source may recover a file, never rewrite its retry key."""
    client = import_source_client
    project = await _project(client)
    value = document(2)
    original = await _verified_source(client, project, value)
    headers = auth_headers()
    response = await client.post(_batch_path(project), headers=headers, json={"source_id": original["source_id"]})
    assert response.status_code == 201, response.text
    alternate = await _verified_source(client, project, value)
    assert alternate["source_id"] != original["source_id"]
    # A declared parent claims the same SHA/count, but has no verified receipt.
    unverified = await _declare(client, project, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())

    def forbidden(*args, **kwargs):
        raise AssertionError("exact-file recovery must not consult provider/parser")

    monkeypatch.setattr(ArtifactTaskImportSourceCommands, "open", forbidden)
    monkeypatch.setattr("app.modules.tasks.task_import_batches.parse_task_import", forbidden)
    recovered = await client.post(_batch_path(project), headers=auth_headers(), json={"source_id": alternate["source_id"]})
    assert recovered.status_code == 201 and recovered.json() == response.json(), recovered.text
    changed = await client.post(_batch_path(project), headers=headers, json={"source_id": alternate["source_id"]})
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "task_import_idempotency_mismatch", changed.text
    denied = await client.post(_batch_path(project), headers=auth_headers(), json={"source_id": unverified["source_id"]})
    assert denied.status_code == 409, denied.text
    assert await _counts(project) == (1, 2, 2, 2, 2, 2)


async def test_existing_manual_external_id_rejects_every_row_without_partial_effects(import_source_client):
    """Native external-ID uniqueness covers manual creation and whole-file rollback."""
    client = import_source_client
    project = await _project(client)
    payload = complete_task_payload() | {"external_task_id": "source-2"}
    existing = await client.post(f"/api/v1/projects/{project}/tasks", headers=auth_headers(), json=payload)
    assert existing.status_code == 201, existing.text
    source = await _verified_source(client, project, document(3))
    rejected = await client.post(_batch_path(project), headers=auth_headers(), json={"source_id": source["source_id"]})
    assert rejected.status_code == 409 and rejected.json()["error"]["code"] == "task_import_external_id_conflict", rejected.text
    assert rejected.json()["detail"] == [{"loc": ["tasks", 2, "external_task_id"], "type": "external_task_id_conflict"}]
    assert await _counts(project) == (0, 0, 0, 1, 1, 1)
    again = await client.post(f"/api/v1/projects/{project}/tasks", headers=auth_headers(), json=payload)
    assert again.status_code == 409, again.text
    other = await _project(client)
    permitted = await client.post(f"/api/v1/projects/{other}/tasks", headers=auth_headers(), json=payload)
    case = await client.post(f"/api/v1/projects/{project}/tasks", headers=auth_headers(), json=payload | {"external_task_id": "Source-2"})
    assert permitted.status_code == case.status_code == 201
    for _ in range(2):
        nullable = await client.post(f"/api/v1/projects/{project}/tasks", headers=auth_headers(), json=complete_task_payload())
        assert nullable.status_code == 201, nullable.text


@pytest.mark.parametrize("failure", ["last_row", "after_all_rows"])
async def test_late_failure_rolls_back_tasks_receipts_and_successful_evidence(import_source_client, monkeypatch, failure):
    """Failure after successful staging leaves no batch or Task creation facts."""
    client = import_source_client
    project = await _project(client)
    source = await _verified_source(client, project, document(3))
    if failure == "last_row":
        stage = AuthorizedTaskCommands.stage_creation

        async def fail_last(commands, prepared, decision):
            result = await stage(commands, prepared, decision)
            if result.external_task_id == "source-2":
                raise RuntimeError("injected failure after the final canonical Task stage")
            return result

        monkeypatch.setattr(AuthorizedTaskCommands, "stage_creation", fail_last)
    else:
        stage = TaskImportBatchCommands._stage_rows

        async def fail_complete(commands, *args, **kwargs):
            await stage(commands, *args, **kwargs)
            raise RuntimeError("injected failure after all Task and member stages")

        monkeypatch.setattr(TaskImportBatchCommands, "_stage_rows", fail_complete)
    response = await client.post(_batch_path(project), headers=auth_headers(), json={"source_id": source["source_id"]})
    assert response.status_code == 500, response.text
    assert await _counts(project) == (0, 0, 0, 0, 0, 0)
    async with db_session.get_session_factory()() as session:
        assert not list(await session.scalars(select(AuditEvent.id).where(
            AuditEvent.project_id == project, AuditEvent.action_id.in_(["project.task.create", "project.task.import"]),
            AuditEvent.event_type == "SensitiveAuthorizationAllowed",
        )))
        assert await session.get(ArtifactTaskImportSource, source["source_id"]) is not None


async def test_matching_metadata_label_never_adds_native_membership(import_source_client):
    """A manual Task cannot join a batch by spoofing its exposed metadata spelling."""
    client = import_source_client
    project = await _project(client)
    source = await _verified_source(client, project, document())
    imported = await client.post(_batch_path(project), headers=auth_headers(), json={"source_id": source["source_id"]})
    assert imported.status_code == 201, imported.text
    batch = imported.json()
    manual = await client.post(f"/api/v1/projects/{project}/tasks", headers=auth_headers(),
                               json=complete_task_payload() | {"import_batch_id": batch["batch_id"]})
    assert manual.status_code == 201, manual.text
    status = await client.get(_batch_path(project) + "/" + batch["batch_id"], headers=auth_headers())
    assert status.status_code == 200 and status.json()["creation"] == batch
    assert [row["task_id"] for row in status.json()["current_tasks"]] == [batch["tasks"][0]["id"]]
    assert await _counts(project) == (1, 1, 1, 2, 2, 2)


async def test_ungranted_actor_cannot_replay_or_read_committed_batch(import_source_client, monkeypatch):
    """A role claim never grants current source or immutable batch authority."""
    client = import_source_client
    project = await _project(client)
    source = await _verified_source(client, project, document())
    headers = auth_headers()
    imported = await client.post(_batch_path(project), headers=headers, json={"source_id": source["source_id"]})
    assert imported.status_code == 201, imported.text
    before = await _counts(project)
    set_dev_actor(monkeypatch, roles="project_manager", subject="ungranted-batch-manager")
    captured = []
    restage = PreparedTaskImportSourceAuthorization.restage_denial

    async def observe(authority, error):
        captured.append((error.__cause__.decision, authority._context.actor_profile_id))
        await restage(authority, error)

    monkeypatch.setattr(PreparedTaskImportSourceAuthorization, "restage_denial", observe)
    for request_headers in (headers, auth_headers()):
        denied = await client.post(_batch_path(project), headers=request_headers, json={"source_id": source["source_id"]})
        assert denied.status_code == 403, denied.text
    hidden = await client.get(_batch_path(project) + "/" + imported.json()["batch_id"], headers=auth_headers())
    assert hidden.status_code == 404, hidden.text
    assert await _counts(project) == before
    async with db_session.get_session_factory()() as session:
        events = list(await session.scalars(select(AuditEvent).where(
            AuditEvent.action_id == "artifact.task_import_source.read",
            AuditEvent.event_type == "SensitiveAuthorizationDenied",
        )))
        decisions = {str(decision.decision_id): (decision, actor) for decision, actor in captured}
        assert len(events) == len(decisions) == 3
        assert set(decisions) == {event.id for event in events}
        assert all(event.actor_id == str(decisions[event.id][1])
                   and event.request_id == str(decisions[event.id][0].request_id)
                   and event.action_id == decisions[event.id][0].action_id.value
                   and event.denial_code == "permission_not_granted"
                   and event.after_facts["resource_context_digest"] == decisions[event.id][0].resource_context_digest
                   for event in events)


async def test_two_import_roots_wait_on_actual_file_custody_then_recover_one_batch(import_source_client, monkeypatch):
    """A gated PostgreSQL wait proves concurrent first imports share one original."""
    client = import_source_client
    project = await _project(client)
    source = await _verified_source(client, project, document(3))
    original = TaskImportBatchCommands._reserve_batch
    first_reserved, second_entered, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pids, calls = [], 0

    async def gated(commands, *args, **kwargs):
        nonlocal calls
        calls += 1
        call = calls
        pids.append(await commands._session.scalar(select(func.pg_backend_pid())))
        if call == 2:
            second_entered.set()
        batch = await original(commands, *args, **kwargs)
        if call == 1:
            first_reserved.set()
            await asyncio.wait_for(release.wait(), timeout=30)
        return batch

    monkeypatch.setattr(TaskImportBatchCommands, "_reserve_batch", gated)
    path, payload = _batch_path(project), {"source_id": source["source_id"]}
    first = asyncio.create_task(client.post(path, headers=auth_headers(), json=payload))
    second = None
    try:
        await asyncio.wait_for(first_reserved.wait(), timeout=30)
        second = asyncio.create_task(client.post(path, headers=auth_headers(), json=payload))
        await asyncio.wait_for(second_entered.wait(), timeout=30)
        deadline = asyncio.get_running_loop().time() + 10
        async with db_session.get_session_factory()() as observer:
            while True:
                blocked = await observer.scalar(text("select :holder = any(pg_blocking_pids(:waiter))"),
                                                {"holder": pids[0], "waiter": pids[1]})
                if blocked:
                    break
                assert asyncio.get_running_loop().time() < deadline, "second root never waited on the original file holder"
                await asyncio.sleep(0.05)
        release.set()
        responses = await asyncio.wait_for(asyncio.gather(first, second), timeout=30)
        assert [response.status_code for response in responses] == [201, 201], [response.text for response in responses]
        assert responses[0].json() == responses[1].json()
        assert await _counts(project) == (1, 3, 2, 3, 3, 3)
    finally:
        release.set()
        for pending in (first, second):
            if pending is not None and not pending.done():
                pending.cancel()
        await asyncio.gather(*(pending for pending in (first, second) if pending is not None), return_exceptions=True)


@pytest.mark.parametrize("table", ["task_import_batches", "task_import_batch_members", "task_import_batch_command_receipts"])
@pytest.mark.parametrize("operation", ["update", "delete", "truncate"])
async def test_committed_custody_rejects_direct_sql_mutation(import_source_client, table, operation):
    """Each native table refuses row mutation and statement-level truncation."""
    client = import_source_client
    project = await _project(client)
    source = await _verified_source(client, project, document())
    imported = await client.post(_batch_path(project), headers=auth_headers(), json={"source_id": source["source_id"]})
    assert imported.status_code == 201, imported.text
    async with db_session.get_session_factory()() as session, session.begin():
        before = list((await session.execute(text(f"select to_jsonb(t) from {table} t order by id"))).scalars())
        if operation == "truncate":
            assert await session.scalar(text(
                "select count(*) from pg_trigger where tgrelid=cast(:table as regclass) "
                "and not tgisinternal and (tgtype & 32)=32 and (tgtype & 1)=0 and tgenabled='O'"
            ), {"table": table}) == 1, "each owner requires its own enabled statement-level TRUNCATE guard"
        updates = {
            "task_import_batches": "metadata_label='changed display label'",
            "task_import_batch_members": "row_index=1",
            "task_import_batch_command_receipts": "request_digest='sha256:" + "a" * 64 + "'",
        }
        statement = {"update": f"update {table} set {updates[table]}", "delete": f"delete from {table}",
                     "truncate": f"truncate {table} cascade"}[operation]
        with pytest.raises(DBAPIError):
            async with session.begin_nested():
                await session.execute(text(statement))
        assert list((await session.execute(text(f"select to_jsonb(t) from {table} t order by id"))).scalars()) == before
    recovered = await client.post(_batch_path(project), headers=auth_headers(), json={"source_id": source["source_id"]})
    assert recovered.status_code == 201 and recovered.json() == imported.json(), recovered.text
