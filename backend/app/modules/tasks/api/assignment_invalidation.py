"""Exact hidden assignment reconciliation contracts; no live service permission."""

from dataclasses import dataclass
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from app.modules.audit.api import AuthorityInvalidationFacts
from app.modules.outbox.api import OutboxEventEnvelope

ASSIGNMENT_INVALIDATION_EVENT = "TaskAssignmentAuthorityInvalidationRequested"


class AssignmentInvalidationUnavailable(RuntimeError):
    """Concealed unavailable, stale or denied reconciliation."""


class AssignmentInvalidationTarget(BaseModel):
    """Original assignment identity captured by the future atomic AUTH producer."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    authority_invalidation_event_id: UUID


class AssignmentInvalidationAuthorityFacts(BaseModel):
    """Complete effect target consumed under TASK and exact-assignment locks."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    target: AssignmentInvalidationTarget
    cause: AuthorityInvalidationFacts
    envelope: OutboxEventEnvelope
    task_status: str
    locked_context_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class AssignmentInvalidationAuthority:
    """Future exact fixed-service decision; test substitutes are explicitly synthetic."""

    actor_profile_id: UUID
    decision_id: UUID


class AssignmentInvalidationAuthorizationPort(Protocol):
    async def prepare(self, facts: AssignmentInvalidationAuthorityFacts) -> object: ...

    async def consume(
        self,
        handle: object,
        facts: AssignmentInvalidationAuthorityFacts,
    ) -> AssignmentInvalidationAuthority: ...

    def close(self, handle: object) -> None: ...


def assignment_invalidation_evidence_id(target: AssignmentInvalidationTarget) -> UUID:
    """One immutable effect identity across transport events and generations."""
    return uuid5(
        NAMESPACE_URL,
        f"workstream:assignment-authority-revoked:{target.authority_invalidation_event_id}:{target.assignment_id}",
    )


@dataclass(frozen=True, slots=True)
class AssignmentInvalidationEvidence:
    target: AssignmentInvalidationTarget
    authority: AssignmentInvalidationAuthority
    from_status: str


class AssignmentInvalidationAuditPort(Protocol):
    async def read_release(
        self, target: AssignmentInvalidationTarget
    ) -> AssignmentInvalidationEvidence | None:
        """Validate an exact immutable release receipt; never select current work."""
        ...

    async def record_release(self, evidence: AssignmentInvalidationEvidence) -> None: ...
