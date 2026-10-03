"""Closed routing request selectors and independent operation identity."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.tasks.api.post_submit_routing import (
    TaskRoutingSelection, TaskRoutingRequestFacts, task_routing_request_digest,
)


def selection():
    return TaskRoutingSelection(
        **{key: new_record_id() for key in (
            "project_id", "task_id", "submission_id", "checker_run_id",
            "evaluation_request_id", "result_id", "completion_event_id",
        )}, submission_version=1, evaluation_generation=1,
        evaluation_request_digest="sha256:" + "a" * 64,
        result_digest="sha256:" + "b" * 64, routing_recommendation="allow_review",
    )


def test_request_identity_is_not_part_of_semantic_digest():
    selected = selection()
    facts = TaskRoutingRequestFacts(
        **selected.model_dump(), route_operation_id=new_record_id(),
        routing_manifest_id=new_record_id(), created_at=datetime.now(UTC),
        route_request_digest=task_routing_request_digest(selected),
    )
    changed = facts.model_dump() | {"route_operation_id": new_record_id(), "routing_manifest_id": new_record_id()}
    assert TaskRoutingRequestFacts(**changed).route_request_digest == facts.route_request_digest
    with pytest.raises(ValidationError, match="digest differs"):
        TaskRoutingRequestFacts(**(changed | {"task_id": new_record_id()}))
    with pytest.raises(ValueError, match="selection is invalid"):
        task_routing_request_digest(facts)


@pytest.mark.parametrize("field", ["route_operation_id", "routing_manifest_id"])
@pytest.mark.parametrize("other", ["route_operation_id", "routing_manifest_id", "evaluation_request_id", "result_id", "completion_event_id"])
def test_request_ids_are_distinct_uuid7(field, other):
    selected = selection()
    values = dict(selected.model_dump(), route_operation_id=new_record_id(),
                  routing_manifest_id=new_record_id(), created_at=datetime.now(UTC),
                  route_request_digest=task_routing_request_digest(selected))
    if field == other:
        from uuid import UUID
        values[field] = UUID("00000000-0000-4000-8000-000000000001")
    else:
        values[field] = values[other]
    with pytest.raises(ValidationError, match="identit"):
        TaskRoutingRequestFacts(**values)


@pytest.mark.parametrize("field", list(TaskRoutingSelection.model_fields))
def test_each_selector_is_bound(field):
    selected = selection()
    value = getattr(selected, field)
    if field == "routing_recommendation":
        with pytest.raises(ValidationError):
            TaskRoutingSelection(**(selected.model_dump() | {field: "needs_revision"}))
        return
    changed = (value + 1 if isinstance(value, int) else
               "sha256:" + "c" * 64 if isinstance(value, str) else new_record_id())
    alternate = TaskRoutingSelection(**(selected.model_dump() | {field: changed}))
    assert task_routing_request_digest(alternate) != task_routing_request_digest(selected)


def test_request_registration_does_not_authorize_adjacent_runtime():
    import json
    from scripts import behavior_ownership as ownership

    target = "backend/app/modules/tasks/post_submit_routing/requests.py"
    assert ownership.ARCH_04E1BA_REQUEST_TARGETS == {target}
    current = json.loads((ownership.ROOT / ownership.PARTITION_PATH).read_text())
    trusted = dict(current, assignments=[row for row in current["assignments"] if row["target"] != target])
    trusted["authority_digest"] = ownership._digest({key: value for key, value in trusted.items() if key != "authority_digest"})
    ownership._validate_additive_partition_transition(current, trusted)
    extra = dict(current, assignments=current["assignments"] + [{
        "group": "lifecycle", "target": "backend/app/modules/tasks/post_submit_routing/live_router.py",
    }])
    with pytest.raises(ownership.BehaviorOwnershipError, match="untrusted_partition_change"):
        ownership._validate_additive_partition_transition(extra, trusted)
