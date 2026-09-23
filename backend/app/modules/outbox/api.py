"""Immutable delivery facts; none of these values grant feature authority."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DeliveryUnavailable(Exception):
    """Concealed invalid, stale, denied or unavailable delivery operation."""


class DeliveryPersistenceError(Exception):
    """Sanitized database observation or delivery failure."""


class DeliveryValue(BaseModel):
    """Closed immutable values with strict scalar admission."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)


class OutboxClaim(DeliveryValue):
    """Exact lease facts, not authority or proof of committed invocation."""

    event_id: UUID
    project_id: UUID
    payload_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    claim_generation: int = Field(ge=1, le=2147483647)
    claim_owner: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,120}$")
    claimed_at: datetime
    claim_expires_at: datetime

    @field_validator("event_id", "project_id")
    @classmethod
    def plain_uuid(cls, value: UUID) -> UUID:
        """Detach driver UUID subclasses at the public value boundary."""
        return UUID(str(value))

    @field_validator("claimed_at", "claim_expires_at")
    @classmethod
    def aware_utc(cls, value: datetime) -> datetime:
        """Reject ambiguous leases and normalize exact timestamps."""
        normalized = None
        try:
            if value.utcoffset() is not None:
                normalized = value.astimezone(timezone.utc)
        except Exception:
            pass
        if normalized is None:
            raise ValueError("outbox timestamp requires a valid timezone")
        return normalized

    @model_validator(mode="after")
    def ordered_lease(self) -> Self:
        """Require positive lease duration."""
        if not 0 < (self.claim_expires_at - self.claimed_at).total_seconds() <= 3600:
            raise ValueError("outbox lease must be positive and at most one hour")
        return self


class OutboxEventEnvelope(DeliveryValue):
    """Detached immutable event and canonical payload text for one invocation."""

    claim: OutboxClaim
    event_type: str
    event_version: int
    aggregate_type: str
    aggregate_id: UUID
    correlation_id: str
    causation_event_id: UUID | None
    idempotency_key: str
    occurred_at: datetime
    payload_json: str


class HandlerOutcome(StrEnum):
    """Only RETRY asserts that repeating the feature operation is safe."""

    ACKNOWLEDGE = "acknowledge"
    RETRY = "retry"
    REJECT = "reject"


class FinalizationCause(StrEnum):
    """Closed reasons used to construct database-timed outcomes."""

    ACKNOWLEDGE = "acknowledge"
    RETRY = "retry"
    REJECT = "reject"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class DeliveryReceipt(DeliveryValue):
    """Exact committed outcome including its canonical digest and claim."""

    claim: OutboxClaim
    outcome_json: str
    outcome_digest: str


class CommittedInvocationObservation(DeliveryValue):
    """Point-in-time facts only: no lease extension, authority or feature fence."""

    claim: OutboxClaim
    observed_at: datetime


class CommittedInvocationPort(Protocol):
    """Independent committed observation, never a dispatcher writer session."""

    async def observe_invocation(
        self,
        claim: OutboxClaim,
    ) -> CommittedInvocationObservation | None:
        """Return one concealed unavailable result for all noncurrent invocations."""
        ...


class OutboxHandler(Protocol):
    """Feature owner supplies its own AUTH, transaction fence and idempotency."""

    async def __call__(self, envelope: OutboxEventEnvelope) -> HandlerOutcome:
        """Return safe bounded disposition, never provider payload or authority."""
        ...


class DeliveryOptions(DeliveryValue):
    """Explicit bounded composition options; no environment or plugin framework."""

    lease_seconds: int = Field(default=300, ge=1, le=3600)
    handler_timeout_seconds: int = Field(default=240, ge=1, le=3600)
    max_attempts: int = Field(default=5, ge=1, le=100)
    retry_base_seconds: int = Field(default=5, ge=1, le=3600)
    retry_cap_seconds: int = Field(default=300, ge=1, le=86400)

    @model_validator(mode="after")
    def ordered_limits(self) -> Self:
        """Leave a lease margin and bound retry scheduling."""
        if (
            self.handler_timeout_seconds >= self.lease_seconds
            or self.retry_cap_seconds < self.retry_base_seconds
        ):
            raise ValueError("outbox delivery limits are inconsistent")
        return self


class DrainObservation(DeliveryValue):
    """One SQL snapshot; overlapping counts must not be summed as readiness."""

    project_id: UUID
    observed_at: datetime
    pending: int
    claimed: int
    retryable: int
    invoked: int
    unresolved: int
    unsupported: int
    dead_letter: int
