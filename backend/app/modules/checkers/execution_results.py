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


RESULT_STATUS_MESSAGES = {
    "passed": ("Check passed.", None),
    "warning": ("Check reported a warning.", "Review the project guide and check findings."),
    "failed": ("Project check failed.", "Review the project guide and check findings."),
}
