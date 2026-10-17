"""The verified wrapper binds its bounded result without asserting caller authority."""

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import EvaluationCompletion, VerifiedEvaluationCompletion, VerifiedMaterialFacts
from app.modules.checkers.api.selected_post_submit import SelectedPostSubmitCurrentResultReference
from tests.checkers.execution.support import selected_request, selected_result


def test_verified_completion_rejects_mismatched_result():
    source = selected_request()
    completed = selected_result(source)
    reference = SelectedPostSubmitCurrentResultReference(**completed.model_dump(
        include=set(SelectedPostSubmitCurrentResultReference.model_fields) - {"schema_version"},
    ))
    fields = dict(
        completion=EvaluationCompletion(
            project_id=source.project_id, task_id=source.task_id, submission_id=source.submission_id,
            reference=reference, routing_recommendation="allow_review", output_binding_ids=(),
            execute_evidence_id=new_record_id(), finalize_evidence_id=new_record_id(),
        ),
        result=completed, submission_version=source.submission_version,
        material=VerifiedMaterialFacts(
            submission_id=source.submission_id, submission_version=source.submission_version,
            admission_id=new_record_id(), binding_id=source.binding_id, content_id=source.content_id,
            replica_id=new_record_id(), content_sha256=source.content_sha256,
            byte_count=source.byte_count, semantic_manifest_sha256=source.content_sha256,
        ),
        input_materialization_evidence_id=new_record_id(),
    )
    value = VerifiedEvaluationCompletion(**fields)
    assert VerifiedEvaluationCompletion.model_validate_json(value.model_dump_json()) == value
    other = selected_result(source)
    assert other.result_digest != completed.result_digest
    infrastructure = selected_result(source, outcome="infrastructure_failed", execution=None,
                            infrastructure_failure_code="material_unavailable")
    for invalid in (other, infrastructure):
        with pytest.raises(ValidationError, match="current reference result mismatch"):
            VerifiedEvaluationCompletion(**(fields | {"result": invalid}))
