"""Explicit project-scoped all-member SCREEN and RELEASE delivery."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.deps.task_batch_transitions import get_task_batch_transition_commands
from app.core.api_controls import StructuredHTTPException, parse_idempotency_key
from app.modules.tasks.api.authorization import TaskAuthorityOperation
from app.modules.tasks.api.task_batch_transition import (
    TaskBatchTransitionPort, TaskBatchTransitionRequest, TaskBatchTransitionResponse,
)
from app.modules.tasks.api.task_import_membership import TaskImportBatchError
from app.modules.tasks.service import TaskServiceError

router = APIRouter(tags=["tasks"])
_KEY_PARAMETER = {"name": "Idempotency-Key", "in": "header", "required": True,
                  "schema": {"type": "string", "format": "uuid"}}


def require_batch_transition_key(request: Request) -> UUID:
    """Require one exact caller retry UUID before resolving a mutating actor."""
    values = request.headers.getlist("Idempotency-Key")
    return parse_idempotency_key(values[0] if len(values) == 1 else "")


def _error(exc: TaskImportBatchError | TaskServiceError) -> StructuredHTTPException:
    code = getattr(exc, "code", None) or "task_batch_transition_invalid"
    return StructuredHTTPException(
        status_code=exc.status_code, detail=str(exc), error_code=code,
        error_message=str(exc), retryable=getattr(exc, "retryable", False),
    )


@router.post(
    "/projects/{project_id}/task-import-batches/{batch_id}/screen",
    response_model=TaskBatchTransitionResponse,
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.SCREEN.value,
                   "parameters": [_KEY_PARAMETER]},
)
async def screen_task_batch(
    project_id: UUID, batch_id: UUID, payload: TaskBatchTransitionRequest,
    key: Annotated[UUID, Depends(require_batch_transition_key)],
    commands: Annotated[TaskBatchTransitionPort, Depends(get_task_batch_transition_commands)],
) -> TaskBatchTransitionResponse:
    """Screen the complete native batch or recover its still-current exact result."""
    try:
        return await commands.screen(project_id, batch_id, payload.reason, idempotency_key=key)
    except (TaskImportBatchError, TaskServiceError) as exc:
        raise _error(exc) from exc


@router.post(
    "/projects/{project_id}/task-import-batches/{batch_id}/release",
    response_model=TaskBatchTransitionResponse,
    openapi_extra={"x-workstream-action-id": TaskAuthorityOperation.RELEASE.value,
                   "parameters": [_KEY_PARAMETER]},
)
async def release_task_batch(
    project_id: UUID, batch_id: UUID, payload: TaskBatchTransitionRequest,
    key: Annotated[UUID, Depends(require_batch_transition_key)],
    commands: Annotated[TaskBatchTransitionPort, Depends(get_task_batch_transition_commands)],
) -> TaskBatchTransitionResponse:
    """Release all members with normal reason and locked prerequisites, or none."""
    try:
        return await commands.release(project_id, batch_id, payload.reason, idempotency_key=key)
    except (TaskImportBatchError, TaskServiceError) as exc:
        raise _error(exc) from exc
