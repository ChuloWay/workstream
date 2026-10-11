"""Compact batch contracts reject partial and substituted ordered success facts."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.tasks.api.task_batch_transition import TaskBatchTransitionRequest, TaskBatchTransitionResponse
from app.modules.tasks.service import TaskValidationError
from app.modules.tasks.task_batch_transitions import TaskBatchTransitionCommands


def response_value(count=2):
    """Use different Task identities with the same legitimate locked guide version."""
    return {"project_id": str(uuid4()), "batch_id": str(uuid4()), "operation": "screen", "row_count": count,
            "tasks": [{"task_id": str(uuid4()), "row_index": index, "status": "screening",
                       "locked_guide_version": "v1.0.0", "locked_contribution_policy_version_id": str(uuid4()),
                       "locked_context_hash": "sha256:" + "a" * 64} for index in range(count)]}


def test_response_preserves_complete_500_row_order_and_string_guide_versions():
    value = response_value(500)
    response = TaskBatchTransitionResponse.model_validate(value)
    assert response.model_dump(mode="json") == value
    assert TaskBatchTransitionResponse.model_validate_json(response.model_dump_json()) == response


@pytest.mark.parametrize("change", ["missing", "reordered", "duplicate", "foreign_status", "bad_hash", "unlocked", "extra"])
def test_incomplete_or_substituted_success_is_refused(change):
    value = response_value()
    if change == "missing":
        value["tasks"].pop()
    elif change == "reordered":
        value["tasks"].reverse()
    elif change == "duplicate":
        value["tasks"][1]["task_id"] = value["tasks"][0]["task_id"]
    elif change == "foreign_status":
        value["tasks"][1]["status"] = "ready"
    elif change == "bad_hash":
        value["tasks"][1]["locked_context_hash"] = "unverified"
    elif change == "unlocked":
        value["tasks"][1]["locked_guide_version"] = None
    else:
        value["tasks"][1]["instructions"] = "private DTO"
    with pytest.raises(ValidationError):
        TaskBatchTransitionResponse.model_validate(value)


@pytest.mark.parametrize("count", [0, 501])
def test_public_row_bounds_are_explicit(count):
    with pytest.raises(ValidationError):
        TaskBatchTransitionResponse.model_validate(response_value(count))


def test_release_and_reason_contracts_are_separate_from_screen():
    value = response_value()
    value["operation"] = "release"
    for task in value["tasks"]:
        task["status"] = "ready"
    assert TaskBatchTransitionResponse.model_validate(value).operation == "release"
    assert TaskBatchTransitionRequest(reason="Decision\nwith Unicode café").reason.endswith("café")
    with pytest.raises(ValidationError):
        TaskBatchTransitionRequest(reason="x" * 4001)
    with pytest.raises(ValidationError):
        TaskBatchTransitionRequest.model_validate({"task_ids": [str(uuid4())]})


@pytest.mark.parametrize("reason", [None, "", " \n"])
async def test_release_reason_is_refused_before_any_transaction_or_authority(reason):
    """Admission must reject incomplete input without accessing a session or Task port."""
    owner = TaskBatchTransitionCommands(None, actor_profile_id=uuid4(), identity_link_id=uuid4(), tasks=None)
    with pytest.raises(TaskValidationError, match="release decision reason is required"):
        await owner.release(uuid4(), uuid4(), reason, idempotency_key=uuid4())
