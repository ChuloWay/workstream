"""SQL delivery facts and single-statement observations; no authority decisions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, cast, func, literal, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.outbox.api import (
    CommittedInvocationObservation,
    DrainObservation,
    OutboxClaim,
)
from app.modules.outbox.models import OutboxDeliveryAttempt, OutboxEvent


async def database_time(session: AsyncSession) -> datetime:
    """Use wall-clock database time even after a transaction waits for a lock."""
    return (await session.execute(select(func.clock_timestamp()))).scalar_one()


def claim_from_attempt(attempt: OutboxDeliveryAttempt) -> OutboxClaim:
    """Detach the exact immutable lease facts from retained custody."""
    return OutboxClaim(
        **{
            name: UUID(attempt.project_id) if name == "project_id" else getattr(attempt, name)
            for name in OutboxClaim.model_fields
        }
    )


def matches_event(event: OutboxEvent, claim: OutboxClaim) -> bool:
    """Require all current event facts, including the lease and generation."""
    return (
        event.delivery_state == "claimed"
        and event.event_id == claim.event_id
        and event.project_id == str(claim.project_id)
        and event.payload_digest == claim.payload_digest
        and event.claim_generation == claim.claim_generation
        and event.claim_owner == claim.claim_owner
        and event.claimed_at == claim.claimed_at
        and event.claim_expires_at == claim.claim_expires_at
    )


class DeliveryRepository:
    """A participant in the orchestrator's transaction, never its committer."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind one owner session."""
        self.session = session

    async def event(
        self, event_id: UUID, project_id: UUID, *, lock: bool = False
    ) -> OutboxEvent | None:
        """Conceal foreign events; refresh identity-map values after any lock wait."""
        query = (
            select(OutboxEvent)
            .where(
                OutboxEvent.event_id == event_id,
                OutboxEvent.project_id == str(project_id),
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update()
        return (await self.session.execute(query)).scalar_one_or_none()

    async def attempt(
        self, claim: OutboxClaim, *, lock: bool = False
    ) -> OutboxDeliveryAttempt | None:
        """Read or lock custody only after its event when locking."""
        query = (
            select(OutboxDeliveryAttempt)
            .where(
                OutboxDeliveryAttempt.event_id == claim.event_id,
                OutboxDeliveryAttempt.claim_generation == claim.claim_generation,
                OutboxDeliveryAttempt.project_id == str(claim.project_id),
            )
            .execution_options(populate_existing=True)
        )
        if lock:
            query = query.with_for_update()
        return (await self.session.execute(query)).scalar_one_or_none()

    async def observe(self, claim: OutboxClaim) -> CommittedInvocationObservation | None:
        """One nonlocking snapshot of exact committed invocation and live lease."""
        e, a = OutboxEvent, OutboxDeliveryAttempt
        query = (
            select(func.clock_timestamp())
            .select_from(e)
            .join(
                a,
                and_(a.event_id == e.event_id, a.claim_generation == e.claim_generation),
            )
            .where(
                e.event_id == claim.event_id,
                e.project_id == str(claim.project_id),
                e.payload_digest == claim.payload_digest,
                e.delivery_state == "claimed",
                a.stage == "invoked",
                a.outcome_json.is_(None),
                e.claim_generation == claim.claim_generation,
                e.claim_owner == claim.claim_owner,
                e.claimed_at == claim.claimed_at,
                e.claim_expires_at == claim.claim_expires_at,
                a.project_id == e.project_id,
                a.payload_digest == e.payload_digest,
                a.claim_owner == e.claim_owner,
                a.claimed_at == e.claimed_at,
                a.claim_expires_at == e.claim_expires_at,
                e.claim_expires_at > func.clock_timestamp(),
            )
        )
        observed = (await self.session.execute(query)).scalar_one_or_none()
        return (
            None
            if observed is None
            else CommittedInvocationObservation(claim=claim, observed_at=observed)
        )

    async def drain(self, project_id: UUID, keys: tuple[tuple[str, int], ...]) -> DrainObservation:
        """One statement, disjoint state counts and explicitly overlapping facts."""
        e, a = OutboxEvent, OutboxDeliveryAttempt
        supported = (
            or_(*(and_(e.event_type == t, e.event_version == v) for t, v in keys))
            if keys
            else literal(False)
        )
        count = lambda predicate: func.count().filter(predicate)  # noqa: E731
        row = (
            (
                await self.session.execute(
                    select(
                        func.statement_timestamp().label("observed_at"),
                        count(e.delivery_state == "pending").label("pending"),
                        count(e.delivery_state == "claimed").label("claimed"),
                        count(e.delivery_state == "retryable").label("retryable"),
                        count(a.stage == "invoked").label("invoked"),
                        count(
                            and_(
                                a.stage == "completed",
                                func.jsonb_extract_path_text(
                                    cast(a.outcome_json, JSONB),
                                    "invocation_unknown",
                                )
                                == "true",
                            )
                        ).label("unresolved"),
                        count(
                            and_(
                                e.delivery_state.in_(("pending", "claimed", "retryable")),
                                ~supported,
                            )
                        ).label("unsupported"),
                        count(e.delivery_state == "dead_letter").label("dead_letter"),
                        count(and_(e.claim_generation > 0, a.event_id.is_(None))).label(
                            "missing_custody"
                        ),
                    )
                    .select_from(e)
                    .outerjoin(
                        a,
                        and_(
                            a.event_id == e.event_id,
                            a.claim_generation == e.claim_generation,
                        ),
                    )
                    .where(e.project_id == str(project_id))
                )
            )
            .mappings()
            .one()
        )
        if row["missing_custody"]:
            from app.modules.outbox.api import DeliveryPersistenceError

            raise DeliveryPersistenceError("outbox_observation_failed")
        return DrainObservation(
            project_id=project_id, **{k: v for k, v in row.items() if k != "missing_custody"}
        )
