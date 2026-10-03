"""Pure contract proof for detached routing source and accepted TASK effects."""

from inspect import isclass, iscoroutinefunction

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.catalogue import (ActionId, PermissionId, ActionAvailability, ACTION_BY_ID, SERVICE_ACTIONS_BY_IDENTITY, resolve_executable_action)
from app.modules.tasks import api as task_api
from app.modules.tasks.api import accepted_effects, post_submit_routing
from app.modules.tasks.api.accepted_effects import (
    TaskAcceptedEffectsPort,
    TaskAcceptedEffectsRequest,
    TaskAcceptedEffectsResult,
    TaskAcceptedEffectsUnavailable,
)
from app.modules.tasks.api.post_submit_routing import TaskPostSubmitManifestFacts
from tests.tasks.post_submit_routing.contract_fixtures import SHA_A, _lineage, _source_values

def _effects_values(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "project_id": new_record_id(),
        "task_id": new_record_id(),
        "assignment_id": new_record_id(),
        "submission_id": new_record_id(),
        "submission_version": 1,
        "contributor_id": new_record_id(),
        "contribution_policy_version_id": new_record_id(),
        "content_id": new_record_id(),
        "content_sha256": SHA_A,
        "final_acceptance_id": new_record_id(),
        "expected_task_status": "evaluation_pending",
    }
    values.update(changes)
    return values


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("id", str(new_record_id())),
        ("created_at", "2026-01-02T00:00:00Z"),
        ("submission_version", "1"),
        ("evaluation_generation", True),
        ("request_digest", "a" * 64),
        ("human_review_required", 1),
        ("byte_count", False),
        ("routing_recommendation", "needs_revision"),
    ),
)
def test_source_contract_is_strict_and_detached(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        TaskPostSubmitManifestFacts(**_source_values(**{field: value}))

    valid = _source_values()
    valid["private_provider_key"] = "must-not-cross-owner-boundary"
    with pytest.raises(ValidationError):
        TaskPostSubmitManifestFacts(**valid)


def test_source_contract_is_an_exact_frozen_value() -> None:
    source = TaskPostSubmitManifestFacts(**_source_values())

    with pytest.raises(ValidationError):
        source.human_review_required = False

    assert set(TaskPostSubmitManifestFacts.model_fields) == {
        "id",
        "created_at",
        "project_id",
        "task_id",
        "submission_id",
        "submission_version",
        "assignment_id",
        "contributor_id",
        "contribution_policy_version_id",
        "checker_run_id",
        "evaluation_request_id",
        "request_digest",
        "evaluation_generation",
        "result_id",
        "result_digest",
        "completion_event_id",
        "execute_evidence_id",
        "finalize_evidence_id",
        "human_review_required",
        "replica_id",
        "content_sha256",
        "byte_count",
        "semantic_manifest_sha256",
        "predecessor_submission_id",
        "predecessor_submission_version",
        "admission_id",
        "binding_id",
        "content_id",
        "locked_policy",
        "routing_recommendation",
    }


def test_source_rejects_nested_lineage_mismatch() -> None:
    with pytest.raises(ValidationError, match="contribution policy lineage differs"):
        TaskPostSubmitManifestFacts(
            **_source_values(locked_policy=_lineage(contribution_policy_version_id=new_record_id()))
        )


@pytest.mark.parametrize("successor", (False, True))
def test_source_rejects_equal_phase_receipts(successor: bool) -> None:
    receipt_id = new_record_id()
    changes: dict[str, object] = {
        "execute_evidence_id": receipt_id,
        "finalize_evidence_id": receipt_id,
    }
    if successor:
        changes.update(
            submission_version=2,
            predecessor_submission_id=new_record_id(),
            predecessor_submission_version=1,
        )

    with pytest.raises(ValidationError, match="phase receipts are not distinct"):
        TaskPostSubmitManifestFacts(**_source_values(**changes))


@pytest.mark.parametrize(
    "changes",
    (
        {"predecessor_submission_id": new_record_id()},
        {"predecessor_submission_version": 1},
        {
            "submission_version": 1,
            "predecessor_submission_id": new_record_id(),
            "predecessor_submission_version": 1,
        },
        {"submission_version": 2},
        {
            "submission_version": 3,
            "predecessor_submission_id": new_record_id(),
            "predecessor_submission_version": 1,
        },
    ),
)
def test_source_rejects_inconsistent_predecessor_shape(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="predecessor"):
        TaskPostSubmitManifestFacts(**_source_values(**changes))


def test_source_accepts_exact_immediate_predecessor() -> None:
    predecessor_id = new_record_id()
    source = TaskPostSubmitManifestFacts(
        **_source_values(
            submission_version=2,
            predecessor_submission_id=predecessor_id,
            predecessor_submission_version=1,
        )
    )

    assert source.predecessor_submission_id == predecessor_id
    assert source.predecessor_submission_version == source.submission_version - 1


def test_source_rejects_its_own_submission_as_predecessor() -> None:
    submission_id = new_record_id()
    with pytest.raises(ValidationError, match="predecessor equals submission"):
        TaskPostSubmitManifestFacts(
            **_source_values(
                submission_id=submission_id,
                submission_version=2,
                predecessor_submission_id=submission_id,
                predecessor_submission_version=1,
            )
        )


def test_false_source_value_is_transport_only() -> None:
    source = TaskPostSubmitManifestFacts(**_source_values(human_review_required=False))

    assert source.human_review_required is False
    assert source.model_dump(mode="json")["human_review_required"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("project_id", str(new_record_id())),
        ("submission_version", "1"),
        ("submission_version", True),
        ("content_sha256", "sha256:" + "A" * 64),
        ("expected_task_status", "accepted"),
        ("routing_manifest_id", new_record_id()),
    ),
)
def test_accepted_effects_request_is_strict(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        TaskAcceptedEffectsRequest(**_effects_values(**{field: value}))


def test_accepted_effects_contract_is_source_neutral() -> None:
    request = TaskAcceptedEffectsRequest(**_effects_values())
    review_request = TaskAcceptedEffectsRequest(
        **_effects_values(expected_task_status="review_pending")
    )
    result = TaskAcceptedEffectsResult(
        request=request,
        task_status="accepted",
        assignment_status="completed",
    )

    assert result.request == request
    assert review_request.expected_task_status == "review_pending"
    assert set(TaskAcceptedEffectsRequest.model_fields) == set(_effects_values())
    assert set(TaskAcceptedEffectsResult.model_fields) == {
        "request",
        "task_status",
        "assignment_status",
    }
    assert iscoroutinefunction(TaskAcceptedEffectsPort.apply_accepted_effects)
    assert issubclass(TaskAcceptedEffectsUnavailable, RuntimeError)
    with pytest.raises(ValidationError):
        request.expected_task_status = "accepted"
    with pytest.raises(ValidationError):
        result.task_status = "review_pending"
    for changes in (
        {"task_status": "review_pending"},
        {"assignment_status": "accepted"},
        {"review_id": new_record_id()},
    ):
        values = {
            "request": request,
            "task_status": "accepted",
            "assignment_status": "completed",
        }
        values.update(changes)
        with pytest.raises(ValidationError):
            TaskAcceptedEffectsResult(**values)


def test_source_foundation_has_no_runtime_entry() -> None:
    assert post_submit_routing.__all__ == ("TaskPostSubmitManifestFacts", "task_post_submit_source_digest")
    assert accepted_effects.__all__ == (
        "TaskAcceptedEffectsPort",
        "TaskAcceptedEffectsRequest",
        "TaskAcceptedEffectsResult",
        "TaskAcceptedEffectsUnavailable",
    )
    for name in post_submit_routing.__all__ + accepted_effects.__all__:
        assert getattr(task_api, name) is getattr(
            post_submit_routing if name in post_submit_routing.__all__ else accepted_effects,
            name,
        )

    assert {
        name
        for name, value in vars(post_submit_routing).items()
        if isclass(value) and value.__module__ == post_submit_routing.__name__
    } == {"TaskPostSubmitManifestFacts"}
    assert {
        name
        for name, value in vars(accepted_effects).items()
        if isclass(value) and value.__module__ == accepted_effects.__name__
    } == {
        "TaskAcceptedEffectsPort",
        "TaskAcceptedEffectsRequest",
        "TaskAcceptedEffectsResult",
        "TaskAcceptedEffectsUnavailable",
    }
    action = ActionId.TASK_POST_SUBMIT_ROUTE
    assert ACTION_BY_ID[action].permission_id is PermissionId.TASK_POST_SUBMIT_ROUTE
    assert ACTION_BY_ID[action].availability is ActionAvailability.PLANNED
    assert SERVICE_ACTIONS_BY_IDENTITY[ServiceIdentity.TASK_POST_SUBMIT_ROUTER] == {action}
    with pytest.raises(ValueError, match="authorization action is not active"):
        resolve_executable_action(action)
