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
    request_id: ResourceId
    request_digest: Sha256
    attempt_id: ResourceId
    result_id: ResourceId
    evaluation_generation: VersionNumber


class ExecutionLease(PostSubmitValue):
    reservation: EvaluationReservation
    lease_id: ResourceId
    lease_generation: VersionNumber
    expires_at: AwareDatetime


class ExecuteFacts(PostSubmitValue):
    request: PostSubmissionEvaluationRequest
    lease: ExecutionLease


class VerifiedMaterialFacts(PostSubmitValue):
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
    @abstractmethod
    async def consume(self, facts: ExecuteFacts) -> ExecuteEvidence: ...


class PreparedFinalization(ABC):
    @abstractmethod
    async def consume(self, facts: FinalizeFacts) -> FinalizeEvidence: ...


class ExecutionAuthorityPort(Protocol):
    async def preflight(self, request: PostSubmissionEvaluationRequest) -> None: ...
    def prepare_execution(
        self, request: PostSubmissionEvaluationRequest
    ) -> AbstractAsyncContextManager[PreparedExecution]: ...


class FinalizationAuthorityPort(Protocol):
    async def preflight(self, request: PostSubmissionEvaluationRequest) -> None: ...
    def prepare_finalization(
        self, request: PostSubmissionEvaluationRequest
    ) -> AbstractAsyncContextManager[PreparedFinalization]: ...


class CompletedEvaluation(PostSubmitValue):
    """Fresh owner projection; the consumer must keep the caller transaction open."""

    reference: PostSubmitCurrentResultReference
    routing_recommendation: Literal["allow_review", "needs_revision", "task_setup_blocked"]
    result: PostSubmissionEvaluationResult


class EvaluationCoordinationPort(Protocol):
    async def reserve_current_evaluation(
        self, request: PostSubmissionEvaluationRequest
    ) -> EvaluationReservation: ...
    async def read_current_result(
        self, request: PostSubmissionEvaluationRequest
    ) -> CompletedEvaluation: ...


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
