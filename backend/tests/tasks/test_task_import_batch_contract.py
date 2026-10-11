"""Instruction mapping and closed original/current batch projections."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.tasks.api.task_import import TaskImportRow, TaskImportSourceCommitment
from app.modules.tasks.schemas import (
    TaskCreate, TaskImportBatchCurrentTask, TaskImportBatchRequest, TaskImportBatchResponse,
    TaskImportBatchStatus, TaskResponse,
)
from app.modules.tasks.task_import_batches import imported_task_payload


def _source():
    return TaskImportSourceCommitment(new_record_id(), new_record_id(),
                                     "sha256:" + "a" * 64, 100, "sha256:" + "b" * 64)


def _original(source, batch_id, external_id):
    values = {field: None for field in TaskResponse.model_fields}
    values.update(imported_task_payload(
        TaskImportRow(external_task_id=external_id, title="Instructions", description="Actual work"), source, batch_id,
    ).model_dump())
    values.update(id=str(new_record_id()), project_id=str(source.project_id), status="draft",
                  created_by=str(new_record_id()), created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
    return TaskResponse.model_validate(values)


def test_mapping_preserves_instructions_and_stamps_server_only_json_custody():
    source, batch_id = _source(), new_record_id()
    row = TaskImportRow(external_task_id="Case-Sensitive", title="Instructions", description="Exact work",
                        difficulty="x" * 80, skill_tags=["python"], estimated_time_minutes=30)
    mapped = imported_task_payload(row, source, batch_id)
    assert {field: getattr(mapped, field) for field in TaskImportRow.model_fields} == row.model_dump()
    assert (mapped.source_type, mapped.source_ref, mapped.source_payload_hash, mapped.import_batch_id) == (
        "json_import", f"task-import-source:{source.source_id}", source.sha256, str(batch_id),
    )
    assert mapped.deadline_at is None
    with pytest.raises(ValidationError):
        TaskCreate.model_validate(mapped.model_dump())
    with pytest.raises(ValidationError):
        TaskImportBatchRequest.model_validate({"source_id": source.source_id, "source_type": "manual"})
    with pytest.raises(ValidationError):
        TaskImportRow.model_validate(row.model_dump() | {"import_batch_id": str(batch_id)})


def test_projection_separates_immutable_creation_from_current_member_states():
    source, batch_id = _source(), new_record_id()
    originals = (_original(source, batch_id, "one"), _original(source, batch_id, "two"))
    creation = TaskImportBatchResponse(
        batch_id=batch_id, project_id=source.project_id, source_id=source.source_id,
        sha256=source.sha256, byte_count=source.byte_count, row_count=2, created_at=datetime.now(UTC),
        schema_version="workstream.task_import.v1", mapping_version="workstream.task_import.draft_mapping.v1",
        tasks=originals,
    )
    current = tuple(TaskImportBatchCurrentTask(task_id=original.id, row_index=index, status="ready")
                    for index, original in enumerate(originals))
    status = TaskImportBatchStatus(creation=creation, current_tasks=current)
    assert [row.status for row in status.current_tasks] == ["ready", "ready"]
    assert [row.status for row in status.creation.tasks] == ["draft", "draft"]
    with pytest.raises(ValidationError):
        TaskImportBatchStatus(creation=creation, current_tasks=tuple(reversed(current)))
    with pytest.raises(ValidationError):
        TaskImportBatchResponse.model_validate(creation.model_dump() | {"project_id": new_record_id()})
    with pytest.raises(ValidationError):
        TaskImportBatchResponse.model_validate(creation.model_dump() | {"tasks": (originals[0], originals[0])})
