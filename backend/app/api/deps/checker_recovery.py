"""HTTP transaction roots for exact Operator checker recovery."""

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.checkers import checker_retry_service
from app.api.deps.authorization import (
    AuthorizationDenied,
    AuthorizationEvidenceUnavailable,
    ResolvedActor,
    _authorization_context,
    get_authorization_actor,
)
from app.core.api_controls import StructuredHTTPException, parse_idempotency_key, request_ids
from app.db.session import get_db_session
from app.modules.checkers.api.execution import (
    CheckerExecutionUnavailable,
    CheckerRequestConflict,
    CheckerRetryAuthorityDenied,
    CheckerRetryCommand,
    CheckerRetryCursorInvalid,
    CheckerRetryRequest,
    CheckerRetryResult,
    CheckerRetrySourcePage,
    CheckerRetrySourceQuery,
)


def require_checker_retry_key(request: Request) -> UUID:
    """Reject absent, duplicate or malformed retry keys before product mutation."""
    values = request.headers.getlist("Idempotency-Key")
    return parse_idempotency_key(values[0] if len(values) == 1 else "")


def _concealed() -> StructuredHTTPException:
    return StructuredHTTPException(
        status_code=404,
        detail="Checker recovery source not found",
        error_code="checker_recovery_source_not_found",
        error_message="Checker recovery source not found",
    )


def _unavailable() -> StructuredHTTPException:
    return StructuredHTTPException(
        status_code=503,
        detail="Checker recovery unavailable",
        error_code="checker_recovery_unavailable",
        error_message="Checker recovery unavailable",
        retryable=True,
    )


class CheckerRetryCommands:
    """Bind the public selector/body to CHECKERS's existing atomic writer."""

    def __init__(self, session: AsyncSession, service, key: UUID) -> None:
        self._session, self._service, self._key = session, service, key

    async def retry(
        self, project_id: UUID, source_run_id: UUID, request: CheckerRetryRequest,
    ) -> CheckerRetryResult:
        result = await self._service.retry(CheckerRetryCommand(
            project_id=project_id,
            source_run_id=source_run_id,
            request_key=self._key,
            reason=request.reason,
        ))
        await self._session.commit()
        return result


class CheckerRetryReads:
    """Authorize, project and commit one exact discovery page."""

    def __init__(self, session: AsyncSession, service) -> None:
        self._session, self._service = session, service

    async def discover(
        self, project_id: UUID, *, limit: int, cursor: str | None,
    ) -> CheckerRetrySourcePage:
        result = await self._service.discover(CheckerRetrySourceQuery(
            project_id=project_id, limit=limit, cursor=cursor,
        ))
        await self._session.commit()
        return result


async def get_checker_retry_commands(
    request: Request,
    key: Annotated[UUID, Depends(require_checker_retry_key)],
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[CheckerRetryCommands]:
    """Own mutation commit, canonical denial evidence and fail-closed rollback."""
    context = _authorization_context(resolved, key, key)
    await session.rollback()
    service = checker_retry_service(
        session,
        context,
        cursor_secret=request.app.state.settings.pagination_cursor_hmac_secret,
    )
    try:
        yield CheckerRetryCommands(session, service, key)
    except CheckerRetryAuthorityDenied as exc:
        await session.rollback()
        try:
            if await service.restage_denial(exc):
                await session.commit()
        except (AuthorizationEvidenceUnavailable, SQLAlchemyError) as evidence_error:
            await session.rollback()
            raise _unavailable() from evidence_error
        raise _concealed() from exc
    except CheckerRequestConflict as exc:
        await session.rollback()
        raise StructuredHTTPException(
            status_code=409,
            detail="Checker retry request conflicts with retained facts",
            error_code="checker_retry_request_conflict",
            error_message="Checker retry request conflicts with retained facts",
        ) from exc
    except CheckerExecutionUnavailable as exc:
        await session.rollback()
        raise _concealed() from exc
    except (AuthorizationEvidenceUnavailable, SQLAlchemyError) as exc:
        await session.rollback()
        raise _unavailable() from exc
    except BaseException:
        await session.rollback()
        raise
    finally:
        if session.in_transaction():
            await session.rollback()


async def get_checker_retry_reads(
    request: Request,
    resolved: Annotated[ResolvedActor, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[CheckerRetryReads]:
    """Own read decision commit and canonical concealed denial evidence."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    context = _authorization_context(resolved, request_id, correlation_id)
    await session.rollback()
    service = checker_retry_service(
        session,
        context,
        cursor_secret=request.app.state.settings.pagination_cursor_hmac_secret,
    )
    try:
        yield CheckerRetryReads(session, service)
    except AuthorizationDenied as exc:
        await session.rollback()
        try:
            if await service.restage_discovery_denial(exc):
                await session.commit()
        except (AuthorizationEvidenceUnavailable, SQLAlchemyError) as evidence_error:
            await session.rollback()
            raise _unavailable() from evidence_error
        raise _concealed() from exc
    except CheckerRetryCursorInvalid as exc:
        await session.rollback()
        raise StructuredHTTPException(
            status_code=422,
            detail="Invalid checker recovery cursor",
            error_code="validation_error",
            error_message="Invalid checker recovery cursor",
        ) from exc
    except (CheckerExecutionUnavailable, AuthorizationEvidenceUnavailable, SQLAlchemyError) as exc:
        await session.rollback()
        raise _unavailable() from exc
    except BaseException:
        await session.rollback()
        raise
    finally:
        if session.in_transaction():
            await session.rollback()
