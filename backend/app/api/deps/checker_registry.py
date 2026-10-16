"""Authenticated public composition for immutable checker registry operations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any, TypeVar
from uuid import UUID

from fastapi import Depends, Request
from pydantic import TypeAdapter
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth import checker_registry_authorization
from app.api.deps.authorization import _authorization_context, get_authorization_actor
from app.core.api_controls import StructuredHTTPException, parse_idempotency_key, request_ids
from app.db.session import get_db_session
from app.modules.checkers.api import (
    ExternalCheckerRegistryAuthorizationDenied,
    ExternalCheckerRegistryConflict,
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistryNotFound,
    ExternalCheckerRegistryUnavailable,
)
from app.modules.checkers.external_registry import ExternalCheckerRegistryService


REGISTRY_IDEMPOTENCY_PARAMETER = {
    "name": "Idempotency-Key",
    "in": "header",
    "required": True,
    "schema": {"type": "string", "format": "uuid"},
}


def require_registry_key(request: Request) -> UUID:
    """Reject missing, duplicate or noncanonical registration keys."""
    values = request.headers.getlist("Idempotency-Key")
    return parse_idempotency_key(values[0] if len(values) == 1 else "")


@dataclass(frozen=True)
class CheckerRegistryOperation:
    """One authenticated actor and caller-root CHECKERS registry operation."""

    session: AsyncSession
    service: ExternalCheckerRegistryService
    actor_profile_id: UUID


def registry_http_error(status_code: int) -> StructuredHTTPException:
    """Map private registry failures to one stable bounded error envelope."""
    code, message = {
        403: ("checker_registry_authority_denied", "Checker registry authority denied"),
        404: ("external_checker_registry_entry_not_found", "Checker registry entry not found"),
        409: ("external_checker_registry_conflict", "Checker registry operation conflicts"),
        503: ("external_checker_registry_unavailable", "Checker registry unavailable"),
    }[status_code]
    return StructuredHTTPException(
        status_code=status_code,
        detail=code,
        error_code=code,
        error_message=message,
        retryable=status_code == 503,
    )


async def _registry_operation(
    *,
    request: Request,
    resolved: Any,
    session: AsyncSession,
    operation_id: UUID | None,
) -> AsyncIterator[CheckerRegistryOperation]:
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    context = _authorization_context(
        resolved,
        request_id,
        operation_id if operation_id is not None else correlation_id,
    )
    await session.rollback()
    try:
        async with session.begin():
            authority = checker_registry_authorization(session, context)
            try:
                yield CheckerRegistryOperation(
                    session=session,
                    service=ExternalCheckerRegistryService(session, authority),
                    actor_profile_id=context.actor_profile_id,
                )
            except ExternalCheckerRegistryAuthorizationDenied as exc:
                await session.commit()
                raise registry_http_error(404 if request.method == "GET" else 403) from exc
    except ExternalCheckerRegistryNotFound as exc:
        raise registry_http_error(404) from exc
    except ExternalCheckerRegistryConflict as exc:
        raise registry_http_error(409) from exc
    except (ExternalCheckerRegistryUnavailable, SQLAlchemyError) as exc:
        raise registry_http_error(503) from exc
    finally:
        if session.in_transaction():
            await session.rollback()


async def get_registry_registration(
    request: Request,
    operation_id: Annotated[UUID, Depends(require_registry_key)],
    resolved: Annotated[Any, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[CheckerRegistryOperation]:
    """Bind a registration key to AUTH correlation and one root transaction."""
    async for operation in _registry_operation(
        request=request,
        resolved=resolved,
        session=session,
        operation_id=operation_id,
    ):
        yield operation


async def get_registry_read(
    request: Request,
    resolved: Annotated[Any, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[CheckerRegistryOperation]:
    """Compose one exact read under the ordinary request correlation."""
    async for operation in _registry_operation(
        request=request,
        resolved=resolved,
        session=session,
        operation_id=None,
    ):
        yield operation


RegistryResponse = TypeVar("RegistryResponse", bound=ExternalCheckerRegistryEntry)


async def commit_registry_response(
    operation: CheckerRegistryOperation,
    response: RegistryResponse,
) -> RegistryResponse:
    """Validate a detached response before committing registry and AUTH evidence."""
    adapter = TypeAdapter(type(response))
    detached = adapter.validate_json(adapter.dump_json(response, warnings="error"))
    await operation.session.commit()
    return detached
