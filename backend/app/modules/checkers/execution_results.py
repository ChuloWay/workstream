"""One complete member classification and closed history presentation."""

from dataclasses import dataclass

from app.modules.checkers.api.evaluation_contract import (
    PostSubmissionExecutionRequest,
    PostSubmissionExecutionResult,
)


@dataclass(frozen=True, slots=True)
class ResultClassification:
    """Closed routing recommendation and counts derived from the complete locked policy."""

    routing: str
    passed: int
    warning: int
    failed: int
    blocking: int


def classify_result(
    request: PostSubmissionExecutionRequest, result: PostSubmissionExecutionResult
) -> ResultClassification:
    """Validate every selected member before deriving policy-governed routing."""
    result.validate_request(request)
    if result.outcome == "infrastructure_failed":
        return ResultClassification("not_evaluated", 0, 0, 0, 0)
    members = result.execution.external_members if result.execution else ()
    failed = sum(member.result.verdict == "failed" for member in members)
    return ResultClassification(
        "needs_revision" if failed else "allow_review",
        sum(member.result.verdict == "passed" for member in members),
        0,
        failed,
        failed,
    )


RESULT_MESSAGES = {
    "passed": ("Check passed.", None),
    "packet_fields_missing": (
        "Required submission fields are missing.",
        "Complete the required submission fields.",
    ),
    "policy_context_invalid": ("The locked policy context is inconsistent.", None),
    "evidence_missing": ("Required evidence is missing.", "Include the required evidence."),
    "evidence_structure_invalid": (
        "Evidence references are invalid.",
        "Correct the evidence references.",
    ),
    "required_files_missing": ("Required files are missing.", "Include the required files."),
    "forbidden_path_present": (
        "The submission includes a forbidden path.",
        "Remove the forbidden content.",
    ),
    "attestation_missing": (
        "Required attestation is missing.",
        "Complete the required attestation.",
    ),
    "placeholder_signal": (
        "A possible placeholder needs attention.",
        "Check the flagged submission structure.",
    ),
    "acceptance_criteria_missing": ("Task acceptance criteria are missing.", None),
}
