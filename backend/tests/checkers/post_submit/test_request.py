"""Identity consistency, complete valid denial control, and absence of owner authority."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.checkers.api import (
    PostSubmissionEvaluationRequest,
    PostSubmissionExecutionUnavailable,
    UnavailablePostSubmissionExecution,
)
from app.modules.checkers.post_submit_contracts import make_post_submit_request
from tests.checkers.post_submit.support import OTHER_HASH, change_request, request


@pytest.mark.parametrize(
    "change,message",
    [
        ("project", "project mismatch"),
        ("guide", "guide version mismatch"),
        ("policy_hash", "policy hash mismatch"),
        ("version", "guide and policy versions differ"),
        ("digest", "request digest mismatch"),
    ],
)
def test_request_digest_and_lineage(change, message):
    source = request()
    assert PostSubmissionEvaluationRequest.model_validate_json(source.model_dump_json()) == source
    fields = source.model_dump(exclude={"request_sha256"})
    if change == "project":
        fields["project_id"] = uuid4()
    elif change == "guide":
        fields["expected_context"].update(guide_version="other", post_policy_version="other")
    elif change == "policy_hash":
        fields["expected_context"]["post_policy_hash"] = OTHER_HASH
    elif change == "version":
        fields["expected_context"]["post_policy_version"] = "other"
    with pytest.raises(ValueError, match=message):
        if change == "digest":
            PostSubmissionEvaluationRequest(**fields, request_sha256=OTHER_HASH)
        else:
            make_post_submit_request(**fields)


def test_coherent_foreign_facts_are_not_an_authorization_proof():
    first = request()
    other = request(project_id=uuid4())
    assert first.project_id != other.project_id
    assert PostSubmissionEvaluationRequest.model_validate(other) == other
    assert first.request_sha256 != other.request_sha256
    assert not hasattr(other, "authorized")
    assert not hasattr(other, "is_current")


async def test_post_port_unavailable(monkeypatch):
    source = request()
    # A complete valid request reaches the precise unavailable guard.
    from app.modules.checkers import post_submit_implementations

    monkeypatch.setattr(
        post_submit_implementations,
        "evaluate_registered_structural_member",
        lambda *args: pytest.fail("unavailable phase executed a member"),
    )
    with pytest.raises(
        PostSubmissionExecutionUnavailable, match="^post_submit_execution_unavailable$"
    ):
        await UnavailablePostSubmissionExecution().evaluate_post_submission(source)


def test_fact_hashes_are_derived_and_nested_values_are_immutable():
    source = request()
    with pytest.raises(ValueError, match="derived"):
        make_post_submit_request(**source.model_dump())
    with pytest.raises(ValidationError, match="frozen"):
        source.structural_input.manifest[0].artifact = "changed"
    dumped = source.model_dump()
    dumped["structural_input"]["manifest"][0]["artifact"] = "changed"
    assert source.structural_input.manifest[0].artifact == "report.txt"
    with pytest.raises(ValidationError, match="digest mismatch"):
        PostSubmissionEvaluationRequest.model_validate(dumped)


@pytest.mark.parametrize("field", ("submission_version", "evaluation_generation", "byte_count"))
@pytest.mark.parametrize("invalid", (True, -1, "1"))
def test_strict_request_numbers(field, invalid):
    with pytest.raises(ValidationError):
        change_request(request(), **{field: invalid})


async def test_unavailable_port_revalidates_unsafe_constructed_instances():
    source = request()
    forged = source.model_copy(update={"project_id": uuid4()})
    with pytest.raises(ValidationError, match="project mismatch"):
        await UnavailablePostSubmissionExecution().evaluate_post_submission(forged)
