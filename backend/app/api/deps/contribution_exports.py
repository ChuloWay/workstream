"""One fresh repeatable-read response transaction with canonical AUTH evidence."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Request, Response
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth import contribution_read_authorization
from app.adapters.contributions import contribution_export_service, contribution_export_csv
from app.api.deps.authorization import (
    _authorization_context, get_authorization_actor, get_authorization_actor_identity,
)
from app.core.api_controls import StructuredHTTPException, request_ids
from app.db.session import get_db_session
from app.modules.contributions.api.records import (
    ContributionExportPort, ContributionExportResponse, ContributionExportTooLarge,
    ContributionExportUnavailable, ContributionReadDenied, ContributionReadRequest,
)


@dataclass(frozen=True)
class ContributionExportRequest:
    """Detached caller identity and one mandatory authorized read owner."""

    session: AsyncSession
    service: ContributionExportPort
    actor_profile_id: UUID


def contribution_export_http_error(status: int) -> StructuredHTTPException:
    """Conceal denied scopes and keep limits/storage errors free of owner facts."""
    code, message = {
        404: ("contribution_export_not_found", "Contribution evidence unavailable"),
        422: ("contribution_export_too_large", "Contribution export exceeds 1000 records; narrow the filters"),
        503: ("contribution_export_unavailable", "Contribution export unavailable"),
    }[status]
    return StructuredHTTPException(status_code=status, detail=code, error_code=code,
                                   error_message=message, retryable=status == 503)


async def get_contribution_export_request(
    request: Request,
    resolved: Annotated[Any, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[ContributionExportRequest]:
    """Discard admission's refresh transaction and select RR before the first AUTH SQL."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    context = _authorization_context(resolved, request_id, correlation_id)
    actor = await get_authorization_actor_identity(resolved)
    await session.rollback()
    try:
        async with session.begin():
            await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            try:
                yield ContributionExportRequest(session, contribution_export_service(
                    session, authorization=contribution_read_authorization(session, context),
                ), actor.actor_profile_id)
            except ContributionReadDenied as exc:
                await session.commit()
                raise contribution_export_http_error(404) from exc
    except ContributionExportTooLarge as exc:
        raise contribution_export_http_error(422) from exc
    except (ContributionExportUnavailable, SQLAlchemyError, ValidationError, TypeError) as exc:
        raise contribution_export_http_error(503) from exc
    finally:
        if session.in_transaction():
            await session.rollback()


async def contribution_export_response(
    context: ContributionExportRequest, selected: ContributionReadRequest,
) -> Response:
    """Fully validate and serialize bytes while authority locks remain held, then commit."""
    projection = ContributionExportResponse.model_validate(await context.service.read(selected))
    if selected.output_format == "csv":
        body = contribution_export_csv(projection)
        response = Response(body, media_type="text/csv; charset=utf-8",
                            headers={"Content-Disposition": 'attachment; filename="contributions.csv"'})
    else:
        body = projection.model_dump_json().encode("utf-8")
        ContributionExportResponse.model_validate_json(body)
        response = Response(body, media_type="application/json")
    await context.session.commit()
    return response
