"""Supported authenticated Operator entry for external-checker registration."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.deps.api_controls import enforce_admin_mutation_rate_limit
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
from app.modules.checkers.api import (
    ExternalCheckerRegistrationCommand,
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistrySpec,
)


router = APIRouter(
    prefix="/operations/external-checker-registry",
    tags=["checker-operations"],
    responses={code: {"model": ApiErrorResponse} for code in (403, 404, 409, 422, 503)},
)


@router.post(
    "",
    response_model=ExternalCheckerRegistryEntry,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_admin_mutation_rate_limit)],
    openapi_extra={
        "x-workstream-action-id": "checker.registry.register",
        "parameters": [REGISTRY_IDEMPOTENCY_PARAMETER],
    },
)
async def register_external_checker(
    payload: ExternalCheckerRegistrySpec,
    operation_id: Annotated[UUID, Depends(require_registry_key)],
    operation: Annotated[
        CheckerRegistryOperation, Depends(get_registry_registration)
    ],
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
    "/{registry_entry_id}",
    response_model=ExternalCheckerRegistryEntry,
    dependencies=[Depends(enforce_human_authorization_read)],
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
