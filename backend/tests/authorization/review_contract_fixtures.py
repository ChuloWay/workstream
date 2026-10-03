"""Side-effect-free inputs for the initial Review authorization contract."""

from app.core.identifiers import new_record_id
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.review_contracts import ReviewLifecyclePhase, ReviewDecisionValue

SHA = "sha256:" + "a" * 64


def _decision_values() -> dict[str, object]:
    return {
        "action_id": ActionId.REVIEW_DECISION,
        "lifecycle_phase": ReviewLifecyclePhase.SHADOW,
        "lifecycle_digest": SHA,
        "project_id": new_record_id(),
        "task_id": new_record_id(),
        "task_assignment_id": new_record_id(),
        "submission_id": new_record_id(),
        "checker_run_id": new_record_id(),
        "queue_entry_id": new_record_id(),
        "review_lease_id": new_record_id(),
        "reviewer_actor_profile_id": new_record_id(),
        "packet_manifest_id": new_record_id(),
        "packet_manifest_generation": 1,
        "packet_manifest_digest": SHA,
        "artifact_binding_id": new_record_id(),
        "chain_digest": SHA,
        "review_id": new_record_id(),
        "review_decision_request_id": new_record_id(),
        "review_operation_id": new_record_id(),
        "idempotency_key": new_record_id(),
        "request_digest": SHA,
        "review_aggregate_digest": SHA,
        "submission_version": 1,
        "inherited_unresolved_blocking_count": 0,
        "decision_shape": "initial",
        "decision": ReviewDecisionValue.ACCEPT,
        "finding_count": 0,
        "blocking_finding_count": 0,
        "findings_resolutions_digest": SHA,
        "review_policy_id": new_record_id(),
        "review_policy_generation": 1,
        "review_policy_digest": SHA,
        "reviewer_contribution_policy_version_id": new_record_id(),
        "artifact_hash": SHA,
    }
