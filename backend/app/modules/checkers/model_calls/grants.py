"""One-use private callback grants; paid-effect identity remains in the call ledger."""

import hashlib
import json
import re
import secrets
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid, select, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from app.core.identifiers import new_record_id
from app.db.base import Base
from app.interfaces.external_checker_execution import ExternalCheckerModelGrant
from app.modules.checkers.api.model_calls import (
    ModelCallCurrentExecutionPort,
    ModelCallExecutionFacts,
    ModelCallEffectAuthorityFacts,
    ModelCallUnavailable,
    ModelPaidSlotKey,
    model_action_digest,
)
from app.modules.checkers.api.model_grants import (
    ModelInvocationGrantAuthorityPort,
    ModelInvocationGrantFacts,
)
from app.modules.checkers.model_calls.repository import require_model_call_transaction


class CheckerModelInvocationGrant(Base):
    """No plaintext capability or transcript; exact immutable callback custody only."""

    __tablename__ = "checker_model_invocation_grants"
    __table_args__ = (
        CheckConstraint(
            "(get_byte(uuid_send(id),6)>>4)=7 and (get_byte(uuid_send(id),8)&192)=128",
            name="id_uuid7",
        ),
        CheckConstraint(
            "token_hash ~ '^sha256:[0-9a-f]{64}$' and "
            "external_request_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "(selected_request_sha256 is null or selected_request_sha256 ~ '^sha256:[0-9a-f]{64}$')",
            name="digests",
        ),
        CheckConstraint(
            "(consumed_at is null and selected_request_sha256 is null and selected_attempt_id is null) or "
            "(consumed_at is not null and selected_request_sha256 is not null and selected_attempt_id is not null)",
            name="consumption",
        ),
    )
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(71), nullable=False, unique=True)
    project_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    checker_run_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("checker_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    registry_entry_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("external_checker_registry_entries.id", ondelete="RESTRICT"),
        nullable=False,
    )
    execution_facts: Mapped[dict] = mapped_column(JSONB, nullable=False)
    paid_slot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    external_request_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        nullable=False,
    )
    authorization_evidence_id: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("audit_events.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    selected_request_sha256: Mapped[str | None] = mapped_column(String(71))
    selected_attempt_id: Mapped[str | None] = mapped_column(
        Uuid(as_uuid=False),
        ForeignKey("checker_model_call_attempts.id", ondelete="RESTRICT"),
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def model_grant_token_hash(token: str) -> str:
    """Hash a closed short-lived capability with an explicit domain separator."""
    if type(token) is not str or re.fullmatch(r"model_[0-9a-f]{32}", token) is None:
        raise ModelCallUnavailable("model_grant_unavailable")
    return (
        "sha256:"
        + hashlib.sha256(b"workstream.checker.model-grant.v1\0" + token.encode("ascii")).hexdigest()
    )


class ModelInvocationGrants:
    """Issue and consume invocation custody in caller-owned transactions."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        authority: ModelInvocationGrantAuthorityPort,
        current: ModelCallCurrentExecutionPort,
    ):
        self._session, self._authority, self._current = session, authority, current

    async def issue(
        self,
        execution: ModelCallExecutionFacts,
        slot: ModelPaidSlotKey,
        external_request_digest: str,
        *,
        registry_entry_id: UUID,
    ) -> ExternalCheckerModelGrant:
        """Authorize current binding before creating one private random capability."""
        require_model_call_transaction(self._session)
        execution = ModelCallExecutionFacts.model_validate(execution)
        slot = ModelPaidSlotKey.model_validate(slot)
        token = "model_" + secrets.token_hex(16)
        grant = ExternalCheckerModelGrant(token, external_request_digest)
        token_hash = model_grant_token_hash(token)
        evidence = await self._authority.authorize_grant(
            execution,
            slot,
            external_request_digest,
            token_hash,
        )
        facts = {
            "execution": execution.model_dump(mode="json"),
            "slot": slot.model_dump(mode="json"),
            "external_request_digest": external_request_digest,
            "token_hash": token_hash,
        }
        if evidence.facts_digest != model_action_digest("grant", facts):
            raise ModelCallUnavailable("model_grant_authority_unavailable")
        await self._current.require_current(execution, slot)
        self._session.add(
            CheckerModelInvocationGrant(
                id=str(new_record_id()),
                token_hash=token_hash,
                project_id=str(execution.project_id),
                checker_run_id=str(execution.checker_run_id),
                registry_entry_id=str(registry_entry_id),
                execution_facts=execution.model_dump(mode="json"),
                paid_slot=slot.model_dump(mode="json"),
                external_request_digest=external_request_digest,
                expires_at=execution.worker_lease_expires_at,
                authorization_evidence_id=str(evidence.evidence_id),
            )
        )
        await self._session.flush()
        return grant

    async def resolve(self, token: str, request_digest: str) -> ModelInvocationGrantFacts:
        """Select concealed capability facts; this lookup does not grant model authority."""
        require_model_call_transaction(self._session)
        token_hash = model_grant_token_hash(token)
        row = await self._session.scalar(
            select(CheckerModelInvocationGrant).where(
                CheckerModelInvocationGrant.token_hash == token_hash,
                CheckerModelInvocationGrant.external_request_digest == request_digest,
                CheckerModelInvocationGrant.consumed_at.is_(None),
                CheckerModelInvocationGrant.expires_at > func.clock_timestamp(),
            )
        )
        if row is None:
            raise ModelCallUnavailable("model_grant_unavailable")
        execution = ModelCallExecutionFacts.model_validate_json(json.dumps(row.execution_facts))
        slot = ModelPaidSlotKey.model_validate_json(json.dumps(row.paid_slot))
        if (
            str(execution.project_id),
            str(execution.checker_run_id),
            execution.worker_lease_expires_at,
        ) != (
            row.project_id,
            row.checker_run_id,
            row.expires_at,
        ):
            raise ModelCallUnavailable("model_grant_unavailable")
        return ModelInvocationGrantFacts(
            token_hash, request_digest, execution, slot, UUID(row.registry_entry_id)
        )

    async def consume_prepared(
        self,
        facts: ModelInvocationGrantFacts,
        *,
        request_sha256: str,
        prepared_attempt_id: UUID,
    ) -> None:
        """Consume after ledger preparation in the same AUTH/TASK/slot transaction."""
        from app.modules.checkers.model_calls.repository import ModelCallRepository

        require_model_call_transaction(self._session)
        if re.fullmatch(r"sha256:[0-9a-f]{64}", request_sha256) is None:
            raise ModelCallUnavailable("model_grant_unavailable")
        repo = ModelCallRepository(self._session)
        slot = await repo.slot(facts.slot, lock=True)
        attempt = await repo.attempt(prepared_attempt_id, lock=True)
        if (
            slot is None
            or attempt is None
            or (attempt.slot_id != slot.id or attempt.request_sha256 != request_sha256)
        ):
            raise ModelCallUnavailable("model_grant_unavailable")
        row = await self._session.scalar(
            select(CheckerModelInvocationGrant)
            .where(
                CheckerModelInvocationGrant.token_hash == facts.token_hash,
                CheckerModelInvocationGrant.external_request_digest
                == facts.external_request_digest,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = await self._session.scalar(select(func.clock_timestamp()))
        if (
            row is None
            or row.consumed_at is not None
            or row.expires_at <= now
            or (
                row.execution_facts != facts.execution.model_dump(mode="json")
                or row.paid_slot != facts.slot.model_dump(mode="json")
            )
        ):
            raise ModelCallUnavailable("model_grant_unavailable")
        row.selected_request_sha256, row.consumed_at = request_sha256, now
        row.selected_attempt_id = str(prepared_attempt_id)
        await self._session.flush()

    async def completed_effect(
        self,
        token: str,
        request_digest: str,
        execution: ModelCallExecutionFacts,
    ) -> ModelCallEffectAuthorityFacts:
        """Select exact consumed effect facts; the ledger must freshly authorize their read."""
        from app.modules.checkers.model_calls.models import CheckerModelCallAttempt

        require_model_call_transaction(self._session)
        row = await self._session.scalar(
            select(CheckerModelInvocationGrant).where(
                CheckerModelInvocationGrant.token_hash == model_grant_token_hash(token),
                CheckerModelInvocationGrant.external_request_digest == request_digest,
                CheckerModelInvocationGrant.consumed_at.is_not(None),
            )
        )
        if row is None or row.execution_facts != execution.model_dump(mode="json"):
            raise ModelCallUnavailable("model_grant_completion_unavailable")
        attempt = await self._session.get(CheckerModelCallAttempt, row.selected_attempt_id)
        if attempt is None or attempt.request_sha256 != row.selected_request_sha256:
            raise ModelCallUnavailable("model_grant_completion_unavailable")
        slot = ModelPaidSlotKey.model_validate_json(json.dumps(row.paid_slot))
        return ModelCallEffectAuthorityFacts(
            project_id=execution.project_id,
            task_id=execution.task_id,
            slot_id=UUID(attempt.slot_id),
            slot_key=slot,
            attempt_id=UUID(attempt.id),
            internal_call_request_id=UUID(attempt.internal_call_request_id),
        )
