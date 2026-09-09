"""Phase/result reference identity and closed failure semantics without persistence."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.checkers.api import (
    PostSubmissionEvaluationResult,
    PostSubmitCurrentResultReference,
    PostSubmitMemberResult,
)
from app.modules.checkers.api.post_submit import PostSubmitCounter
from app.modules.checkers.post_submit_contracts import make_post_submit_result
from tests.checkers.post_submit.support import OTHER_HASH, request


def result(source, **changes):
    fields = dict(
        request_id=source.evaluation_request_id,
        request_digest=source.request_sha256,
        attempt_id=uuid4(),
        evaluation_generation=source.evaluation_generation,
        result_id=uuid4(),
        outcome="completed",
        member_results=tuple(
            PostSubmitMemberResult(
                checker_id=item.checker_id,
                definition_version=item.definition_version,
                implementation_version=item.implementation_version,
                status="passed",
                code="passed",
                failure_category="none",
                severity="info",
            )
            for item in source.policy.entries
        ),
    )
    fields.update(changes)
    return make_post_submit_result(**fields)


def test_result_is_not_currentness_or_acceptance():
    source = request()
    completed = result(source)
    completed.validate_request(source)
    fields = {
        name: getattr(completed, name)
        for name in PostSubmitCurrentResultReference.model_fields
        if name != "schema_version"
    }
    reference = PostSubmitCurrentResultReference(**fields)
    reference.validate_result(completed)
    assert not hasattr(reference, "is_current")
    assert not hasattr(completed, "accept")
    assert (
        PostSubmissionEvaluationResult.model_validate_json(completed.model_dump_json()) == completed
    )


@pytest.mark.parametrize("field", ("request_id", "request_digest", "evaluation_generation"))
def test_result_rejects_crossed_request(field):
    source = request()
    value = (
        OTHER_HASH if field.endswith("digest") else 2 if field.endswith("generation") else uuid4()
    )
    with pytest.raises(ValueError, match="request mismatch"):
        result(source, **{field: value}).validate_request(source)


@pytest.mark.parametrize("damage", ("omit", "reorder", "version", "claim"))
def test_completed_member_list_matches_plan_exactly(damage):
    source = request()
    members = list(result(source).member_results)
    if damage == "omit":
        members.pop()
    elif damage == "reorder":
        members.reverse()
    elif damage == "version":
        members[0] = members[0].model_copy(update={"implementation_version": "other"})
    else:
        members[0] = PostSubmitMemberResult(
            **{
                **members[0].model_dump(),
                "status": "failed",
                "code": "evidence_missing",
                "failure_category": "submission_structure",
                "severity": "high",
            }
        )
    with pytest.raises(ValueError, match="members mismatch|registered claim"):
        result(source, member_results=tuple(members)).validate_request(source)


@pytest.mark.parametrize(
    "code",
    ("capacity_exceeded", "deadline_exceeded", "implementation_unavailable", "invalid_output"),
)
def test_infrastructure_failure_never_carries_work_failure(code):
    source = request()
    failed = result(
        source, outcome="infrastructure_failed", member_results=(), infrastructure_failure_code=code
    )
    failed.validate_request(source)
    assert failed.member_results == ()
    fields = {
        key: getattr(failed, key)
        for key in PostSubmitCurrentResultReference.model_fields
        if key != "schema_version"
    }
    with pytest.raises(ValueError, match="current reference result mismatch"):
        PostSubmitCurrentResultReference(**fields).validate_result(failed)


@pytest.mark.parametrize(
    "changes",
    [
        {"member_results": ()},
        {"infrastructure_failure_code": "deadline_exceeded"},
        {"outcome": "infrastructure_failed"},
        {"outcome": "accept"},
        {"outcome": "infrastructure_failed", "member_results": ()},
    ],
)
def test_phase_shapes_reject_conflicting_or_empty_outcomes(changes):
    with pytest.raises(ValueError):
        result(request(), **changes)


def test_result_digest_and_reference_require_exact_identity():
    source = request()
    complete = result(source)
    body = complete.model_dump()
    body["result_digest"] = OTHER_HASH
    with pytest.raises(ValueError, match="result digest mismatch"):
        PostSubmissionEvaluationResult.model_validate(body)
    with pytest.raises(ValueError, match="derived"):
        make_post_submit_result(**complete.model_dump())
    fields = {
        key: getattr(complete, key)
        for key in PostSubmitCurrentResultReference.model_fields
        if key != "schema_version"
    }
    fields["attempt_id"] = uuid4()
    with pytest.raises(ValueError, match="current reference result mismatch"):
        PostSubmitCurrentResultReference(**fields).validate_result(complete)


@pytest.mark.parametrize(
    "changes",
    [
        {"severity": "high"},
        {"code": "packet_fields_missing"},
        {"failure_category": "task_configuration"},
        {"status": "failed"},
        {"message": "private/path"},
        {"counters": ({"key": "artifact_count", "value": True},)},
        {"counters": ({"key": "raw_path", "value": 1},)},
        {"counters": ({"key": "artifact_count", "value": 1},) * 2},
    ],
)
def test_member_result_shape_is_closed(changes):
    passing = result(request()).member_results[0]
    with pytest.raises(ValidationError):
        PostSubmitMemberResult(**{**passing.model_dump(), **changes})


def test_registered_failure_and_result_counter_boundaries():
    source = request()
    definition = source.catalogue.definitions[0]
    member = PostSubmitMemberResult(
        checker_id=definition.capability_id,
        implementation_version=definition.implementation_version,
        status="failed",
        code="packet_fields_missing",
        failure_category="submission_structure",
        severity="high",
        counters=(PostSubmitCounter(key="missing_count", value=1024),),
    )
    member.validate_catalogue(source.catalogue)
    assert PostSubmitCounter(key="missing_count", value=0).value == 0
    with pytest.raises(ValidationError):
        PostSubmitCounter(key="missing_count", value=1025)
    with pytest.raises(ValueError, match="implementation mismatch"):
        member.model_copy(update={"implementation_version": "other"}).validate_catalogue(
            source.catalogue
        )


def test_consumers_revalidate_unchecked_copies():
    source = request()
    complete = result(source)
    forged = complete.model_copy(update={"result_digest": OTHER_HASH})
    with pytest.raises(ValidationError, match="result digest mismatch"):
        forged.validate_request(source)
    forged_member = complete.member_results[0].model_copy(update={"severity": "high"})
    with pytest.raises(ValidationError, match="passing result shape"):
        forged_member.validate_catalogue(source.catalogue)
