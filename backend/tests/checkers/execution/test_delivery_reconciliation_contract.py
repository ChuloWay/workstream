"""Closed uncertain-delivery identities, held states and exact replay facts."""

from datetime import datetime, timezone

from pydantic import ValidationError
import pytest

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.api.deps.checker_recovery import PostSubmitDeliveryReads
from app.modules.audit.schemas import (
    ActorReferenceKind,
    AuthorityAuditEventInput,
    AuthorityEventType,
)


from app.modules.outbox.api import OutboxAppendInput
from app.modules.checkers.api.delivery_reconciliation import (
    PostSubmitDeliveryChildPayload,
    PostSubmitDeliveryCommand,
    PostSubmitDeliveryPreparation,
    PostSubmitDeliveryResult,
    PostSubmitDeliverySource,
    PostSubmitDeliverySuccessor,
    post_submit_delivery_request_digest,
)


_AUTHORIZATION_RESOURCE_JSON = '{"resource_context":{}}'
_AUTHORIZATION_RESOURCE_DIGEST = canonical_json_hash({"resource_context": {}})


@pytest.fixture
def source() -> PostSubmitDeliverySource:
    return PostSubmitDeliverySource(
        project_id=new_record_id(),
        event_id=new_record_id(),
        event_type="PostSubmissionEvaluationRequested",
        event_version=1,
        aggregate_id=new_record_id(),
        evaluation_request_id=new_record_id(),
        checker_run_id=new_record_id(),
        evaluation_generation=2,
        claim_generation=5,
        payload_digest="sha256:" + "1" * 64,
        finalized_at=datetime(2026, 10, 18, tzinfo=timezone.utc),
        classification="committed",
    )


@pytest.fixture
def preparation(source) -> PostSubmitDeliveryPreparation:
    return PostSubmitDeliveryPreparation(
        command=PostSubmitDeliveryCommand(
            actor_profile_id=new_record_id(),
            project_id=source.project_id,
            event_id=source.event_id,
            request_key=new_record_id(),
            reason="Verify retained outcome after acknowledgement loss",
        ),
        source=source,
    )


def test_source_retains_separate_execution_and_delivery_identity(source) -> None:
    recovered = PostSubmitDeliverySource.model_validate_json(source.model_dump_json())
    assert recovered.evaluation_request_id == source.evaluation_request_id
    assert recovered.checker_run_id == source.checker_run_id
    assert recovered.evaluation_generation == 2
    assert recovered.claim_generation == 5
    assert recovered.evaluation_request_id != recovered.checker_run_id


@pytest.mark.parametrize(
    "field", ["evaluation_request_id", "checker_run_id", "evaluation_generation"]
)
def test_source_requires_each_execution_identity(source, field) -> None:
    values = source.model_dump()
    del values[field]
    with pytest.raises(ValidationError) as caught:
        PostSubmitDeliverySource.model_validate(values)
    assert [(error["loc"], error["type"]) for error in caught.value.errors()] == [
        ((field,), "missing")
    ]


@pytest.mark.parametrize("classification", ["committed", "retry_safe"])
def test_held_child_only_allows_unresolved_source(source, classification) -> None:
    values = source.model_dump() | {
        "reconciliation_event_id": new_record_id(),
        "reconciliation_state": "held",
        "classification": "unresolved",
    }
    assert PostSubmitDeliverySource.model_validate(values).classification == "unresolved"
    with pytest.raises(ValidationError, match="uncertain reconciliation child must be held"):
        PostSubmitDeliverySource.model_validate(values | {"classification": classification})


def test_public_source_rejects_internal_unknown_child_state(source) -> None:
    values = source.model_dump() | {
        "reconciliation_event_id": new_record_id(),
        "reconciliation_state": "unknown",
        "classification": "unresolved",
    }
    with pytest.raises(ValidationError) as caught:
        PostSubmitDeliverySource.model_validate(values)
    assert [(error["loc"], error["type"]) for error in caught.value.errors()] == [
        (("reconciliation_state",), "literal_error")
    ]


@pytest.mark.parametrize("classification", ["committed", "retry_safe"])
def test_preparation_accepts_supported_unreconciled_sources(preparation, classification) -> None:
    values = preparation.model_dump()
    values["source"]["classification"] = classification
    assert PostSubmitDeliveryPreparation.model_validate(values).source.classification == classification


@pytest.mark.parametrize("change", ["unresolved", "existing_child", "project", "event"])
def test_preparation_rejects_held_or_mismatched_source(preparation, change) -> None:
    values = preparation.model_dump()
    if change == "unresolved":
        values["source"]["classification"] = "unresolved"
    elif change == "existing_child":
        values["source"].update(
            reconciliation_event_id=new_record_id(), reconciliation_state="pending"
        )
    else:
        values["command"][f"{change}_id"] = new_record_id()
    # Both components are valid independently; only their preparation is denied.
    PostSubmitDeliveryCommand.model_validate(values["command"])
    PostSubmitDeliverySource.model_validate(values["source"])
    with pytest.raises(ValidationError, match="post-submit delivery preparation differs"):
        PostSubmitDeliveryPreparation.model_validate(values)


@pytest.mark.parametrize("field", ["payload", "outcome_json", "transport_url", "exception_text"])
def test_child_payload_excludes_raw_private_fields(preparation, field) -> None:
    source = preparation.source
    child = PostSubmitDeliveryChildPayload(
        original_event_id=source.event_id,
        original_claim_generation=source.claim_generation,
        original_payload_digest=source.payload_digest,
        original_event_type=source.event_type,
        original_event_version=source.event_version,
        evaluation_request_id=source.evaluation_request_id,
        checker_run_id=source.checker_run_id,
        evaluation_generation=source.evaluation_generation,
        classification=source.classification,
        reconciliation_request_id=preparation.command.request_key,
        request_digest=post_submit_delivery_request_digest(preparation),
        authorization_decision_id=new_record_id(),
        authorization_resource_digest=_AUTHORIZATION_RESOURCE_DIGEST,
        authorization_resource_json=_AUTHORIZATION_RESOURCE_JSON,
        operator_actor_profile_id=preparation.command.actor_profile_id,
        operator_identity_link_id=new_record_id(),
    )
    private_value = "private-provider-coordinate"
    with pytest.raises(ValidationError) as caught:
        PostSubmitDeliveryChildPayload.model_validate(
            child.model_dump() | {field: private_value}
        )
    assert [(error["loc"], error["type"]) for error in caught.value.errors()] == [
        ((field,), "extra_forbidden")
    ]
    assert private_value not in str(caught.value)


def test_child_payload_passes_canonical_outbox_privacy_validation(preparation) -> None:
    source = preparation.source
    child = PostSubmitDeliveryChildPayload(
        original_event_id=source.event_id,
        original_claim_generation=source.claim_generation,
        original_payload_digest=source.payload_digest,
        original_event_type=source.event_type,
        original_event_version=source.event_version,
        evaluation_request_id=source.evaluation_request_id,
        checker_run_id=source.checker_run_id,
        evaluation_generation=source.evaluation_generation,
        classification=source.classification,
        reconciliation_request_id=preparation.command.request_key,
        request_digest=post_submit_delivery_request_digest(preparation),
        authorization_decision_id=new_record_id(),
        authorization_resource_digest=_AUTHORIZATION_RESOURCE_DIGEST,
        authorization_resource_json=_AUTHORIZATION_RESOURCE_JSON,
        operator_actor_profile_id=preparation.command.actor_profile_id,
        operator_identity_link_id=new_record_id(),
    )

    appended = OutboxAppendInput(
        event_type="PostSubmissionDeliveryReconciliationRequested",
        event_version=1,
        aggregate_type="outbox_delivery",
        aggregate_id=source.event_id,
        project_id=source.project_id,
        correlation_id=str(preparation.command.request_key),
        causation_event_id=source.event_id,
        idempotency_key="post-submit-reconcile:" + str(source.event_id),
        payload=child.model_dump(mode="json"),
    )
    assert appended.payload["reconciliation_request_id"] == str(
        preparation.command.request_key
    )


@pytest.mark.parametrize(
    "section,field,replacement",
    [
        ("command", "reason", "Verify a different operational incident"),
        ("command", "request_key", None),
        ("source", "evaluation_request_id", None),
        ("source", "checker_run_id", None),
        ("source", "evaluation_generation", 3),
        ("source", "claim_generation", 6),
        ("source", "payload_digest", "sha256:" + "3" * 64),
        ("source", "classification", "retry_safe"),
    ],
)
def test_request_digest_binds_command_and_source(preparation, section, field, replacement) -> None:
    original = post_submit_delivery_request_digest(preparation)
    assert post_submit_delivery_request_digest(
        PostSubmitDeliveryPreparation.model_validate(preparation.model_dump())
    ) == original
    values = preparation.model_dump()
    values[section][field] = new_record_id() if replacement is None else replacement
    changed = PostSubmitDeliveryPreparation.model_validate(values)
    assert post_submit_delivery_request_digest(changed) != original


@pytest.mark.parametrize("change", ["event", "classification"])
def test_result_binds_successor_identity_state_and_classification(source, change) -> None:
    child = PostSubmitDeliverySuccessor(
        event_id=new_record_id(),
        payload_digest="sha256:" + "4" * 64,
        occurred_at=source.finalized_at,
        classification=source.classification,
    )
    result = PostSubmitDeliveryResult(
        source=PostSubmitDeliverySource.model_validate(source.model_dump() | {
            "reconciliation_event_id": child.event_id,
            "reconciliation_state": "pending",
        }),
        successor=child,
        authorization_decision_id=new_record_id(),
    )
    values = result.model_dump()
    if change == "event":
        values["successor"]["event_id"] = new_record_id()
    else:
        values["successor"]["classification"] = "retry_safe"
    PostSubmitDeliverySource.model_validate(values["source"])
    PostSubmitDeliverySuccessor.model_validate(values["successor"])
    with pytest.raises(ValidationError, match="post-submit delivery result differs"):
        PostSubmitDeliveryResult.model_validate(values)


@pytest.mark.parametrize(
    "state,current_classification",
    [("active", "retry_safe"), ("acknowledged", "committed"), ("held", "unresolved")],
)
def test_replay_result_preserves_successor_with_current_child_projection(
    source, state, current_classification,
) -> None:
    child = PostSubmitDeliverySuccessor(
        event_id=new_record_id(),
        payload_digest="sha256:" + "4" * 64,
        occurred_at=source.finalized_at,
        classification="retry_safe",
    )
    projected = PostSubmitDeliverySource.model_validate(
        source.model_dump()
        | {
            "classification": current_classification,
            "reconciliation_event_id": child.event_id,
            "reconciliation_state": state,
        }
    )

    result = PostSubmitDeliveryResult(
        source=projected,
        successor=child,
        authorization_decision_id=new_record_id(),
    )
    assert result.source.reconciliation_state == state
    assert result.successor.classification == "retry_safe"


@pytest.mark.asyncio
async def test_read_response_validation_precedes_authority_audit_commit() -> None:
    class Session:
        commits = 0

        async def commit(self):
            self.commits += 1

    class Service:
        async def discover(self, _query):
            return {"items": (), "next_cursor": None}

    session = Session()
    reads = PostSubmitDeliveryReads(session, Service())
    with pytest.raises(ValidationError):
        await reads.discover(new_record_id(), limit=50, cursor=None)
    assert session.commits == 0


def test_delivery_audit_resource_keeps_project_as_its_only_target_namespace() -> None:
    event_id = new_record_id()
    project_id = new_record_id()
    source_id = new_record_id()
    values = {
        "event_id": event_id,
        "event_type": AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED,
        "entity_type": "authorization_decision",
        "entity_id": str(event_id),
        "actor_ref_kind": ActorReferenceKind.ACTOR_PROFILE,
        "actor_ref": str(new_record_id()),
        "request_id": new_record_id(),
        "correlation_id": new_record_id(),
        "permission_id": "operations.reconcile.run",
        "action_id": "operations.post_submit_delivery.reconcile",
        "project_id": str(project_id),
        "resource_type": "outbox_delivery",
        "resource_id": str(source_id),
        "target_ref_kind": "project",
        "target_ref_id": str(project_id),
        "reason": "authorization_evaluation",
        "after_facts": {
            "allowed": True,
            "resource_context_digest": "sha256:" + "a" * 64,
        },
    }

    admitted = AuthorityAuditEventInput.model_validate(values)
    assert (admitted.resource_type, admitted.target_ref_kind) == (
        "outbox_delivery",
        "project",
    )
    for field in ("target_ref_kind", "invalidation_target_kind"):
        candidate = values | {field: "outbox_delivery"}
        if field == "invalidation_target_kind":
            candidate["invalidation_target_ref"] = str(source_id)
        with pytest.raises(TypeError, match="invalid authority audit input"):
            AuthorityAuditEventInput.model_validate(candidate)
