"""Closed selected POST envelopes for the single execution owner."""

from __future__ import annotations

from typing import TypeAlias

from pydantic import TypeAdapter
from app.modules.checkers.api.selected_post_submit import (
    SelectedPostSubmissionEvaluationRequest,
    SelectedPostSubmissionEvaluationResult,
)


PostSubmissionExecutionRequest: TypeAlias = SelectedPostSubmissionEvaluationRequest
PostSubmissionExecutionResult: TypeAlias = SelectedPostSubmissionEvaluationResult

_REQUEST = TypeAdapter(PostSubmissionExecutionRequest)
_RESULT = TypeAdapter(PostSubmissionExecutionResult)


def validate_execution_request(value: object) -> PostSubmissionExecutionRequest:
    """Validate the only executable POST request schema."""
    return _REQUEST.validate_python(value)


def validate_stored_execution_request(value: str) -> PostSubmissionExecutionRequest:
    """Decode selected canonical JSON using the strict model boundary."""
    return _REQUEST.validate_json(value)


def validate_execution_result(value: object) -> PostSubmissionExecutionResult:
    """Validate the only executable POST result schema."""
    return _RESULT.validate_python(value)


def validate_stored_execution_result(value: str) -> PostSubmissionExecutionResult:
    """Decode selected canonical result JSON through the strict model boundary."""
    return _RESULT.validate_json(value)


def coverage_gap_without_failure(result: PostSubmissionExecutionResult) -> bool:
    """A completed result whose checks could not evaluate part of the work, with no failure.

    Such a return is evidence about the checker, not the contributor: it never
    auto-accepts, spends no revision round and never exhausts an assignment.
    """
    members = result.execution.external_members if result.execution else ()
    return not any(member.result.verdict == "failed" for member in members) and any(
        finding.level == "coverage_incomplete"
        for member in members
        for finding in member.result.findings
    )


__all__ = (
    "coverage_gap_without_failure",
    "PostSubmissionExecutionRequest",
    "PostSubmissionExecutionResult",
    "validate_execution_request",
    "validate_stored_execution_request",
    "validate_stored_execution_result",
    "validate_execution_result",
)
