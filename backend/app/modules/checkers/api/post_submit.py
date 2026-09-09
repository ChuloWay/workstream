"""Detached, bounded post-submit phase facts; no persistence or authorization."""

from __future__ import annotations

from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, StrictInt, StrictStr, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.post_submit_catalogue import (
    ByteCount,
    CompiledPostSubmitPolicyV2,
    GuideVersion,
    Identifier,
    PostSubmitCatalogue,
    PostSubmitValue,
    ResourceId,
    Severity,
    Sha256,
    VersionNumber,
    canonical_post_submit_bytes,
)

Text = Annotated[StrictStr, Field(max_length=65_536)]
PathText = Annotated[StrictStr, Field(max_length=1000)]
KeyText = Annotated[StrictStr, Field(max_length=200)]
HashText = Annotated[StrictStr, Field(max_length=128)]
CounterValue = Annotated[StrictInt, Field(ge=0, le=1024)]


class PostSubmitManifestEntry(PostSubmitValue):
    """Untrusted structural text remains representable so checkers can reject it."""

    artifact: PathText
    hash: HashText
    notes: Annotated[StrictStr, Field(max_length=4096)] | None = None
    size_bytes: ByteCount | None = None


class PostSubmitEvidenceEntry(PostSubmitValue):
    """A finite evidence projection without arbitrary metadata or lazy relations."""

    label: KeyText
    uri: PathText | None = None
    hash: HashText | None = None
    type: KeyText
    key: KeyText | None = None
    policy_key: KeyText | None = None
    evidence_key: KeyText | None = None
    required_evidence_key: KeyText | None = None


class PostSubmitPolicyInputs(PostSubmitValue):
    """Detached effective-policy values; the later owning resolver verifies derivation."""

    required_evidence_keys: tuple[PathText, ...] = Field(default=(), max_length=256)
    required_artifact_paths: tuple[PathText, ...] = Field(default=(), max_length=256)
    forbidden_artifact_patterns: tuple[PathText, ...] = Field(default=(), max_length=256)
    required_attestation_terms: tuple[PathText, ...] = Field(default=(), max_length=256)


class ObservedPostSubmitContext(PostSubmitValue):
    """Nullable observed source fields permit precise missing-context outcomes."""

    project_id: ResourceId | None = None
    guide_id: ResourceId | None = None
    guide_version: GuideVersion | None = None
    source_id: ResourceId | None = None
    source_hash: Sha256 | None = None
    compilation_id: ResourceId | None = None
    compilation_result_hash: Sha256 | None = None
    effective_policy_id: ResourceId | None = None
    effective_policy_hash: Sha256 | None = None
    pre_policy_id: ResourceId | None = None
    pre_policy_hash: Sha256 | None = None
    post_policy_id: ResourceId | None = None
    post_policy_version: GuideVersion | None = None
    post_policy_hash: Sha256 | None = None
    review_policy_id: ResourceId | None = None
    review_generation: VersionNumber | None = None
    review_hash: Sha256 | None = None
    revision_policy_id: ResourceId | None = None
    revision_generation: VersionNumber | None = None
    revision_hash: Sha256 | None = None
    contribution_policy_version_id: ResourceId | None = None


class ExpectedPostSubmitContext(ObservedPostSubmitContext):
    """The complete expected lineage, without a legacy PaymentPolicy dependency."""

    project_id: ResourceId
    guide_id: ResourceId
    guide_version: GuideVersion
    source_id: ResourceId
    source_hash: Sha256
    compilation_id: ResourceId
    compilation_result_hash: Sha256
    effective_policy_id: ResourceId
    effective_policy_hash: Sha256
    pre_policy_id: ResourceId
    pre_policy_hash: Sha256
    post_policy_id: ResourceId
    post_policy_version: GuideVersion
    post_policy_hash: Sha256
    review_policy_id: ResourceId
    review_generation: VersionNumber
    review_hash: Sha256
    revision_policy_id: ResourceId
    revision_generation: VersionNumber
    revision_hash: Sha256
    contribution_policy_version_id: ResourceId

    @model_validator(mode="after")
    def validate_versions(self) -> Self:
        """Preserve the existing post-policy/guide string-version relationship."""
        if self.post_policy_version != self.guide_version:
            raise ValueError("post-submit guide and policy versions differ")
        return self


class PostSubmissionStructuralInput(PostSubmitValue):
    """Immutable detached values consumed by the actual structural handlers."""

    schema_version: Literal["post_submit_structural_input.v1"] = "post_submit_structural_input.v1"
    summary: Text
    worker_attestation: Text
    package_hash: HashText
    criteria: Text
    manifest: tuple[PostSubmitManifestEntry, ...] = Field(max_length=1024)
    evidence: tuple[PostSubmitEvidenceEntry, ...] = Field(max_length=1024)
    policy_inputs: PostSubmitPolicyInputs
    observed_context: ObservedPostSubmitContext


class PostSubmissionEvaluationRequest(PostSubmitValue):
    """Hash-bound value consistency, never stored ownership or execution authority."""

    schema_version: Literal["post_submit_evaluation_request.v1"] = (
        "post_submit_evaluation_request.v1"
    )
    evaluation_request_id: ResourceId
    evaluation_generation: VersionNumber
    project_id: ResourceId
    task_id: ResourceId
    assignment_id: ResourceId
    submission_id: ResourceId
    submission_version: VersionNumber
    content_id: ResourceId
    binding_id: ResourceId
    content_sha256: Sha256
    byte_count: ByteCount
    expected_context: ExpectedPostSubmitContext
    catalogue: PostSubmitCatalogue
    policy: CompiledPostSubmitPolicyV2
    structural_input: PostSubmissionStructuralInput
    request_sha256: Sha256

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        """Reject inconsistent duplicated facts before the unavailable execution port."""
        if len(canonical_post_submit_bytes(self)) > 1_048_576:
            raise ValueError("post-submit request capacity exceeded")
        if (
            self.project_id != self.expected_context.project_id
            or self.project_id != self.policy.project_id
        ):
            raise ValueError("post-submit request project mismatch")
        if self.policy.guide_version != self.expected_context.guide_version:
            raise ValueError("post-submit request guide version mismatch")
        if self.policy.policy_hash != self.expected_context.post_policy_hash:
            raise ValueError("post-submit request policy hash mismatch")
        self.policy.validate_catalogue(self.catalogue)
        expected = canonical_json_hash(self.model_dump(mode="json", exclude={"request_sha256"}))
        if self.request_sha256 != expected:
            raise ValueError("post-submit request digest mismatch")
        return self


class PostSubmitCounter(PostSubmitValue):
    """Closed counters cannot carry arbitrary checker messages or references."""

    key: Literal["artifact_count", "missing_count", "invalid_count", "matched_count"]
    value: CounterValue


class PostSubmitMemberResult(PostSubmitValue):
    """One sanitized structural outcome, validated against its pinned definition."""

    schema_version: Literal["post_submit_structural_result.v1"] = "post_submit_structural_result.v1"
    checker_id: Identifier
    definition_version: Literal["v0.2"] = "v0.2"
    implementation_version: Identifier
    status: Literal["passed", "warning", "failed"]
    code: Literal[
        "passed",
        "packet_fields_missing",
        "policy_context_invalid",
        "evidence_missing",
        "evidence_structure_invalid",
        "required_files_missing",
        "forbidden_path_present",
        "attestation_missing",
        "placeholder_signal",
        "acceptance_criteria_missing",
    ]
    failure_category: Literal["none", "submission_structure", "task_configuration"]
    severity: Severity
    counters: tuple[PostSubmitCounter, ...] = Field(default=(), max_length=4)

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        """Check closed passing/failing combinations and finite counters."""
        passed_fields = (
            self.code == "passed",
            self.failure_category == "none",
            self.severity == "info",
        )
        if self.status == "passed" and not all(passed_fields):
            raise ValueError("post-submit passing result shape is invalid")
        if self.status != "passed" and any(passed_fields):
            raise ValueError("post-submit nonpassing result shape is invalid")
        if len({item.key for item in self.counters}) != len(self.counters):
            raise ValueError("post-submit result counters repeat")
        if len(canonical_post_submit_bytes(self)) > 4096:
            raise ValueError("post-submit member result capacity exceeded")
        return self

    def validate_catalogue(self, catalogue: PostSubmitCatalogue) -> None:
        """Require exactly the registered implementation's claim-specific outcome."""
        self = PostSubmitMemberResult.model_validate(self)
        definition = catalogue.definition(self.checker_id, self.definition_version)
        if self.implementation_version != definition.implementation_version:
            raise ValueError("post-submit result implementation mismatch")
        if self.status != "passed" and (
            self.code,
            self.failure_category,
            self.status,
            self.severity,
        ) != (
            definition.failure_code,
            definition.failure_category,
            definition.failure_status,
            definition.failure_severity,
        ):
            raise ValueError("post-submit result does not match registered claim")


class PostSubmissionEvaluationResult(PostSubmitValue):
    """A typed phase result is not evidence that a durable result is current."""

    schema_version: Literal["post_submit_evaluation_result.v1"] = "post_submit_evaluation_result.v1"
    request_id: ResourceId
    request_digest: Sha256
    attempt_id: ResourceId
    evaluation_generation: VersionNumber
    result_id: ResourceId
    result_digest: Sha256
    outcome: Literal["completed", "infrastructure_failed"]
    member_results: tuple[PostSubmitMemberResult, ...] = Field(max_length=9)
    infrastructure_failure_code: (
        Literal[
            "capacity_exceeded",
            "deadline_exceeded",
            "implementation_unavailable",
            "invalid_output",
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        """Separate infrastructure failure and recompute exact result identity."""
        if self.outcome == "completed":
            if not self.member_results or self.infrastructure_failure_code is not None:
                raise ValueError("post-submit completed result shape is invalid")
        elif self.member_results or self.infrastructure_failure_code is None:
            raise ValueError("post-submit infrastructure result shape is invalid")
        if len(canonical_post_submit_bytes(self)) > 65536:
            raise ValueError("post-submit phase result capacity exceeded")
        if self.result_digest != canonical_json_hash(
            self.model_dump(mode="json", exclude={"result_digest"})
        ):
            raise ValueError("post-submit result digest mismatch")
        return self

    def validate_request(self, request: PostSubmissionEvaluationRequest) -> None:
        """Bind the complete member list to the exact request without claiming custody."""
        self = PostSubmissionEvaluationResult.model_validate(self)
        request = PostSubmissionEvaluationRequest.model_validate(request)
        if (self.request_id, self.request_digest, self.evaluation_generation) != (
            request.evaluation_request_id,
            request.request_sha256,
            request.evaluation_generation,
        ):
            raise ValueError("post-submit result request mismatch")
        if self.outcome == "completed":
            expected = tuple(
                (entry.checker_id, entry.definition_version, entry.implementation_version)
                for entry in request.policy.entries
            )
            actual = tuple(
                (item.checker_id, item.definition_version, item.implementation_version)
                for item in self.member_results
            )
            if actual != expected:
                raise ValueError("post-submit result members mismatch")
            for member in self.member_results:
                member.validate_catalogue(request.catalogue)


class PostSubmitCurrentResultReference(PostSubmitValue):
    """A later owner-issued reference, with no self-authorizing is_current flag."""

    schema_version: Literal["post_submit_current_result_reference.v1"] = (
        "post_submit_current_result_reference.v1"
    )
    request_id: ResourceId
    request_digest: Sha256
    attempt_id: ResourceId
    evaluation_generation: VersionNumber
    result_id: ResourceId
    result_digest: Sha256

    def validate_result(self, result: PostSubmissionEvaluationResult) -> None:
        """Match exact completed result identity; the repository must prove currentness."""
        self = PostSubmitCurrentResultReference.model_validate(self)
        result = PostSubmissionEvaluationResult.model_validate(result)
        names = (
            "request_id",
            "request_digest",
            "attempt_id",
            "evaluation_generation",
            "result_id",
            "result_digest",
        )
        if result.outcome != "completed" or any(
            getattr(self, key) != getattr(result, key) for key in names
        ):
            raise ValueError("post-submit current reference result mismatch")


class PostSubmissionExecutionUnavailable(RuntimeError):
    """The real phase executor and its authority are intentionally not installed."""


class PostSubmissionExecutionPort(Protocol):
    """One complete locked phase command, never caller-selected individual checks."""

    async def evaluate_post_submission(
        self, request: PostSubmissionEvaluationRequest
    ) -> PostSubmissionEvaluationResult:
        """Evaluate one request after later owner resolution and authority checks."""
        ...


class UnavailablePostSubmissionExecution:
    """Deny execution after validating a well-formed request, with no external I/O."""

    async def evaluate_post_submission(
        self, request: PostSubmissionEvaluationRequest
    ) -> PostSubmissionEvaluationResult:
        """Keep production unavailable until ARCH-04C/04D supply custody and authority."""
        PostSubmissionEvaluationRequest.model_validate(request)
        raise PostSubmissionExecutionUnavailable("post_submit_execution_unavailable")
