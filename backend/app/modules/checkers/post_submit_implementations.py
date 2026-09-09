"""Private detached-input adaptation over the existing registered structural rules."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.checkers.api.post_submit import (
    PostSubmissionEvaluationRequest,
    PostSubmitEvidenceEntry,
    PostSubmitMemberResult,
)
from app.modules.checkers.api.post_submit_catalogue import PostSubmitDefinition
from app.modules.checkers.runner import (
    CheckerContext,
    CheckerOutcome,
    CheckerRegistry,
    _fail,
    _pass,
)


@dataclass(frozen=True)
class _TaskView:
    """Detached criteria consumed by the existing presence handler."""

    acceptance_criteria: str


@dataclass(frozen=True)
class _EvidenceView:
    """Private copied evidence values for the existing structural helpers."""

    label: str
    uri: str | None
    hash: str | None
    type: str
    metadata_json: dict[str, str]

    @classmethod
    def from_facts(cls, facts: PostSubmitEvidenceEntry) -> _EvidenceView:
        """Copy only closed evidence keys for the existing pure presence rule."""
        keys = ("key", "policy_key", "evidence_key", "required_evidence_key")
        metadata = {key: value for key in keys if (value := getattr(facts, key)) is not None}
        return cls(facts.label, facts.uri, facts.hash, facts.type, metadata)


@dataclass(frozen=True)
class _SubmissionView:
    """Private copies shield immutable source facts from legacy helper mutation."""

    summary: str
    package_hash: str
    worker_attestation: str
    artifact_hash_manifest: list[dict]
    evidence_items: tuple[_EvidenceView, ...]


def detached_checker_context(request: PostSubmissionEvaluationRequest) -> CheckerContext:
    """Use copies for legacy pure helpers; no original immutable fact can be mutated."""
    request = PostSubmissionEvaluationRequest.model_validate(request)
    data = request.structural_input
    policy = data.policy_inputs
    return CheckerContext(
        task=_TaskView(data.criteria),
        submission=_SubmissionView(
            data.summary,
            data.package_hash,
            data.worker_attestation,
            [item.model_dump(mode="json") for item in data.manifest],
            tuple(_EvidenceView.from_facts(item) for item in data.evidence),
        ),
        required_checker_names=frozenset(
            entry.checker_id
            for entry in request.policy.entries
            if entry.classification != "project_warning"
        ),
        warning_checker_names=frozenset(
            entry.checker_id
            for entry in request.policy.entries
            if entry.classification == "project_warning"
        ),
        blocking_severities=frozenset(request.policy.blocking_severities),
        effective_policy={
            "required_artifacts": [
                {"path": value, "required": True} for value in policy.required_artifact_paths
            ],
            "required_evidence": [
                {"key": value, "required": True} for value in policy.required_evidence_keys
            ],
            "forbidden_artifacts": [
                {"pattern": value} for value in policy.forbidden_artifact_patterns
            ],
            "attestation_terms": list(policy.required_attestation_terms),
        },
        detached_input=data,
        expected_context=request.expected_context,
    )


async def check_modern_policy_context(context: CheckerContext) -> CheckerOutcome:
    """Check structural source-reference consistency, without asserting authorization."""
    if context.detached_input is None or context.expected_context is None:
        raise ValueError("modern checker requires detached context")
    observed = context.detached_input.observed_context
    expected = context.expected_context
    if any(getattr(observed, key) != value for key, value in expected.model_dump().items()):
        return _fail(
            "check_policy_context_present",
            "Submission policy context is incomplete or inconsistent.",
            "A project manager must correct the locked policy context.",
            worker_visible=False,
            routing_recommendation="task_setup_blocked",
        )
    return _pass("check_policy_context_present", "Submission has consistent policy context.")


def bounded_structural_result(
    definition: PostSubmitDefinition, outcome: CheckerOutcome
) -> PostSubmitMemberResult:
    """Discard legacy text/metadata and require the registered claim's closed outcome."""
    if outcome.checker_name != definition.capability_id:
        raise ValueError("post-submit handler returned another checker identity")
    passed = outcome.status == "passed"
    result = PostSubmitMemberResult(
        checker_id=definition.capability_id,
        implementation_version=definition.implementation_version,
        status=outcome.status,
        code="passed" if passed else definition.failure_code,
        failure_category="none" if passed else definition.failure_category,
        severity=outcome.severity,
    )
    if not passed and (result.status, result.severity) != (
        definition.failure_status,
        definition.failure_severity,
    ):
        raise ValueError("post-submit handler returned an unsupported outcome")
    return result


async def evaluate_registered_structural_member(
    registry: CheckerRegistry,
    definition: PostSubmitDefinition,
    request: PostSubmissionEvaluationRequest,
) -> PostSubmitMemberResult:
    """Private conformance seam; no product route or complete live phase executor."""
    selected = request.catalogue.definition(definition.capability_id, definition.capability_version)
    if selected != definition:
        raise ValueError("post-submit conformance definition mismatch")
    definition.validate_configuration({})
    registration = registry.resolve(definition.capability_id, definition.implementation_version)
    if registration.definition != definition:
        raise ValueError("post-submit installed definition mismatch")
    context = detached_checker_context(request)
    outcome = await registration.checker.run(context)
    return bounded_structural_result(definition, outcome)
