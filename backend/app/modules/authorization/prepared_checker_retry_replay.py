"""Fresh Operator custody validates the exact original retry decision."""

from uuid import UUID

from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.domain.checker_retry import CheckerRetryResourceContext
from app.modules.authorization.runtime import (
    PreparedAuthorizationHandleInvalid, authorization_resource_digest,
)


async def validate_checker_retry_replay(owner, issuance, action, caller_input, resource, decision_id):
    """Read only the original allow; response replay must stage no new decision."""
    invalid = PreparedAuthorizationHandleInvalid("invalid checker retry replay")
    if action is not ActionId.OPERATIONS_CHECKER_RETRY or type(resource) is not CheckerRetryResourceContext:
        raise invalid
    owner._validate_consumption(
        issuance, action, caller_input, resource, historical_checker_retry_link=True,
    )
    authority = issuance.authority
    if (
        authority.scope_project_id is not None
        or authority.matched_grant_id is None
        or authority.matched_grant_status != "active"
        or authority.context.actor_profile_id != resource.preparation.actor_profile_id
    ):
        raise invalid
    event = await owner._authorization._audit.get_authority_event(decision_id)
    expected = {
        "id": str(decision_id),
        "event_domain": "authority",
        "event_type": "SensitiveAuthorizationAllowed",
        "actor_ref_kind": "actor_profile",
        "actor_id": str(resource.preparation.actor_profile_id),
        "action_id": ActionId.OPERATIONS_CHECKER_RETRY.value,
        "permission_id": PermissionId.OPERATIONS_CHECKER_RETRY.value,
        "project_id": str(resource.project_id),
        "resource_type": "checker_run",
        "resource_id": str(resource.resource_id),
        "target_ref_kind": "project",
        "target_ref_id": str(resource.project_id),
        "denial_code": None,
        "request_id": str(resource.preparation.request_key),
        "correlation_id": str(resource.preparation.request_key),
        "after_facts": {
            "allowed": True,
            "resource_context_digest": authorization_resource_digest(resource),
        },
    }
    if event is None or any(getattr(event, field, object()) != value for field, value in expected.items()):
        raise invalid
    try:
        UUID(str(event.matched_grant_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise invalid from exc
