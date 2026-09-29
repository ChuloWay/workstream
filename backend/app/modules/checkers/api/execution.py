"""Exact execution custody contracts; no value is self-authorizing."""

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from typing import Literal, Protocol

from pydantic import AwareDatetime, Field

from app.modules.checkers.api.post_submit import (
    PostSubmissionEvaluationRequest,
    PostSubmissionEvaluationResult,
    PostSubmitCurrentResultReference,
)
from app.modules.checkers.api.post_submit_catalogue import (
    PostSubmitValue,
    ResourceId,
    Sha256,
    VersionNumber,
)

COMPLETION_EVENT = "PostSubmissionEvaluationCompleted"


class CheckerExecutionUnavailable(RuntimeError):
    """Conceal absent, foreign, denied, stale or already leased execution."""


class CheckerRequestConflict(CheckerExecutionUnavailable):
    """A request key or generation already belongs to different facts."""


class EvaluationReservation(PostSubmitValue):
    """Stable request, attempt and result identities reserved together."""

    request_id: ResourceId
    request_digest: Sha256
    attempt_id: ResourceId
    result_id: ResourceId
    evaluation_generation: VersionNumber


class ExecutionLease(PostSubmitValue):
    """Database-timed generation granting temporary use of one reserved attempt."""

    reservation: EvaluationReservation
    lease_id: ResourceId
    lease_generation: VersionNumber
    expires_at: AwareDatetime


class ExecuteFacts(PostSubmitValue):
    """Exact request and lease consumed by execution authority."""

    request: PostSubmissionEvaluationRequest
    lease: ExecutionLease


class VerifiedMaterialFacts(PostSubmitValue):
    """ART-verified byte and lineage facts required for completed results."""

    submission_id: ResourceId
    submission_version: VersionNumber
    admission_id: ResourceId
    binding_id: ResourceId
    content_id: ResourceId
    replica_id: ResourceId
    content_sha256: Sha256
    byte_count: int = Field(strict=True, ge=0)
    semantic_manifest_sha256: Sha256


class FinalizeFacts(ExecuteFacts):
    """Exact terminal result and material custody consumed by finalization authority."""

    result: PostSubmissionEvaluationResult
    material: VerifiedMaterialFacts | None
    output_binding_ids: tuple[ResourceId, ...] = Field(max_length=0)


class ExecuteEvidence(PostSubmitValue):
    """Opaque action-specific receipt; real AUTH custody is installed by 04D."""

    evidence_id: ResourceId
    facts_digest: Sha256


class FinalizeEvidence(PostSubmitValue):
    """Nominally distinct from execute evidence, even for the same run."""

    evidence_id: ResourceId
    facts_digest: Sha256


class PreparedExecution(ABC):
    """Single-operation prepared authority for execution facts."""

    @abstractmethod
    async def consume(self, facts: ExecuteFacts) -> ExecuteEvidence:
        """Consume execution facts and return their action-specific receipt."""
        ...


class PreparedFinalization(ABC):
    """Separately prepared authority for terminal result publication."""

    @abstractmethod
    async def consume(self, facts: FinalizeFacts) -> FinalizeEvidence:
        """Consume finalization facts and return their distinct receipt."""
        ...


class ExecutionAuthorityPort(Protocol):
    """Provide fresh authorization before acquiring an execution lease."""

    async def preflight(self, request: PostSubmissionEvaluationRequest) -> None:
        """Reject unavailable execution authority before entering preparation."""
        ...

    def prepare_execution(
        self, request: PostSubmissionEvaluationRequest
    ) -> AbstractAsyncContextManager[PreparedExecution]:
        """Hold execution preparation within the caller transaction."""
        ...


class FinalizationAuthorityPort(Protocol):
    """Provide fresh authorization for atomic terminal publication."""

    async def preflight(self, request: PostSubmissionEvaluationRequest) -> None:
        """Reject unavailable finalization authority before preparation."""
        ...

    def prepare_finalization(
        self, request: PostSubmissionEvaluationRequest
    ) -> AbstractAsyncContextManager[PreparedFinalization]:
        """Hold finalization preparation within the terminal transaction."""
        ...


class CompletedEvaluation(PostSubmitValue):
    """Fresh owner projection; the consumer must keep the caller transaction open."""

    reference: PostSubmitCurrentResultReference
    routing_recommendation: Literal["allow_review", "needs_revision", "task_setup_blocked"]
    result: PostSubmissionEvaluationResult


class EvaluationCoordinationPort(Protocol):
    """Reserve and read exact current evaluations in caller transactions."""

    async def reserve_current_evaluation(
        self, request: PostSubmissionEvaluationRequest
    ) -> EvaluationReservation:
        """Reserve or replay the exact request without committing the caller transaction."""
        ...

    async def read_current_result(
        self, request: PostSubmissionEvaluationRequest
    ) -> CompletedEvaluation:
        """Lock and return the completed evaluation for the exact current request."""
        ...


class EvaluationCompletion(PostSubmitValue):
    """Bounded publication facts, never perpetual authority or private packet data."""

    project_id: ResourceId
    task_id: ResourceId
    submission_id: ResourceId
    reference: PostSubmitCurrentResultReference
    routing_recommendation: Literal["allow_review", "needs_revision", "task_setup_blocked"]
    output_binding_ids: tuple[ResourceId, ...] = Field(max_length=0)
    execute_evidence_id: ResourceId
    finalize_evidence_id: ResourceId
