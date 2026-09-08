"""One-shot failures capture real transaction state before raising a database error."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.actors.service import ActorService
from app.modules.audit.service import AuditService
from app.modules.authorization.admin_service import AdminRoleGrantService
from tests.authorization.admin_access.read_support import READ_ACTIONS
from tests.authorization.admin_access.support import (
    ActorObservation,
    observed_actor,
    stored_authority,
)


@dataclass
class FailureObservation:
    actor_id: UUID
    rows: dict[str, list[dict[str, Any]]] | None = None
    actor: ActorObservation | None = None

    async def capture(self, session: AsyncSession) -> None:
        await session.flush()
        self.rows = await stored_authority(session)
        self.actor = await observed_actor(session, self.actor_id)


def fail_next_commit(
    monkeypatch: pytest.MonkeyPatch,
    actor_id: UUID,
    *,
    grant_operation: str | None = None,
) -> FailureObservation:
    """Fail the feature commit, not an independent mutation rate-control commit."""
    probe = FailureObservation(actor_id)
    original = AsyncSession.commit
    attempted = False
    owner_session: AsyncSession | None = None
    if grant_operation is not None:
        assert grant_operation in {"issue", "revoke"}
        method = f"complete_{grant_operation}"
        complete = getattr(AdminRoleGrantService, method)

        async def remember_owner(service, *args, **kwargs):
            nonlocal owner_session
            owner_session = service._session
            return await complete(service, *args, **kwargs)

        monkeypatch.setattr(AdminRoleGrantService, method, remember_owner)

    async def fail_commit(session):
        nonlocal attempted
        if attempted or (grant_operation is not None and session is not owner_session):
            return await original(session)
        attempted = True
        await probe.capture(session)
        raise SQLAlchemyError("injected late commit failure")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    return probe


def fail_admin_read(
    monkeypatch: pytest.MonkeyPatch,
    actor_id: UUID,
    surface: str,
    stage: str,
) -> FailureObservation:
    if stage == "commit":
        return fail_next_commit(monkeypatch, actor_id)
    probe = FailureObservation(actor_id)
    if stage == "evidence":
        original = AuditService.add_authority_event
        action, _ = READ_ACTIONS[surface]

        async def fail_evidence(service, value):
            if value.action_id is not None and value.action_id.value == action:
                await probe.capture(service._repository._session)
                raise SQLAlchemyError("injected pre-evidence failure")
            return await original(service, value)

        monkeypatch.setattr(AuditService, "add_authority_event", fail_evidence)
    elif stage == "lookup":
        method = "read_admin_profile" if surface == "profile" else "read_admin_identity_link"

        async def fail_lookup(service, _target):
            await probe.capture(service._session)
            raise SQLAlchemyError("injected target lookup failure")

        monkeypatch.setattr(ActorService, method, fail_lookup)
    else:
        assert stage == "touch"

        async def fail_touch(service, _resolved):
            await probe.capture(service._session)
            raise SQLAlchemyError("injected pre-touch failure")

        monkeypatch.setattr(ActorService, "touch_after_authorization", fail_touch)
    return probe
