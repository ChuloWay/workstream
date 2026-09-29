"""Exact post-submit byte access; neither durable execution nor live authority."""

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from app.modules.checkers.api import PostSubmissionEvaluationRequest, PostSubmissionEvaluationResult


class PostSubmissionMaterializationUnavailable(RuntimeError):
    """Reject material without exposing provider or private packet details."""


@dataclass(frozen=True, slots=True)
class SubmissionMaterialEntry:
    """Expose verified archive metadata without a filesystem path."""
    normalized_path: str
    entry_type: Literal["file", "directory"]
    byte_count: int
    sha256: str | None
    executable: bool | None


class SubmissionMaterialView(Protocol):
    """Permit bounded reads only during the consumer callback."""

    @property
    def entries(self) -> tuple[SubmissionMaterialEntry, ...]:
        """Return verified entries only while the consumer is running."""

    def read_file(self, normalized_path: str, *, maximum_bytes: int) -> bytes:
        """Read one bounded verified file without filesystem authority."""


class PostSubmissionMaterialConsumer(Protocol):
    """Evaluate scoped input asynchronously and return detached phase facts."""
    async def evaluate(
        self, request: PostSubmissionEvaluationRequest, material: SubmissionMaterialView,
    ) -> PostSubmissionEvaluationResult:
        """Return detached closed phase facts before ART revokes material access."""


@dataclass(frozen=True, slots=True)
class PostSubmissionMaterializationResult:
    """Bind a validated evaluation to its verified immutable input custody."""
    submission_id: UUID
    submission_version: int
    admission_id: UUID
    binding_id: UUID
    content_id: UUID
    replica_id: UUID
    content_sha256: str
    byte_count: int
    semantic_manifest_sha256: str
    evaluation: PostSubmissionEvaluationResult


class PostSubmissionMaterializationPort(Protocol):
    """Verify and scope exact input without publishing durable checker results."""
    async def materialize(
        self, request: PostSubmissionEvaluationRequest, consumer: PostSubmissionMaterialConsumer,
    ) -> PostSubmissionMaterializationResult:
        """Verify exact stored bytes and finish cleanup before returning phase facts."""
