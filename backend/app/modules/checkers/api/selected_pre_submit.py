"""Closed facts from the selected default-plus-external PRE execution."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

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
)
