"""Closed evidence-only facts from selected external POST images."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from uuid import UUID

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.external import ExternalCheckerExecutionResult


@dataclass(frozen=True, slots=True)
class ExternalPostSubmitIsolationFacts:
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
class ExternalPostSubmitMemberFacts:
    """One normalized POST image result in exact locked policy order."""

    order: int
    requirement_id: str
    registry_entry_id: UUID
    registry_entry_digest: str
    request_digest: str
    result: ExternalCheckerExecutionResult
    isolation: ExternalPostSubmitIsolationFacts

    def __post_init__(self) -> None:
        if (
            type(self.order) is not int
            or self.order < 0
            or not self.requirement_id
            or self.result.outcome != "completed"
            or self.result.request_digest != self.request_digest
            or self.result.registry_entry_id != self.registry_entry_id
            or self.result.registry_entry_digest != self.registry_entry_digest
            or self.result.phase != "post_submit"
        ):
            raise ValueError("external POST member facts are invalid")


@dataclass(frozen=True, slots=True)
class SelectedPostSubmitExecutionFacts:
    """Complete evidence-only result from every locked external POST image."""

    policy_sha256: str
    required_external_count: int
    external_members: tuple[ExternalPostSubmitMemberFacts, ...]

    def __post_init__(self) -> None:
        members = self.external_members
        if (
            type(self.policy_sha256) is not str
            or len(self.policy_sha256) != 71
            or not self.policy_sha256.startswith("sha256:")
            or type(self.required_external_count) is not int
            or self.required_external_count < 0
            or len(members) != self.required_external_count
            or tuple(item.order for item in members) != tuple(range(len(members)))
            or len({item.requirement_id for item in members}) != len(members)
        ):
            raise ValueError("selected POST execution facts are invalid")

    def canonical_body(self) -> dict[str, object]:
        """Return exact evidence and isolation without any acceptance signal."""
        return {
            "schema_version": "workstream.selected_post_submit_execution.v1",
            "policy_sha256": self.policy_sha256,
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
        }

    @property
    def result_digest(self) -> str:
        """Bind every required image result and observed sandbox fact."""
        return canonical_json_hash(self.canonical_body())


class SelectedPostSubmitInfrastructureUnavailable(RuntimeError):
    """Retain a recoverable POST infrastructure category, never a work verdict."""

    def __init__(self, code: str) -> None:
        if code not in {
            "capacity_exceeded",
            "deadline_exceeded",
            "material_unavailable",
            "implementation_unavailable",
            "invalid_output",
        }:
            raise ValueError("selected POST infrastructure failure is invalid")
        self.code = code
        super().__init__(code)


__all__ = (
    "ExternalPostSubmitIsolationFacts",
    "ExternalPostSubmitMemberFacts",
    "SelectedPostSubmitExecutionFacts",
    "SelectedPostSubmitInfrastructureUnavailable",
)
