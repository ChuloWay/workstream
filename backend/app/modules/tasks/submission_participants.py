"""Private TASK composition ports; public TASK facts remain dependency-independent."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.modules.checkers.api import SubmissionPacketView
from app.modules.checkers.api.post_submit import PostSubmissionEvaluationContent
from app.modules.checkers.api.external_policy import LockedExternalPostSubmitPolicy
from app.modules.checkers.api.selected_post_submit import SelectedPostSubmissionContent
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
    evaluation_content: PostSubmissionEvaluationContent | None = None
    selected_post_submit_policy: LockedExternalPostSubmitPolicy | None = None
    selected_evaluation_content: SelectedPostSubmissionContent | None = None

    def __post_init__(self) -> None:
        """Keep retained legacy and selected content mutually exclusive."""
        if (self.selected_post_submit_policy is None) != (
            self.selected_evaluation_content is None
        ):
            raise ValueError("selected POST admission content is incomplete")
        if (self.evaluation_content is None) == (
            self.selected_evaluation_content is None
        ):
            raise ValueError("admission must select exactly one POST contract")
        if (
            self.selected_evaluation_content is not None
            and self.selected_evaluation_content.policy
            != self.selected_post_submit_policy
        ):
            raise ValueError("selected POST admission policy differs")


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
