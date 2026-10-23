"""Authenticated public composition for Operator-owned checker model controls."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth import checker_model_authorization
from app.adapters.checkers import model_call_service
from app.api.deps.auth import get_auth_verification_result
from app.api.deps.authorization import (
    ResolvedActor,
    _authorization_context,
    get_authorization_actor,
)
from app.core.api_controls import StructuredHTTPException, parse_idempotency_key, request_ids
from app.core.hashing import canonical_json_hash
from app.db.session import get_db_session
from app.modules.model_usage.api import (
    ModelBudgetProvisioningFacts,
    ModelCallBudgetUnavailable,
    ModelCallAdministrationPort,
    ModelCallConflict,
    ModelCallUnavailable,
    ModelProfileProvisioningFacts,
    ModelRecoveryChildRequest,
    PreparedModelCallAttempt,
    ProjectModelBudgetConfiguration,
    ProjectModelBudgetConfigurationSpec,
    ProjectModelProfile,
    ProjectModelProfileSpec,
)
from app.schemas.auth import AuthVerificationResult


MODEL_ADMIN_IDEMPOTENCY_PARAMETER = {
    "name": "Idempotency-Key",
    "in": "header",
    "required": True,
    "schema": {"type": "string", "format": "uuid"},
}


def require_model_admin_key(request: Request) -> UUID:
    """Reject an absent, duplicate or noncanonical Operator mutation key."""
    values = request.headers.getlist("Idempotency-Key")
    return parse_idempotency_key(values[0] if len(values) == 1 else "")


def _error(status_code: int) -> StructuredHTTPException:
    code, message = {
        404: ("checker_model_control_not_found", "Checker model control not found"),
        409: ("checker_model_control_conflict", "Checker model control conflicts"),
        503: ("checker_model_control_unavailable", "Checker model control unavailable"),
    }[status_code]
    return StructuredHTTPException(
        status_code=status_code,
        detail=code,
        error_code=code,
        error_message=message,
        retryable=status_code == 503,
    )


async def require_model_admin_human(
    operation_id: Annotated[UUID, Depends(require_model_admin_key)],
    result: Annotated[AuthVerificationResult, Depends(get_auth_verification_result)],
) -> None:
    """Consume the key first and conceal every nonhuman public mutation caller."""
    del operation_id
    if result.token.subject_kind != "human":
        raise _error(404)


async def require_model_recovery_human(
    result: Annotated[AuthVerificationResult, Depends(get_auth_verification_result)],
) -> None:
    """Conceal recovery controls from every nonhuman public caller."""
    if result.token.subject_kind != "human":
        raise _error(404)


@dataclass(frozen=True)
class CheckerModelAdminCommands:
    """Bind path, actor and caller key to the existing atomic CHECKERS owner."""

    service: ModelCallAdministrationPort
    actor_profile_id: UUID
    operation_id: UUID

    async def provision_profile(
        self, project_id: UUID, spec: ProjectModelProfileSpec
    ) -> ProjectModelProfile:
        if spec.project_id != project_id:
            raise ModelCallConflict("model_profile_project_conflict")
        return await self.service.provision_profile(
            ModelProfileProvisioningFacts(
                operation_id=self.operation_id,
                actor_profile_id=self.actor_profile_id,
                spec=spec,
                profile_digest=canonical_json_hash(spec.model_dump(mode="json")),
            )
        )

    async def configure_budget(
        self, project_id: UUID, spec: ProjectModelBudgetConfigurationSpec
    ) -> ProjectModelBudgetConfiguration:
        if spec.project_id != project_id:
            raise ModelCallConflict("model_budget_project_conflict")
        return await self.service.provision_budget(
            ModelBudgetProvisioningFacts(
                operation_id=self.operation_id,
                actor_profile_id=self.actor_profile_id,
                spec=spec,
                configuration_digest=canonical_json_hash(spec.model_dump(mode="json")),
            )
        )

    async def prepare_recovery_child(
        self,
        project_id: UUID,
        parent_attempt_id: UUID,
        request: ModelRecoveryChildRequest,
    ) -> PreparedModelCallAttempt:
        if request.slot.project_id != project_id:
            raise ModelCallConflict("model_recovery_project_conflict")
        return await self.service.prepare_recovery_child(
            request.slot,
            registry_entry_id=request.registry_entry_id,
            parent_attempt_id=parent_attempt_id,
            terminal_digest=request.terminal_digest,
            request_sha256=request.request_sha256,
        )


@asynccontextmanager
async def _model_admin_operation(
    request: Request,
    operation_id: UUID,
    resolved: ResolvedActor,
    session: AsyncSession,
    *,
    correlation_id: UUID | None = None,
) -> AsyncIterator[CheckerModelAdminCommands]:
    request_id, _ = (UUID(value) for value in request_ids(request))
    context = _authorization_context(resolved, request_id, correlation_id or operation_id)
    await session.rollback()
    try:
        async with session.begin():
            authority = checker_model_authorization(session, context)
            try:
                yield CheckerModelAdminCommands(
                    service=model_call_service(session, authority),
                    actor_profile_id=context.actor_profile_id,
                    operation_id=operation_id,
                )
            except ModelCallUnavailable as exc:
                # AUTH has already staged its canonical denial. Preserve that evidence
                # before the public boundary conceals the private authority reason.
                if str(exc) == "model_call_authority_unavailable" and session.is_active:
                    await session.commit()
                raise
    except ModelCallBudgetUnavailable as exc:
        raise _error(409) from exc
    except ModelCallConflict as exc:
        raise _error(409) from exc
    except ModelCallUnavailable as exc:
        status_code = 404 if str(exc) == "model_call_authority_unavailable" else 503
        raise _error(status_code) from exc
    except SQLAlchemyError as exc:
        raise _error(503) from exc
    finally:
        if session.in_transaction():
            await session.rollback()


async def get_checker_model_admin_commands(
    request: Request,
    operation_id: Annotated[UUID, Depends(require_model_admin_key)],
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[CheckerModelAdminCommands]:
    """Compose one human Operator mutation and its root transaction."""
    async with _model_admin_operation(request, operation_id, resolved, session) as commands:
        yield commands


async def get_checker_model_recovery_commands(
    request: Request,
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[CheckerModelAdminCommands]:
    """Compose recovery under fresh request IDs; the parent/candidate own replay."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    async with _model_admin_operation(
        request,
        request_id,
        resolved,
        session,
        correlation_id=correlation_id,
    ) as commands:
        yield commands


__all__ = (
    "MODEL_ADMIN_IDEMPOTENCY_PARAMETER",
    "CheckerModelAdminCommands",
    "get_checker_model_admin_commands",
    "get_checker_model_recovery_commands",
    "require_model_admin_human",
    "require_model_admin_key",
    "require_model_recovery_human",
)
