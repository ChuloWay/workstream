"""Canonical contributor and Project Manager checker history reads."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from app.api.deps.api_controls import (
    enforce_admin_mutation_rate_limit,
    enforce_authorization_read_rate_limit,
)
from app.api.deps.authorization import enforce_human_authorization_read
from app.api.deps.checker_registry import (
    REGISTRY_IDEMPOTENCY_PARAMETER,
    CheckerRegistryOperation,
    commit_registry_response,
    get_registry_read,
    get_registry_registration,
    require_registry_key,
)
from app.core.api_controls import ApiErrorResponse
from app.api.deps.checker_recovery import (
    CheckerRetryCommands,
    CheckerRetryReads,
    get_checker_retry_commands,
    get_checker_retry_reads,
    require_checker_retry_human,
    PostSubmitDeliveryCommands,
    PostSubmitDeliveryReads,
    get_post_submit_delivery_commands,
    get_post_submit_delivery_reads,
    require_post_submit_delivery_human,
)
from app.api.deps.checker_models import (
    MODEL_ADMIN_IDEMPOTENCY_PARAMETER,
    CheckerModelAdminCommands,
    get_checker_model_admin_commands,
    get_checker_model_read_commands,
    get_checker_model_recovery_commands,
    require_model_admin_human,
    require_model_admin_key,
    require_model_recovery_human,
)

from app.api.deps.history import HistoryReadOperation, get_history_reads


from app.modules.checkers.api.history import (
    ContributorCheckerHistoryPage,
    ManagementCheckerHistoryPage,
    ContributorCheckerHistory,
    ManagementCheckerHistory,
)
from app.modules.checkers.api import (
    ExternalCheckerRegistrationCommand,
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistrySpec,
)
from app.modules.checkers.api.execution import (
    CheckerRetryPublicResult,
    CheckerRetryRequest,
    CheckerRetrySourcePage,
)
from app.modules.checkers.api.delivery_reconciliation import (
    PostSubmitDeliveryPage,
    PostSubmitDeliveryRequest,
    PostSubmitDeliveryResult,
)
from app.modules.model_usage.api import (
    ModelRecoveryChildRequest,
    ModelUsageEffectInspection,
    PreparedModelCallAttempt,
    ProjectModelBudgetConfiguration,
    ProjectModelBudgetConfigurationSpec,
    ProjectModelProfile,
    ProjectModelProfileSpec,
)


router = APIRouter(tags=["checkers"])


@router.post(
    "/operations/projects/{project_id}/model-profiles",
    response_model=ProjectModelProfile,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(enforce_admin_mutation_rate_limit),
        Depends(require_model_admin_human),
        Depends(require_model_admin_key),
    ],
    responses={code: {"model": ApiErrorResponse} for code in (404, 409, 422, 503)},
    openapi_extra={
        "x-workstream-action-id": "project.model_profile.provision",
        "parameters": [MODEL_ADMIN_IDEMPOTENCY_PARAMETER],
    },
)
async def provision_project_model_profile(
    project_id: UUID,
    payload: ProjectModelProfileSpec,
    commands: Annotated[CheckerModelAdminCommands, Depends(get_checker_model_admin_commands)],
) -> ProjectModelProfile:
    """Publish or exactly replay one immutable approved project model profile."""
    return await commands.provision_profile(project_id, payload)


@router.post(
    "/operations/projects/{project_id}/model-budget-configurations",
    response_model=ProjectModelBudgetConfiguration,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(enforce_admin_mutation_rate_limit),
        Depends(require_model_admin_human),
        Depends(require_model_admin_key),
    ],
    responses={code: {"model": ApiErrorResponse} for code in (404, 409, 422, 503)},
    openapi_extra={
        "x-workstream-action-id": "project.model_budget.configure",
        "parameters": [MODEL_ADMIN_IDEMPOTENCY_PARAMETER],
    },
)
async def configure_project_model_budget(
    project_id: UUID,
    payload: ProjectModelBudgetConfigurationSpec,
    commands: Annotated[CheckerModelAdminCommands, Depends(get_checker_model_admin_commands)],
) -> ProjectModelBudgetConfiguration:
    """Create or replay one immutable lifetime project model budget version."""
    return await commands.configure_budget(project_id, payload)


@router.get(
    "/operations/projects/{project_id}/model-usage/effects/{effect_id}",
    response_model=ModelUsageEffectInspection,
    dependencies=[
        Depends(enforce_authorization_read_rate_limit),
        Depends(enforce_human_authorization_read),
    ],
    responses={code: {"model": ApiErrorResponse} for code in (404, 422, 503)},
    openapi_extra={"x-workstream-action-id": "project.model_usage.read"},
)
async def read_project_model_usage_effect(
    project_id: UUID,
    effect_id: UUID,
    commands: Annotated[CheckerModelAdminCommands, Depends(get_checker_model_read_commands)],
) -> ModelUsageEffectInspection:
    """Read redacted accounting and evidence identities for one exact paid effect."""
    return await commands.inspect_effect(project_id, effect_id)


@router.post(
    "/operations/projects/{project_id}/model-call-attempts/{parent_attempt_id}/recovery-children",
    response_model=PreparedModelCallAttempt,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        Depends(enforce_admin_mutation_rate_limit),
        Depends(require_model_recovery_human),
    ],
    responses={code: {"model": ApiErrorResponse} for code in (404, 409, 422, 503)},
    openapi_extra={
        "x-workstream-action-id": "project.model_call.recovery_child.authorize",
    },
)
async def prepare_project_model_recovery_child(
    project_id: UUID,
    parent_attempt_id: UUID,
    payload: ModelRecoveryChildRequest,
    commands: Annotated[CheckerModelAdminCommands, Depends(get_checker_model_recovery_commands)],
) -> PreparedModelCallAttempt:
    """Create or replay a child only for one exact known terminal paid effect."""
    return await commands.prepare_recovery_child(project_id, parent_attempt_id, payload)


@router.post(
    "/operations/external-checker-registry",
    response_model=ExternalCheckerRegistryEntry,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_admin_mutation_rate_limit)],
    responses={code: {"model": ApiErrorResponse} for code in (403, 404, 409, 422, 503)},
    openapi_extra={
        "x-workstream-action-id": "checker.registry.register",
        "parameters": [REGISTRY_IDEMPOTENCY_PARAMETER],
    },
)
async def register_external_checker(
    payload: ExternalCheckerRegistrySpec,
    operation_id: Annotated[UUID, Depends(require_registry_key)],
    operation: Annotated[CheckerRegistryOperation, Depends(get_registry_registration)],
) -> ExternalCheckerRegistryEntry:
    """Publish or exactly replay one immutable digest-pinned checker entry."""
    response = await operation.service.register(
        ExternalCheckerRegistrationCommand(
            actor_profile_id=operation.actor_profile_id,
            operation_id=operation_id,
            spec=payload,
        )
    )
    return await commit_registry_response(operation, response)


@router.get(
    "/operations/external-checker-registry/{registry_entry_id}",
    response_model=ExternalCheckerRegistryEntry,
    dependencies=[Depends(enforce_human_authorization_read)],
    responses={code: {"model": ApiErrorResponse} for code in (403, 404, 409, 422, 503)},
    openapi_extra={"x-workstream-action-id": "checker.registry.read"},
)
async def read_external_checker(
    registry_entry_id: UUID,
    operation: Annotated[CheckerRegistryOperation, Depends(get_registry_read)],
) -> ExternalCheckerRegistryEntry:
    """Read one exact immutable entry under fresh system Operator authority."""
    response = await operation.service.read_authorized(
        operation.actor_profile_id, registry_entry_id
    )
    return await commit_registry_response(operation, response)


CHECKER_RETRY_KEY_PARAMETER = {
    "name": "Idempotency-Key",
    "in": "header",
    "required": True,
    "schema": {"type": "string", "format": "uuid"},
}

POST_SUBMIT_DELIVERY_KEY_PARAMETER = {
    "name": "Idempotency-Key",
    "in": "header",
    "required": True,
    "schema": {"type": "string", "format": "uuid"},
}


@router.get(
    "/operations/projects/{project_id}/post-submit-deliveries",
    response_model=PostSubmitDeliveryPage,
    dependencies=[Depends(enforce_authorization_read_rate_limit)],
    openapi_extra={
        "x-workstream-action-id": "operations.post_submit_delivery.list",
    },
)
async def list_uncertain_post_submit_deliveries(
    project_id: UUID,
    reads: Annotated[PostSubmitDeliveryReads, Depends(get_post_submit_delivery_reads)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> PostSubmitDeliveryPage:
    """List privacy-bounded exact terminal UNKNOWN post-submit attempts."""
    return await reads.discover(project_id, limit=limit, cursor=cursor)


@router.post(
    "/operations/projects/{project_id}/post-submit-deliveries/{event_id}/reconcile",
    response_model=PostSubmitDeliveryResult,
    status_code=201,
    dependencies=[
        Depends(enforce_admin_mutation_rate_limit),
        Depends(require_post_submit_delivery_human),
    ],
    openapi_extra={
        "x-workstream-action-id": "operations.post_submit_delivery.reconcile",
        "parameters": [POST_SUBMIT_DELIVERY_KEY_PARAMETER],
    },
)
async def reconcile_uncertain_post_submit_delivery(
    project_id: UUID,
    event_id: UUID,
    payload: PostSubmitDeliveryRequest,
    commands: Annotated[PostSubmitDeliveryCommands, Depends(get_post_submit_delivery_commands)],
) -> PostSubmitDeliveryResult:
    """Append or exactly replay the sole authorized reconciliation child."""
    return await commands.reconcile(project_id, event_id, payload)


@router.get(
    "/operations/projects/{project_id}/checker-retry-sources",
    response_model=CheckerRetrySourcePage,
    dependencies=[Depends(enforce_authorization_read_rate_limit)],
    openapi_extra={
        "x-workstream-action-id": "operations.checker_retry_source.list",
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
    response_model=CheckerRetryPublicResult,
    status_code=201,
    dependencies=[
        Depends(enforce_admin_mutation_rate_limit),
        Depends(require_checker_retry_human),
    ],
    openapi_extra={
        "x-workstream-action-id": "operations.checker.retry",
        "parameters": [CHECKER_RETRY_KEY_PARAMETER],
    },
)
async def retry_checker_infrastructure_failure(
    project_id: UUID,
    source_run_id: UUID,
    payload: CheckerRetryRequest,
    commands: Annotated[CheckerRetryCommands, Depends(get_checker_retry_commands)],
) -> CheckerRetryPublicResult:
    """Create or replay one exact reason-bound terminal checker retry."""
    result = await commands.retry(project_id, source_run_id, payload)
    return CheckerRetryPublicResult.from_result(result)


@router.get(
    "/submissions/{submission_id}/checker-runs",
    response_model=ContributorCheckerHistoryPage,
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
        "checker_runs",
        submission_id,
        limit=limit,
        cursor=cursor,
    )


@router.get(
    "/projects/{project_id}/submissions/{submission_id}/checker-runs",
    response_model=ManagementCheckerHistoryPage,
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
        "checker_runs",
        submission_id,
        project_id=project_id,
        limit=limit,
        cursor=cursor,
    )


@router.get(
    "/submissions/{submission_id}/checker-runs/{checker_run_id}",
    response_model=ContributorCheckerHistory,
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
        "checker_run",
        checker_run_id,
        submission_id=submission_id,
    )


@router.get(
    "/projects/{project_id}/submissions/{submission_id}/checker-runs/{checker_run_id}",
    response_model=ManagementCheckerHistory,
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
        "checker_run",
        checker_run_id,
        submission_id=submission_id,
        project_id=project_id,
    )
