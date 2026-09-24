"""Closed manager PREP requests and independently validated audit storage shapes."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.audit.schemas import LifecycleAuditEventInput, LifecycleAuditEventType as Event
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid
from app.modules.tasks.api.transition_audit import TaskPolicyLineage
from tests.authorization.task_authority.test_audit_contract import event_fields
from tests.authorization.task_authority.test_prepared import setup, prepare


@pytest.mark.parametrize("field", [None, "resource_id", "scope_project_id", "request_digest"])
async def test_create_prepared_request_rejects_substitution(field):
    _, repo, prepared, resource, evidence = setup()
    repo.find_effective_grant = AsyncMock(return_value=repo.grant)
    resource = resource.model_copy(
        update={
            "task_status": "draft",
            "idempotency_key": uuid4(),
            "request_digest": "sha256:" + "b" * 64,
        }
    )
    try:
        handle, value = await prepare(prepared, resource, ActionId.PROJECT_TASK_CREATE)
        if field is None:
            result = await prepared.consume(handle, ActionId.PROJECT_TASK_CREATE, value, resource)
            assert result.allowed and len(evidence.events) == 1
        else:
            changed = resource.model_copy(
                update={field: "sha256:" + "c" * 64 if field == "request_digest" else uuid4()}
            )
            with pytest.raises(PreparedAuthorizationHandleInvalid):
                await prepared.consume(handle, ActionId.PROJECT_TASK_CREATE, value, changed)
            assert not evidence.events
    finally:
        prepared.close()


def lineage():
    return {
        name: 1
        if name.endswith("generation")
        else "sha256:" + "a" * 64
        if name.endswith("hash")
        else "v1"
        if name.endswith("version")
        else str(uuid4())
        for name in TaskPolicyLineage.model_fields
    }


def manager_event():
    fields = event_fields()
    fields.update(
        event_type=Event.TASK_SCREENED,
        from_status="draft",
        to_status="screening",
        locked_lineage=lineage(),
    )
    fields["references"].pop("assignment_id")
    return fields


@pytest.mark.parametrize("field", list(TaskPolicyLineage.model_fields))
def test_audit_requires_each_policy_lineage_field(field):
    fields = manager_event()
    assert LifecycleAuditEventInput(**fields).locked_lineage == fields["locked_lineage"]
    fields["locked_lineage"].pop(field)
    with pytest.raises(ValidationError, match="exact fields"):
        LifecycleAuditEventInput(**fields)


@pytest.mark.parametrize(
    "mutation", ["private", "uuid", "hash", "generation", "assignment", "source", "state"]
)
def test_manager_audit_rejects_invalid_storage_facts(mutation):
    fields = manager_event()
    if mutation == "private":
        fields["locked_lineage"]["private_material"] = "not audit evidence"
    elif mutation == "uuid":
        fields["locked_lineage"]["locked_review_policy_id"] = "invalid"
    elif mutation == "hash":
        fields["locked_lineage"]["locked_review_policy_hash"] = "invalid"
    elif mutation == "generation":
        fields["locked_lineage"]["locked_review_policy_generation"] = True
    elif mutation == "assignment":
        fields["references"]["assignment_id"] = uuid4()
    elif mutation == "source":
        fields["source_type"] = "manual"
    else:
        fields["from_status"] = None
    with pytest.raises(ValidationError):
        LifecycleAuditEventInput(**fields)


def test_missing_lineage_proof_detects_removed_storage_validation(monkeypatch):
    fields = manager_event()
    fields["locked_lineage"].pop("locked_review_policy_hash")

    def assert_missing_lineage_rejected():
        with pytest.raises(ValidationError, match="exact fields"):
            LifecycleAuditEventInput(**fields)

    assert_missing_lineage_rejected()
    monkeypatch.setattr("app.modules.audit.schemas._task_policy_lineage", lambda value: dict(value))
    with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
        assert_missing_lineage_rejected()


def test_manager_replay_discriminator_requires_the_complete_namespace():
    from app.modules.tasks.api.authorization import TaskAuthorityOperation
    from app.modules.tasks.command_replay import TaskCommandReplay
    from app.modules.tasks.models import TaskCommandReceipt

    actor, task, key, identity = uuid4(), uuid4(), uuid4(), uuid4()
    values = dict(
        id=identity,
        actor_profile_id=str(actor),
        task_id=str(task),
        action_id="project.task.screen",
        idempotency_key=key,
        status="committed",
    )

    def admitted(changes):
        return TaskCommandReplay.manager_replay(
            TaskCommandReceipt(**(values | changes)),
            TaskAuthorityOperation.SCREEN,
            task,
            actor,
            key,
        )

    assert admitted({}) == identity
    for changed in (
        {"actor_profile_id": str(uuid4())},
        {"task_id": str(uuid4())},
        {"idempotency_key": uuid4()},
        {"action_id": "project.task.release"},
        {"status": "pending"},
    ):
        assert admitted(changed) is None
