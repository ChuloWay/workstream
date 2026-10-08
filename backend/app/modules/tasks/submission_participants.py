"""Private TASK composition ports; public TASK facts remain dependency-independent."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.checkers.api import SubmissionPacketView
from app.modules.checkers.api.post_submit import PostSubmissionEvaluationContent
from app.modules.projects.api import ProjectLockedPolicyContextFacts
from app.modules.tasks.api import TaskSubmissionContextFacts


@dataclass(frozen=True, slots=True)
class SubmissionArtifactAdmissionRequest:
    admission_id: UUID
    submission_id: UUID
    submission_version: int
    task_context: TaskSubmissionContextFacts
    project_context: ProjectLockedPolicyContextFacts
    packet: SubmissionPacketView


@dataclass(frozen=True, slots=True)
class SubmissionArtifactBindingFacts:
    binding_id: UUID
    content_id: UUID
    binding_decision_id: UUID
    archive_sha256: str
    byte_count: int


@dataclass(frozen=True, slots=True)
class SubmissionArtifactAdmissionResult(SubmissionArtifactBindingFacts):
    evaluation_content: PostSubmissionEvaluationContent


@dataclass(frozen=True, slots=True)
class SubmissionArtifactReplayRequest:
    admission_id: UUID
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    contributor_id: UUID
    submission_id: UUID
    submission_version: int
    packet_sha256: str


class SubmissionArtifactAdmissionPort(Protocol):
    async def consume(self, request: SubmissionArtifactAdmissionRequest) -> SubmissionArtifactAdmissionResult:
        """Consume once and project real material using already-locked policy facts."""

    async def read_consumed(self, request: SubmissionArtifactReplayRequest) -> SubmissionArtifactBindingFacts:
        """Select and reauthorize retained binding custody without new consumption."""
