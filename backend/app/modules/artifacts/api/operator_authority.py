"""Public ART authority facts for exact Operator reads and recovery."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, final
from uuid import UUID


class ArtifactOperatorAuthorityDenied(RuntimeError):
    """An exact AUTH decision denied an ART Operator operation."""


class ArtifactOperatorAuthorityUnavailable(RuntimeError):
    """An ART Operator decision could not be durably evidenced."""


class ArtifactOperatorResourceType(StrEnum):
    """Closed provider-neutral resource vocabulary selected by ART."""

    BINDING_SCOPE = "artifact_binding_scope"
    CONTENT = "artifact_content"
    REPLICA = "artifact_replica"
    VERIFICATION_JOB = "artifact_verification_job"
    RECOVERY_ATTEMPT = "artifact_recovery_attempt"
    AUDIT_RESOURCE = "artifact_audit_resource"
    ADMISSION_SCOPE = "artifact_admission_scope"


@final
@dataclass(frozen=True, slots=True)
class ArtifactOperatorAuthorityFacts:
    """Server-composed canonical selector and every associated project."""

    resource_type: ArtifactOperatorResourceType
    resource_id: str
    project_ids: tuple[UUID, ...]
    action_id: str
    record_id: UUID | None = None


@final
@dataclass(frozen=True, slots=True)
class ArtifactOperatorAuthorizationEvidence:
    """Privacy-bounded result of one canonical AUTH decision."""

    action_id: str
    permission_id: str
    decision_id: UUID


class ArtifactOperatorAuthority(Protocol):
    """Fresh exact ART read authority; the caller owns commit and rollback."""

    async def authorize(
        self, *, authorization_context: object, facts: ArtifactOperatorAuthorityFacts
    ) -> ArtifactOperatorAuthorizationEvidence: ...

    async def restage_denial(self) -> bool:
        """Stage the exact rolled-back denial in a clean caller transaction."""


@final
@dataclass(frozen=True, slots=True)
class ArtifactRecoveryAuthorityFacts:
    """Canonical facts bound to one exact Operator retry decision."""

    project_id: UUID
    task_id: UUID
    submission_id: UUID | None
    source_verification_job_id: UUID
    expected_source_job_cas_version: int


@final
@dataclass(frozen=True, slots=True)
class ArtifactRecoveryAuthorizationEvidence:
    """Privacy-bounded result of one canonical retry decision."""

    action_id: str
    permission_id: str
    decision_id: UUID


class ArtifactRecoveryAuthority(Protocol):
    """Fresh retry authority; ART owns the recovery transaction."""

    async def authorize(
        self, *, authorization_context: object, facts: ArtifactRecoveryAuthorityFacts
    ) -> ArtifactRecoveryAuthorizationEvidence: ...

    async def restage_denial(self) -> bool:
        """Stage the exact rolled-back denial in a clean caller transaction."""
