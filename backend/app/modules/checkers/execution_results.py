"""One complete member classification and closed history presentation."""

from dataclasses import dataclass

from app.modules.checkers.api.evaluation_contract import (
    PostSubmissionExecutionRequest,
    PostSubmissionExecutionResult,
    coverage_gap_without_failure,
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
    request: PostSubmissionExecutionRequest, result: PostSubmissionExecutionResult,
    *, human_review_required: bool,
) -> ResultClassification:
    """Validate every selected member before deriving policy-governed routing.

    A coverage gap (``coverage_incomplete`` without errors) never auto-accepts:
    with human review it goes to a reviewer, otherwise it returns to the
    contributor. TASK records that return without spending a revision round.
    """
    result.validate_request(request)
    if result.outcome == "infrastructure_failed":
        return ResultClassification("not_evaluated", 0, 0, 0, 0)
    members = result.execution.external_members if result.execution else ()
    failed = sum(member.result.verdict == "failed" for member in members)
    returned = failed or (coverage_gap_without_failure(result) and not human_review_required)
    return ResultClassification(
        "needs_revision" if returned else "allow_review",
        sum(member.result.verdict == "passed" for member in members),
        0,
        failed,
        failed,
    )


RESULT_STATUS_MESSAGES = {
    "passed": ("Check passed.", None),
    "warning": ("Check reported a warning.", "Review the project guide and check findings."),
    "failed": ("Project check failed.", "Review the project guide and check findings."),
    "coverage_incomplete": (
        "Check could not evaluate part of the submission.",
        "Make the listed files readable by the project checks, then resubmit.",
    ),
}
