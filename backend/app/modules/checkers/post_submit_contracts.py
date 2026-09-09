"""Owner-local construction helpers for hash-bound post-submit facts."""

from __future__ import annotations

from pydantic import TypeAdapter

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.post_submit import (
    PostSubmissionEvaluationRequest,
    PostSubmissionEvaluationResult,
)


_REQUEST_FIELDS = {
    name: TypeAdapter(field.rebuild_annotation())
    for name, field in PostSubmissionEvaluationRequest.model_fields.items()
}
_RESULT_FIELDS = {
    name: TypeAdapter(field.rebuild_annotation())
    for name, field in PostSubmissionEvaluationResult.model_fields.items()
}


def make_post_submit_request(**fields: object) -> PostSubmissionEvaluationRequest:
    """Compute identity and then validate every field; this grants no authority."""
    if "request_sha256" in fields:
        raise ValueError("request identity is derived, not caller selected")
    fields = {
        name: _REQUEST_FIELDS[name].validate_python(value) if name in _REQUEST_FIELDS else value
        for name, value in fields.items()
    }
    candidate = PostSubmissionEvaluationRequest.model_construct(
        **fields, request_sha256="sha256:" + "0" * 64
    )
    body = candidate.model_dump(mode="json", exclude={"request_sha256"})
    fields["request_sha256"] = canonical_json_hash(body)
    return PostSubmissionEvaluationRequest.model_validate(fields)


def make_post_submit_result(**fields: object) -> PostSubmissionEvaluationResult:
    """Derive a result identity before validating its closed outcome shape."""
    if "result_digest" in fields:
        raise ValueError("result identity is derived, not caller selected")
    fields = {
        name: _RESULT_FIELDS[name].validate_python(value) if name in _RESULT_FIELDS else value
        for name, value in fields.items()
    }
    candidate = PostSubmissionEvaluationResult.model_construct(
        **fields, result_digest="sha256:" + "0" * 64
    )
    body = candidate.model_dump(mode="json", exclude={"result_digest"})
    fields["result_digest"] = canonical_json_hash(body)
    return PostSubmissionEvaluationResult.model_validate(fields)
