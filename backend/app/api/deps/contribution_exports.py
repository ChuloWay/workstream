"""One fresh repeatable-read response transaction with canonical AUTH evidence."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Request, Response
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth import contribution_read_authorization
from app.adapters.contributions import contribution_export_service, contribution_export_csv
from app.api.deps.authorization import (
    _authorization_context, get_authorization_actor, get_authorization_actor_identity,
)
from app.core.api_controls import StructuredHTTPException, request_ids
from app.core.config import decode_pagination_cursor_hmac_secret
from app.db.session import get_db_session
from app.modules.contributions.api.records import (
    ContributionExportAtCapacity, ContributionExportPort, ContributionExportResponse,
    ContributionExportTooLarge, ContributionExportUnavailable, ContributionReadDenied,
    ContributionReadRequest, InvalidContributionCursor,
)


@dataclass(frozen=True)
class ContributionExportRequest:
    """Detached caller identity and one mandatory authorized read owner."""

    session: AsyncSession
    service: ContributionExportPort
    actor_profile_id: UUID


def contribution_export_http_error(
    status: int, *, retry_after: int | None = None,
) -> StructuredHTTPException:
    """Conceal denied scopes and keep limits/storage errors free of owner facts."""
    code, message = {
        404: ("contribution_export_not_found", "Contribution evidence unavailable"),
        422: ("contribution_export_too_large", "Contribution export exceeds 100000 records; narrow the filters"),
        429: ("contribution_export_at_capacity", "Contribution export capacity is temporarily full"),
        503: ("contribution_export_unavailable", "Contribution export unavailable"),
    }[status]
    return StructuredHTTPException(status_code=status, detail=code, error_code=code,
                                   error_message=message, retryable=status in {429, 503},
                                   headers=({"Retry-After": str(retry_after)}
                                            if retry_after is not None else None))


def contribution_cursor_http_error() -> StructuredHTTPException:
    """Reject malformed, substituted, missing and expired cursors generically."""
    code = "contribution_export_cursor_invalid"
    return StructuredHTTPException(status_code=422, detail=code, error_code=code,
                                   error_message="Invalid contribution export cursor")


async def get_contribution_export_request(
    request: Request,
    resolved: Annotated[Any, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[ContributionExportRequest]:
    """Capture identity once; the response owns each complete authorized snapshot."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    context = _authorization_context(resolved, request_id, correlation_id)
    actor = await get_authorization_actor_identity(resolved)
    await session.rollback()
    secret = request.app.state.settings.pagination_cursor_hmac_secret
    if secret is None:
        raise contribution_export_http_error(503)
    try:
        yield ContributionExportRequest(session, contribution_export_service(
            session, authorization=contribution_read_authorization(session, context),
            cursor_secret=decode_pagination_cursor_hmac_secret(secret),
        ), actor.actor_profile_id)
    except ContributionReadDenied as exc:
        raise contribution_export_http_error(404) from exc
    except ContributionExportTooLarge as exc:
        raise contribution_export_http_error(422) from exc
    except InvalidContributionCursor as exc:
        raise contribution_cursor_http_error() from exc
    except ContributionExportAtCapacity as exc:
        if session.in_transaction():
            await session.rollback()
        raise contribution_export_http_error(429, retry_after=exc.retry_after) from exc
    except (ContributionExportUnavailable, SQLAlchemyError, ValidationError, TypeError) as exc:
        raise contribution_export_http_error(503) from exc
    finally:
        if session.in_transaction():
            await session.rollback()


def _serialization_conflict(error: BaseException) -> bool:
    """Recognize only a driver's serialization refusal through owner wrappers."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, DBAPIError) and getattr(current.orig, "sqlstate", None) == "40001":
            return True
        current = current.__cause__ or current.__context__
    return False


async def contribution_export_response(
    context: ContributionExportRequest, selected: ContributionReadRequest,
) -> Response:
    """Retry one refused read snapshot; retain only fully serialized fresh evidence."""
    for attempt in range(2):
        try:
            async with context.session.begin():
                await context.session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
                try:
                    projection = ContributionExportResponse.model_validate(await context.service.read(selected))
                except ContributionReadDenied:
                    # The canonical DENY belongs to this fresh attempt, not the
                    # aborted snapshot. Preserve it before public concealment.
                    await context.session.commit()
                    raise
                if selected.output_format == "csv":
                    body = contribution_export_csv(projection)
                    headers = {"Content-Disposition": 'attachment; filename="contributions.csv"'}
                    if projection.next_cursor is not None:
                        headers["X-Workstream-Next-Cursor"] = projection.next_cursor
                    response = Response(body, media_type="text/csv; charset=utf-8",
                                        headers=headers)
                else:
                    body = projection.model_dump_json().encode("utf-8")
                    ContributionExportResponse.model_validate_json(body)
                    response = Response(body, media_type="application/json")
                await context.session.commit()
                return response
        except (ContributionExportUnavailable, SQLAlchemyError) as exc:
            if attempt or not _serialization_conflict(exc):
                raise
            if context.session.in_transaction():
                await context.session.rollback()
    raise AssertionError("bounded contribution read attempt did not return")
