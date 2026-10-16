"""Canonical contributor and Project Manager checker history reads."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from app.api.deps.authorization import enforce_human_authorization_read
from app.api.deps.checker_recovery import (
    CheckerRetryCommands, CheckerRetryReads,
    get_checker_retry_commands, get_checker_retry_reads,
)

from app.api.deps.history import HistoryReadOperation, get_history_reads


from app.modules.checkers.api.history import (
    ContributorCheckerHistoryPage,
    ManagementCheckerHistoryPage,
    ContributorCheckerHistory,
    ManagementCheckerHistory,
)
from app.modules.checkers.api.execution import (
    CheckerRetryRequest, CheckerRetryResult, CheckerRetrySourcePage,
)
from app.modules.authorization.catalogue import ActionId


router = APIRouter(tags=["checkers"])

CHECKER_RETRY_KEY_PARAMETER = {
    "name": "Idempotency-Key",
    "in": "header",
    "required": True,
    "schema": {"type": "string", "format": "uuid"},
}


@router.get(
    "/operations/projects/{project_id}/checker-retry-sources",
    response_model=CheckerRetrySourcePage,
    openapi_extra={
        "x-workstream-action-id": ActionId.OPERATIONS_CHECKER_RETRY_SOURCE_LIST.value,
    },
)
async def list_checker_retry_sources(
    project_id: UUID,
    reads: Annotated[CheckerRetryReads, Depends(get_checker_retry_reads)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> CheckerRetrySourcePage:
    """List exact finalized infrastructure failures for a system Operator."""
    return await reads.discover(project_id, limit=limit, cursor=cursor)


@router.post(
    "/operations/projects/{project_id}/checker-runs/{source_run_id}/retry",
    response_model=CheckerRetryResult,
    status_code=201,
    openapi_extra={
        "x-workstream-action-id": ActionId.OPERATIONS_CHECKER_RETRY.value,
        "parameters": [CHECKER_RETRY_KEY_PARAMETER],
    },
)
async def retry_checker_infrastructure_failure(
    project_id: UUID,
    source_run_id: UUID,
    payload: CheckerRetryRequest,
    commands: Annotated[CheckerRetryCommands, Depends(get_checker_retry_commands)],
) -> CheckerRetryResult:
    """Create or replay one exact reason-bound terminal checker retry."""
    return await commands.retry(project_id, source_run_id, payload)


@router.get("/submissions/{submission_id}/checker-runs", response_model=ContributorCheckerHistoryPage,
    dependencies=[Depends(enforce_human_authorization_read)],
    openapi_extra={"x-workstream-action-id": "submission.checker_run.list"},
)
async def read_contributor_checker_runs(
    submission_id: UUID,
    history: Annotated[HistoryReadOperation, Depends(get_history_reads)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=1024)] = None,
) -> ContributorCheckerHistoryPage:
    """Read retained checker runs under fresh contributor authority."""
    return await history.read(
        "checker_runs", submission_id, limit=limit, cursor=cursor,
    )


@router.get("/projects/{project_id}/submissions/{submission_id}/checker-runs", response_model=ManagementCheckerHistoryPage,
    dependencies=[Depends(enforce_human_authorization_read)],
    openapi_extra={"x-workstream-action-id": "project.submission.checker_run.list"},
)
async def read_management_checker_runs(
    submission_id: UUID,
    project_id: UUID,
    history: Annotated[HistoryReadOperation, Depends(get_history_reads)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: Annotated[str | None, Query(max_length=1024)] = None,
) -> ManagementCheckerHistoryPage:
    """Read retained checker runs under fresh management authority."""
    return await history.read(
        "checker_runs", submission_id, project_id=project_id, limit=limit, cursor=cursor,
    )


@router.get("/submissions/{submission_id}/checker-runs/{checker_run_id}", response_model=ContributorCheckerHistory,
    dependencies=[Depends(enforce_human_authorization_read)],
    openapi_extra={"x-workstream-action-id": "checker_run.read"},
)
async def read_contributor_checker_run(
    checker_run_id: UUID,
    submission_id: UUID,
    history: Annotated[HistoryReadOperation, Depends(get_history_reads)],
) -> ContributorCheckerHistory:
    """Read retained checker run under fresh contributor authority."""
    return await history.read(
        "checker_run", checker_run_id, submission_id=submission_id,
    )


@router.get("/projects/{project_id}/submissions/{submission_id}/checker-runs/{checker_run_id}", response_model=ManagementCheckerHistory,
    dependencies=[Depends(enforce_human_authorization_read)],
    openapi_extra={"x-workstream-action-id": "project.checker_run.read"},
)
async def read_management_checker_run(
    checker_run_id: UUID,
    submission_id: UUID,
    project_id: UUID,
    history: Annotated[HistoryReadOperation, Depends(get_history_reads)],
) -> ManagementCheckerHistory:
    """Read retained checker run under fresh management authority."""
    return await history.read(
        "checker_run", checker_run_id, submission_id=submission_id, project_id=project_id,
    )
