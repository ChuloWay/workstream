"""Closed manager PREP requests and independently validated audit storage shapes."""

import json

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.audit.schemas import LifecycleAuditEventInput, LifecycleAuditEventType as Event
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.task_authority import task_resource_guard
from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid
from app.modules.tasks.api.transition_audit import TaskPolicyLineage
from tests.authorization.task_authority.test_audit_contract import event_fields
from tests.authorization.task_authority.test_prepared import setup, prepare


def test_revision_fields_do_not_change_existing_manager_authority_evidence_shape():
    _, _, _, resource, _ = setup()
    manager = resource.model_copy(update={
        "task_status": "draft", "idempotency_key": uuid4(),
        "request_digest": "sha256:" + "b" * 64,
    })
    for value in (manager.model_dump(mode="json"), json.loads(manager.model_dump_json())):
        assert all(not key.startswith("revision_") for key in value)
    repair = manager.model_copy(update={"revision_routing_manifest_id": uuid4()})
    assert all(key in repair.model_dump(mode="json") for key in (
        "revision_preparation_id", "revision_preparation_sha256",
        "revision_routing_manifest_id", "revision_replay_preparation_id",
    ))


def repair_resource():
    _, _, _, resource, _ = setup()
    contributor_id = uuid4()
    return resource.model_copy(update={
        "task_status": "needs_revision",
        "assigned_to": contributor_id,
        "assignment_id": uuid4(),
        "assignment_contributor_id": contributor_id,
        "reason": "Correct the recorded preparation",
        "idempotency_key": uuid4(),
        "request_digest": "sha256:" + "b" * 64,
        "revision_preparation_id": uuid4(),
        "revision_preparation_sha256": "sha256:" + "c" * 64,
        "revision_routing_manifest_id": uuid4(),
    })


@pytest.mark.parametrize("field", [
    "task_status", "assigned_to", "assignment_id", "assignment_contributor_id",
    "reason", "idempotency_key", "request_digest", "replay_assignment_id",
    "replay_command_id", "revision_preparation_id", "revision_preparation_sha256",
    "revision_routing_manifest_id",
])
def test_revision_repair_guard_requires_exact_active_assignment_and_preparation(field):
    resource = repair_resource()
    assert task_resource_guard(ActionId.PROJECT_TASK_REVISION_REPAIR, resource)
    changed = {
        "task_status": "ready", "assigned_to": uuid4(), "assignment_id": None,
        "assignment_contributor_id": uuid4(), "reason": " ", "idempotency_key": None,
        "request_digest": None, "replay_assignment_id": uuid4(), "replay_command_id": uuid4(),
        "revision_preparation_id": None, "revision_preparation_sha256": None,
        "revision_routing_manifest_id": None,
    }
    assert not task_resource_guard(
        ActionId.PROJECT_TASK_REVISION_REPAIR, resource.model_copy(update={field: changed[field]})
    )


@pytest.mark.parametrize("status", [
    "needs_revision", "submitted", "evaluation_pending", "review_pending", "accepted", "rejected",
])
def test_revision_repair_terminal_replay_requires_typed_committed_child(status):
    resource = repair_resource().model_copy(update={"task_status": status})
    action = ActionId.PROJECT_TASK_REVISION_REPAIR
    if status != "needs_revision":
        assert not task_resource_guard(action, resource)
    assert task_resource_guard(
        action, resource.model_copy(update={"revision_replay_preparation_id": uuid4()})
    )


def test_revision_repair_missing_root_requires_manifest_and_null_parent_pair():
    resource = repair_resource().model_copy(update={
        "revision_preparation_id": None,
        "revision_preparation_sha256": None,
    })
    assert task_resource_guard(ActionId.PROJECT_TASK_REVISION_REPAIR, resource)
    assert not task_resource_guard(
        ActionId.PROJECT_TASK_REVISION_REPAIR,
        resource.model_copy(update={"revision_routing_manifest_id": None}),
    )
    assert task_resource_guard(
        ActionId.PROJECT_TASK_REVISION_REPAIR,
        resource.model_copy(update={"revision_replay_preparation_id": uuid4(),
                                    "task_status": "submitted"}),
    )


@pytest.mark.parametrize("field", [
    "revision_preparation_id", "revision_preparation_sha256", "revision_routing_manifest_id",
    "revision_replay_preparation_id",
])
@pytest.mark.parametrize("action", [ActionId.PROJECT_TASK_CREATE, ActionId.TASK_READ])
def test_other_task_actions_reject_revision_preparation_fields(action, field):
    _, _, _, resource, _ = setup()
    if action is ActionId.PROJECT_TASK_CREATE:
        resource = resource.model_copy(update={
            "task_status": "draft", "idempotency_key": uuid4(),
            "request_digest": "sha256:" + "b" * 64,
        })
    assert task_resource_guard(action, resource)
    injected = "sha256:" + "c" * 64 if field.endswith("sha256") else uuid4()
    assert not task_resource_guard(action, resource.model_copy(update={field: injected}))


@pytest.mark.parametrize("field", [
    "revision_preparation_id", "revision_preparation_sha256", "revision_routing_manifest_id",
    "revision_replay_preparation_id",
])
async def test_revision_repair_prepared_request_binds_preparation_fields(field):
    _, repo, prepared, resource, evidence = setup()
    repo.find_effective_grant = AsyncMock(return_value=repo.grant)
    repair = repair_resource().model_copy(update={
        "scope_project_id": resource.scope_project_id,
        "actor_profile_id": resource.actor_profile_id,
        "identity_link_id": resource.identity_link_id,
    })
    try:
        handle, value = await prepare(prepared, repair, ActionId.PROJECT_TASK_REVISION_REPAIR)
        changed = repair.model_copy(update={
            field: "sha256:" + "d" * 64 if field.endswith("sha256") else uuid4()
        })
        with pytest.raises(PreparedAuthorizationHandleInvalid):
            await prepared.consume(handle, ActionId.PROJECT_TASK_REVISION_REPAIR, value, changed)
        assert not evidence.events
    finally:
        prepared.close()


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


def manager_event(event_type=Event.TASK_SCREENED):
    fields = event_fields()
    fields.update(
        event_type=event_type,
        from_status="draft",
        to_status="screening",
        locked_lineage=lineage(),
    )
    if event_type is Event.TASK_CREATED:
        fields.update(from_status=None, to_status='draft', source_type='manual', locked_lineage=None)
    elif event_type is Event.TASK_RELEASED:
        fields.update(from_status='screening', to_status='ready', task_reason='Manager release')
    fields["references"].pop("assignment_id")
    from app.core.hashing import canonical_json_hash
    facts = dict(resource_type='task_authority', resource_id=str(fields['entity_id']),
        scope_project_id=str(fields['references']['project_id']), actor_profile_id=str(fields['actor_id']),
        identity_link_id=str(uuid4()), task_status=fields['from_status'] or 'draft', assigned_to=None, assignment_id=None,
        assignment_contributor_id=None, locked_context_hash='sha256:'+'a'*64, reason=fields.get('task_reason'),
        idempotency_key=str(uuid4()), replay_assignment_id=None, request_digest='sha256:'+'b'*64,
        replay_command_id=None)
    fields['manager_authority_facts'] = facts
    fields['authorization_resource_digest'] = canonical_json_hash({'resource_context': {k:v for k,v in facts.items() if v is not None}})
    return fields


@pytest.mark.parametrize(
    ("character", "minimum_canonical_bytes"),
    [("é", 2000), ("😀", 4000), ("\x01", 6000)],
)
def test_manager_audit_admits_every_canonical_1000_character_reason(
    character, minimum_canonical_bytes
):
    fields = manager_event()
    reason = character * 1000
    fields["task_reason"] = reason
    fields["manager_authority_facts"]["reason"] = reason
    from app.core.hashing import canonical_json_hash

    fields["authorization_resource_digest"] = canonical_json_hash(
        {
            "resource_context": {
                key: value
                for key, value in fields["manager_authority_facts"].items()
                if value is not None
            }
        }
    )
    encoded = json.dumps(
        fields["manager_authority_facts"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    assert minimum_canonical_bytes < len(encoded) <= 8192
    if character == "😀":
        assert len(json.dumps(fields["manager_authority_facts"]).encode("utf-8")) > 8192
    assert LifecycleAuditEventInput(**fields).task_reason == reason


def test_manager_audit_rejects_facts_beyond_canonical_evidence_bound():
    fields = manager_event()
    fields["manager_authority_facts"]["reason"] = "\x01" * 1300
    with pytest.raises(ValidationError, match="invalid bounded manager authority facts"):
        LifecycleAuditEventInput(**fields)


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
