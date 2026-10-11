"""Closed facts from the selected default-plus-external PRE execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.default_checker import WORKSTREAM_DEFAULT_BEHAVIOR_SHA256
from app.modules.checkers.api.default_checker import WorkstreamDefaultCheckerResult
from app.modules.checkers.api.external import ExternalCheckerExecutionResult


@dataclass(frozen=True, slots=True)
class ExternalPreSubmitIsolationFacts:
    """Observed sandbox identity detached from the trusted service response."""

    repository: str
    platform_manifest_digest: str
    platform_manifest_media_type: str
    platform_manifest_byte_count: int
    operating_system: str
    architecture: str
    config_image_id: str
    runtime: str
    isolation_mode: str
    sandbox_uid: int
    sandbox_gid: int


@dataclass(frozen=True, slots=True)
class ExternalPreSubmitMemberFacts:
    """One completed required project PRE image in canonical policy order."""

    order: int
    requirement_id: str
    registry_entry_id: UUID
    registry_entry_digest: str
    request_digest: str
    result: ExternalCheckerExecutionResult
    isolation: ExternalPreSubmitIsolationFacts

    def __post_init__(self) -> None:
        if (
            type(self.order) is not int
            or self.order < 0
            or not self.requirement_id
            or self.result.outcome != "completed"
            or self.result.request_digest != self.request_digest
            or self.result.registry_entry_id != self.registry_entry_id
            or self.result.registry_entry_digest != self.registry_entry_digest
        ):
            raise ValueError("external PRE member facts are invalid")


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitExecutionFacts:
    """One default result followed by the executed required external prefix."""

    policy_sha256: str
    workstream_default: WorkstreamDefaultCheckerResult
    required_external_count: int
    external_members: tuple[ExternalPreSubmitMemberFacts, ...]
    eligible: bool

    def __post_init__(self) -> None:
        members = self.external_members
        if (
            not self.policy_sha256.startswith("sha256:")
            or len(self.policy_sha256) != 71
            or type(self.required_external_count) is not int
            or self.required_external_count < 0
            or tuple(item.order for item in members) != tuple(range(len(members)))
            or len({item.requirement_id for item in members}) != len(members)
            or len(members) > self.required_external_count
        ):
            raise ValueError("selected PRE execution facts are invalid")
        external_passed = all(item.result.verdict == "passed" for item in members)
        complete = len(members) == self.required_external_count
        if self.eligible != (
            self.workstream_default.eligible and complete and external_passed
        ):
            raise ValueError("selected PRE eligibility differs from required results")
        if (
            not self.workstream_default.eligible
            and members
            or any(item.result.verdict == "failed" for item in members[:-1])
        ):
            raise ValueError("selected PRE execution continued after a blocker")

    def canonical_body(self) -> dict[str, object]:
        """Return the complete bounded result body retained by the durable owner."""
        return {
            "schema_version": "workstream.selected_pre_submit_execution.v1",
            "policy_sha256": self.policy_sha256,
            "workstream_default": self.workstream_default.model_dump(mode="json"),
            "required_external_count": self.required_external_count,
            "external_members": [
                {
                    "order": member.order,
                    "requirement_id": member.requirement_id,
                    "registry_entry_id": str(member.registry_entry_id),
                    "registry_entry_digest": member.registry_entry_digest,
                    "request_digest": member.request_digest,
                    "result": member.result.model_dump(mode="json"),
                    "isolation": asdict(member.isolation),
                }
                for member in self.external_members
            ],
            "eligible": self.eligible,
        }

    @property
    def result_digest(self) -> str:
        """Bind every default, project-image and observed-isolation result fact."""
        return canonical_json_hash(self.canonical_body())


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitReservationFacts:
    """Complete durable PRE request reserved before any external work starts."""

    actor_profile_id: UUID
    identity_link_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    attempt_id: UUID
    attempt_request_digest: str
    prepared_generation_id: UUID
    policy_sha256: str
    default_behavior_sha256: str
    default_input_sha256: str
    archive_sha256: str
    archive_byte_count: int
    semantic_manifest_sha256: str

    def __post_init__(self) -> None:
        """Reject partial authority, material, policy or default-input custody."""
        identifiers = (
            self.actor_profile_id,
            self.identity_link_id,
            self.project_id,
            self.task_id,
            self.assignment_id,
            self.attempt_id,
            self.prepared_generation_id,
        )
        digests = (
            self.attempt_request_digest,
            self.policy_sha256,
            self.default_behavior_sha256,
            self.default_input_sha256,
            self.archive_sha256,
            self.semantic_manifest_sha256,
        )
        if (
            any(type(value) is not UUID for value in identifiers)
            or any(
                type(value) is not str
                or len(value) != 71
                or not value.startswith("sha256:")
                for value in digests
            )
            or self.default_behavior_sha256 != WORKSTREAM_DEFAULT_BEHAVIOR_SHA256
            or type(self.archive_byte_count) is not int
            or self.archive_byte_count < 0
        ):
            raise ValueError("selected PRE reservation facts are invalid")

    def canonical_body(self) -> dict[str, object]:
        """Bind the actual contributor, task, ART generation, policy and bytes."""
        return {
            "schema_version": "workstream.selected_pre_submit_reservation.v1",
            "actor_profile_id": str(self.actor_profile_id),
            "identity_link_id": str(self.identity_link_id),
            "project_id": str(self.project_id),
            "task_id": str(self.task_id),
            "assignment_id": str(self.assignment_id),
            "attempt_id": str(self.attempt_id),
            "attempt_request_digest": self.attempt_request_digest,
            "prepared_generation_id": str(self.prepared_generation_id),
            "policy_sha256": self.policy_sha256,
            "default_behavior_sha256": self.default_behavior_sha256,
            "default_input_sha256": self.default_input_sha256,
            "archive_sha256": self.archive_sha256,
            "archive_byte_count": self.archive_byte_count,
            "semantic_manifest_sha256": self.semantic_manifest_sha256,
        }

    @property
    def request_digest(self) -> str:
        """Return the immutable request identity used by reserve and replay."""
        return canonical_json_hash(self.canonical_body())


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitLeaseFacts:
    """Database-timed generation for one genuine pre-admission ART attempt."""

    reservation: SelectedPreSubmitReservationFacts
    lease_id: UUID
    lease_generation: int
    lease_expires_at: datetime

    def __post_init__(self) -> None:
        """Reject a copied identifier or an unbounded/non-current lease shape."""
        if (
            type(self.reservation) is not SelectedPreSubmitReservationFacts
            or type(self.lease_id) is not UUID
            or type(self.lease_generation) is not int
            or self.lease_generation < 1
            or self.lease_expires_at.tzinfo is None
        ):
            raise ValueError("selected PRE lease facts are invalid")


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitTerminalFacts:
    """Exact terminal value finalized under a fresh TASK-first transaction."""

    lease: SelectedPreSubmitLeaseFacts
    outcome: Literal["completed", "infrastructure_failed"]
    execution: SelectedPreSubmitExecutionFacts | None
    infrastructure_failure_code: str | None
    queued_at: datetime
    started_at: datetime
    completed_at: datetime

    def __post_init__(self) -> None:
        """Keep work findings separate from recoverable infrastructure outcomes."""
        if type(self.lease) is not SelectedPreSubmitLeaseFacts:
            raise ValueError("selected PRE terminal lease is invalid")
        if any(value.tzinfo is None for value in (
            self.queued_at,
            self.started_at,
            self.completed_at,
        )) or not (self.queued_at <= self.started_at <= self.completed_at):
            raise ValueError("selected PRE terminal timing is invalid")
        if self.outcome == "completed":
            if (
                type(self.execution) is not SelectedPreSubmitExecutionFacts
                or self.infrastructure_failure_code is not None
                or self.execution.policy_sha256
                != self.lease.reservation.policy_sha256
            ):
                raise ValueError("selected PRE completed outcome is invalid")
        elif (
            self.execution is not None
            or self.infrastructure_failure_code not in {
                "capacity_exceeded",
                "deadline_exceeded",
                "material_unavailable",
                "implementation_unavailable",
                "invalid_output",
            }
        ):
            raise ValueError("selected PRE infrastructure outcome is invalid")

    def canonical_body(self) -> dict[str, object]:
        """Return persisted latency, lease and terminal facts without private paths."""
        return {
            "schema_version": "workstream.selected_pre_submit_terminal.v1",
            "reservation": self.lease.reservation.canonical_body(),
            "request_digest": self.lease.reservation.request_digest,
            "lease_id": str(self.lease.lease_id),
            "lease_generation": self.lease.lease_generation,
            "lease_expires_at": self.lease.lease_expires_at.isoformat(),
            "outcome": self.outcome,
            "execution": self.execution.canonical_body() if self.execution else None,
            "infrastructure_failure_code": self.infrastructure_failure_code,
            "queued_at": self.queued_at.isoformat(),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "queue_latency_ms": int(
                (self.started_at - self.queued_at).total_seconds() * 1000
            ),
            "execution_latency_ms": int(
                (self.completed_at - self.started_at).total_seconds() * 1000
            ),
        }

    @property
    def terminal_digest(self) -> str:
        """Bind the exact terminal body used by replay and admission."""
        return canonical_json_hash(self.canonical_body())


class SelectedPreSubmitInfrastructureUnavailable(RuntimeError):
    """Retain a recoverable PRE infrastructure category, never a work failure."""

    def __init__(self, code: str) -> None:
        if code not in {
            "capacity_exceeded",
            "deadline_exceeded",
            "material_unavailable",
            "implementation_unavailable",
            "invalid_output",
        }:
            raise ValueError("selected PRE infrastructure failure is invalid")
        self.code = code
        super().__init__(code)


__all__ = (
    "ExternalPreSubmitIsolationFacts",
    "ExternalPreSubmitMemberFacts",
    "SelectedPreSubmitExecutionFacts",
    "SelectedPreSubmitInfrastructureUnavailable",
    "SelectedPreSubmitLeaseFacts",
    "SelectedPreSubmitReservationFacts",
    "SelectedPreSubmitTerminalFacts",
)
