"""Contribution input protects exclusive source semantics without granting authority."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.contributions.records.schemas import ContributionRecordInput


@pytest.mark.parametrize("kind", ["completed_review", "accepted_submission"])
def test_contribution_input_shapes(kind):
    reviewer = kind == "completed_review"
    values = dict(
        id=uuid4(), project_id=uuid4(), task_id=uuid4(), submission_id=uuid4(),
        contributor_id=uuid4(), contribution_type=kind, artifact_hash="sha256:" + "a" * 64,
        contribution_policy_version_id=uuid4(),
        source_review_id=uuid4() if reviewer else None,
        source_review_lease_id=uuid4() if reviewer else None,
        source_final_acceptance_id=None if reviewer else uuid4(),
        source_task_assignment_id=None if reviewer else uuid4(),
    )
    record = ContributionRecordInput(**values)
    assert record.model_dump() == values
    with pytest.raises(ValidationError, match="frozen"):
        record.contributor_id = uuid4()
    for field in ("source_review_id", "source_review_lease_id", "source_final_acceptance_id", "source_task_assignment_id"):
        with pytest.raises(ValidationError, match="exclusive and complete"):
            ContributionRecordInput(**(values | {field: uuid4() if values[field] is None else None}))
    for delta in (
        {"project_id": str(values["project_id"])}, {"artifact_hash": "bad"},
        {"contribution_type": "checker_passed"}, {"authorized": True},
        {"created_at": "2026-01-01"},
    ):
        with pytest.raises(ValidationError):
            ContributionRecordInput(**(values | delta))
