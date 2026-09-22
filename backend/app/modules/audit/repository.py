"""Database access methods for shared audit records."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import Row, and_, case, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.schemas import LifecycleAuditEventType
from app.modules.tasks.models import AuditEvent, WorkstreamTask


LIFECYCLE_AUTH_SOURCE = "local_lifecycle"
_LIFECYCLE_REPLAY_FIELDS = (
    "entity_type",
    "entity_id",
    "event_type",
    "from_status",
    "to_status",
    "actor_id",
    "external_subject",
    "external_issuer",
    "actor_roles",
    "claim_snapshot",
    "auth_source",
    "is_dev_auth",
    "reason",
    "event_payload",
    "event_domain",
    "event_version",
    "occurred_at",
)


class LifecycleAuditConflict(ValueError):
    """Signal changed reuse of an immutable lifecycle audit identity."""


class AuditRepository:
    """Wraps persistence for audit events independent of domain services."""

    def __init__(self, session: AsyncSession) -> None:
        """Create a repository bound to one database session.

        Args:
            session: Async SQLAlchemy session for the current unit of work.
        """
        self._session = session

    async def add_audit_event(self, event: AuditEvent) -> AuditEvent:
        """Persist an audit event.

        Args:
            event: Audit event model to persist.

        Returns:
            Persisted audit event model.
        """
        if event.event_domain == "authority":
            raise ValueError("authority events require the typed audit service")
        if event.auth_source == LIFECYCLE_AUTH_SOURCE:
            raise ValueError("lifecycle events require the typed audit participant")
        return await self._persist(event)

    async def _add_validated_lifecycle_event(self, event: AuditEvent) -> AuditEvent:
        """Return exact replay or flush one participant-validated lifecycle event."""
        if event.event_domain != "legacy_lifecycle" or event.auth_source != LIFECYCLE_AUTH_SOURCE:
            raise ValueError("expected validated lifecycle audit event")
        await self._session.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:event_id, 0))"),
            {"event_id": event.id},
        )
        existing = await self._session.get(AuditEvent, event.id)
        if existing is not None:
            if existing.event_domain != "legacy_lifecycle" or any(
                getattr(existing, field) != getattr(event, field)
                for field in _LIFECYCLE_REPLAY_FIELDS
            ):
                raise LifecycleAuditConflict("lifecycle audit identity conflict")
            return existing
        return await self._persist(event)

    async def _add_validated_authority_event(self, event: AuditEvent) -> AuditEvent:
        """Persist an authority event already validated by AuditService."""
        if event.event_domain != "authority":
            raise ValueError("expected authority audit event")
        return await self._persist(event)

    async def get_authority_event(self, event_id: str) -> AuditEvent | None:
        """Return one authority cause visible in the caller transaction."""
        return await self._session.scalar(
            select(AuditEvent).where(
                AuditEvent.id == event_id, AuditEvent.event_domain == "authority"
            )
        )

    async def _persist(self, event: AuditEvent) -> AuditEvent:
        """Flush one event without taking transaction ownership."""
        self._session.add(event)
        await self._session.flush()
        await self._session.refresh(event)
        return event

    async def list_audit_events(self, entity_type: str, entity_id: str) -> Sequence[AuditEvent]:
        """List events for one entity in database creation order."""
        result = await self._session.execute(
            select(AuditEvent)
            .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
            .order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc())
        )
        return result.scalars().all()

    async def read_task_evidence_rows(
        self, project_id: UUID, task_id: UUID, limit: int,
        after_created_at: datetime | None, after_event_id: UUID | None,
    ) -> Sequence[Row]:
        """Select one scoped statement snapshot without private payload loading.

        A task marker distinguishes missing scope from empty/exhausted history.
        TASK supplies validated selectors and translates the fixed scalar rows.
        """
        task, event = WorkstreamTask, AuditEvent
        conditions = [
            event.entity_type == "task", event.entity_id == task.id,
            event.event_domain == "legacy_lifecycle",
        ]
        if after_created_at is not None:
            conditions.append(tuple_(event.created_at, event.id) > tuple_(after_created_at, str(after_event_id)))
        refs = event.event_payload["references"]
        typed_transition = and_(
            event.auth_source == LIFECYCLE_AUTH_SOURCE,
            event.event_type.in_((
                LifecycleAuditEventType.TASK_CLAIMED.value,
                LifecycleAuditEventType.TASK_STARTED.value,
                LifecycleAuditEventType.TASK_START_OVERRIDDEN.value,
            )),
        )
        statement = select(
            task.id.label("scoped_task_id"), event.id.label("event_id"), event.event_type,
            event.from_status, event.to_status, event.actor_id, event.created_at,
            case((typed_transition, refs["project_id"].as_string())).label("reference_project_id"),
            case((typed_transition, refs["task_id"].as_string())).label("reference_task_id"),
            case((typed_transition, refs["assignment_id"].as_string())).label("assignment_id"),
            case((typed_transition, refs["authorization_decision_id"].as_string())).label("authorization_decision_id"),
        ).select_from(task).outerjoin(event, and_(*conditions)).where(
            task.project_id == str(project_id), task.id == str(task_id),
        ).order_by(event.created_at, event.id).limit(limit + 1)
        with self._session.no_autoflush:
            return (await self._session.execute(statement)).all()
