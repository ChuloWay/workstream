"""Hidden atomic setup closure, with unavailable production authorization."""

from __future__ import annotations

from contextlib import asynccontextmanager

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.authorization.api import (
    AuthorizationDenied,
    AuthorizationUnavailable,
    PreparedAuthorizationInvalid,
    PreparedSetupFinalization,
    ProjectSetupFinalizationLocator,
    SetupFinalizationAuthorizationPort,
    setup_finalization_identity,
)
from app.modules.projects.api import (
    ProjectGuideSetupFinalizationCommand,
    ProjectGuideSetupFinalizationError,
    ProjectGuideSetupFinalizationReceipt,
)
from app.modules.projects.repository import ProjectRepositoryIntegrityError

from .finalization_payloads import (
    compose_facts,
    deny,
    new_row,
    public_receipt,
    require_authority,
    require_lineage,
    require_replay,
    require_source_shape,
)
from .repository import GuideCompilationIntegrityError, GuideCompilationRepository


class _UnavailableAuthorization:
    """No live adapter exists until the separate AUTH-12B2 activation."""

    @asynccontextmanager
    async def prepare_setup_finalization(self, _locator):
        """Deny before any product serialization lock or mutation."""
        raise AuthorizationUnavailable("setup finalization authority is unavailable")
        yield  # pragma: no cover


class GuideCompilationFinalizationService:
    """Validate existing custody and finalize inside the caller's root transaction."""

    def __init__(
        self, session: AsyncSession, authorization: SetupFinalizationAuthorizationPort | None = None
    ) -> None:
        """Bind one session and a purpose-specific request-local authorization port."""
        self._session = session
        self._authorization = (
            authorization if authorization is not None else _UnavailableAuthorization()
        )
        self._repository = GuideCompilationRepository(session)

    async def finalize(
        self, command: ProjectGuideSetupFinalizationCommand
    ) -> ProjectGuideSetupFinalizationReceipt:
        """Return new or replayed custody; never commit or dispatch downstream work."""
        if (
            not self._session.in_transaction()
            or self._session.in_nested_transaction()
            or self._session.new
            or self._session.dirty
            or self._session.deleted
        ):
            deny()
        try:
            return await self._finalize(command)
        except ProjectGuideSetupFinalizationError:
            raise
        except (AuthorizationDenied, AuthorizationUnavailable, PreparedAuthorizationInvalid):
            raise ProjectGuideSetupFinalizationError("service_authority_denied") from None
        except (
            GuideCompilationIntegrityError,
            ProjectRepositoryIntegrityError,
            ValidationError,
            ValueError,
        ):
            raise ProjectGuideSetupFinalizationError("source_state_unavailable") from None
        except SQLAlchemyError:
            raise ProjectGuideSetupFinalizationError("storage_unavailable") from None

    async def _finalize(self, command) -> ProjectGuideSetupFinalizationReceipt:
        """Close PREP before touching product state, including every replay path."""
        finalization_id, operation_id, _ = setup_finalization_identity(
            command.setup_run_id, command.setup_generation, command.compilation_id
        )
        attempt_id = await self._repository.finalization_attempt_id(command)
        locator = ProjectSetupFinalizationLocator(
            project_id=command.project_id, operation_id=operation_id
        )
        replay = None
        async with self._authorization.prepare_setup_finalization(locator) as capability:
            if not isinstance(capability, PreparedSetupFinalization):
                raise ProjectGuideSetupFinalizationError("service_authority_denied")
            view = await self._repository.lock_finalization(command, attempt_id)
            # Always re-query after acquiring setup serialization, including initial misses.
            rows = await self._repository.finalization_receipts(command, operation_id)
            require_lineage(view, command)
            if rows:
                if (
                    len(rows) != 1
                    or rows[0].id != finalization_id
                    or rows[0].operation_id != operation_id
                ):
                    deny()
                replay = rows[0]
                facts = compose_facts(view, replay.source_state_digest)
                require_replay(view, replay, facts)
                from uuid import UUID

                await capability.validate_replay(
                    facts, UUID(replay.authorization_decision_event_id)
                )
            else:
                facts = compose_facts(view, require_source_shape(view))
                authority = await capability.consume_new(facts)
                require_authority(authority, facts)
        # __aexit__ (including a failing close) has completed before any product mutation.
        if replay is not None:
            return public_receipt(replay)
        row = new_row(facts, authority)
        await self._repository.persist_finalization(row, view.setup)
        return public_receipt(row)
