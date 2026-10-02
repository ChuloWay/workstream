"""Closed Review values and request identity independent of generated IDs."""

from typing import get_args

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.authorization.review_contracts import ReviewDecisionValue
from app.modules.reviews.decision.schemas import (
    FindingResolutionInput,
    ReviewDecision,
    ReviewSourceInput,
)
from tests.reviews.decision.support import finding


def source_input():
    return ReviewSourceInput(
        **{
            name: new_record_id()
            for name in (
                "id",
                "project_id",
                "task_id",
                "task_assignment_id",
                "submission_id",
                "review_queue_entry_id",
                "review_lease_id",
                "packet_manifest_id",
                "reviewer_id",
                "reviewer_contribution_policy_version_id",
                "locked_review_policy_id",
            )
        },
        submission_version=1,
        packet_manifest_digest="sha256:" + "a" * 64,
        artifact_hash="sha256:" + "b" * 64,
        locked_guide_version="guide-1",
        locked_review_policy_generation=1,
        locked_review_policy_hash="sha256:" + "c" * 64,
        predecessor_review_id=None,
        decision="needs_revision",
        summary="Requires a repair.",
        findings=(finding(),),
        resolutions=(
            FindingResolutionInput(
                id=new_record_id(),
                finding_id=new_record_id(),
                result="unresolved",
                rationale="The requested result still differs from the specification.",
            ),
        ),
    )


def test_decision_values_match_authorization_contract():
    assert set(get_args(ReviewDecision)) == {v.value for v in ReviewDecisionValue}


def test_generated_ids_do_not_change_request_identity():
    original = source_input()
    duplicate = original.model_copy(
        update={
            "id": new_record_id(),
            "findings": tuple(
                f.model_copy(update={"id": new_record_id()}) for f in original.findings
            ),
            "resolutions": tuple(
                r.model_copy(update={"id": new_record_id()}) for r in original.resolutions
            ),
        }
    )
    assert original.request_digest == duplicate.request_digest
    assert original.aggregate_digest != duplicate.aggregate_digest
    assert original.semantic_payload(request=True)["action"] == "review.decision"


@pytest.mark.parametrize(
    "field,value",
    [
        ("project_id", new_record_id()),
        ("task_id", new_record_id()),
        ("reviewer_id", new_record_id()),
        ("submission_version", 2),
        ("predecessor_review_id", new_record_id()),
        ("summary", "A different judgment."),
        ("decision", "reject"),
        ("artifact_hash", "sha256:" + "d" * 64),
        ("packet_manifest_digest", "sha256:" + "e" * 64),
    ],
)
def test_source_substitution_changes_both_digests(field, value):
    original = source_input()
    altered = original.model_copy(update={field: value})
    assert altered.request_digest != original.request_digest
    assert altered.aggregate_digest != original.aggregate_digest


@pytest.mark.parametrize(
    "collection,field,value",
    [
        ("findings", "area", "Other area"),
        ("findings", "issue", "A different issue"),
        ("findings", "finding_kind", "advisory"),
        ("findings", "required_fix", "Another fix"),
        ("resolutions", "finding_id", new_record_id()),
        ("resolutions", "result", "resolved"),
        ("resolutions", "rationale", "A different rationale"),
    ],
)
def test_nested_substitution_changes_both_digests(collection, field, value):
    original = source_input()
    altered = original.model_copy(
        update={collection: (getattr(original, collection)[0].model_copy(update={field: value}),)}
    )
    assert altered.request_digest != original.request_digest
    assert altered.aggregate_digest != original.aggregate_digest


@pytest.mark.parametrize(
    "field,value",
    [
        ("summary", " \n\t"),
        ("summary", "x" * 4001),
        ("decision", "approved"),
        ("project_id", "not-a-native-UUID"),
        ("submission_version", True),
        ("submission_version", 0),
        ("packet_manifest_digest", "not-a-hash"),
        ("acceptance_evidence_refs", []),
        ("confidence", 0.9),
    ],
)
def test_closed_bounded_source_contract(field, value):
    values = source_input().model_dump()
    values[field] = value
    with pytest.raises(ValidationError):
        ReviewSourceInput.model_validate(values)


def test_member_bounds_and_duplicate_identity():
    source = source_input()
    for members in ((source.findings[0],) * 2, tuple(finding() for _ in range(101))):
        with pytest.raises(ValidationError):
            ReviewSourceInput.model_validate({**source.model_dump(), "findings": members})


def test_generated_id_regression_detects_unstable_request_digest(monkeypatch):
    original = ReviewSourceInput.semantic_payload

    def broken_payload(self, *, request=False):
        payload = original(self, request=request)
        if request:
            payload["id"] = str(self.id)
        return payload

    monkeypatch.setattr(ReviewSourceInput, "semantic_payload", broken_payload)
    with pytest.raises(AssertionError):
        test_generated_ids_do_not_change_request_identity()
