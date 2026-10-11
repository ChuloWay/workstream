"""Closed active and retained POST envelopes for the single execution owner."""

from __future__ import annotations

from typing import Annotated, TypeAlias

from pydantic import Field, TypeAdapter

from app.modules.checkers.api.post_submit import (
    PostSubmissionEvaluationRequest,
    PostSubmissionEvaluationResult,
)
from app.modules.checkers.api.selected_post_submit import (
    SelectedPostSubmissionEvaluationRequest,
    SelectedPostSubmissionEvaluationResult,
)


PostSubmissionExecutionRequest: TypeAlias = Annotated[
    PostSubmissionEvaluationRequest | SelectedPostSubmissionEvaluationRequest,
    Field(discriminator="schema_version"),
]
PostSubmissionExecutionResult: TypeAlias = Annotated[
    PostSubmissionEvaluationResult | SelectedPostSubmissionEvaluationResult,
    Field(discriminator="schema_version"),
]

_REQUEST = TypeAdapter(PostSubmissionExecutionRequest)
_RESULT = TypeAdapter(PostSubmissionExecutionResult)


def validate_execution_request(value: object) -> PostSubmissionExecutionRequest:
    """Validate the selected writer or a retained legacy request by schema."""
    return _REQUEST.validate_python(value)


def validate_execution_result(value: object) -> PostSubmissionExecutionResult:
    """Validate the selected writer or a retained legacy result by schema."""
    return _RESULT.validate_python(value)


__all__ = (
    "PostSubmissionExecutionRequest",
    "PostSubmissionExecutionResult",
    "validate_execution_request",
    "validate_execution_result",
)
