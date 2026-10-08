"""Validate immutable submission allows under fresh exact PREP authority."""

from app.modules.authorization.catalogue import ACTION_BY_ID, ActionId
from app.modules.authorization.domain.resource_digest import authorization_resource_digest
from app.modules.authorization.runtime import (
    HumanAuthorizationContext, ServiceAuthorizationContext, ServiceIdentity,
    PreparedAuthorizationHandleInvalid,
)
from app.modules.authorization.submission_consumption import RESOURCE_BY_ACTION


async def validate_submission_replay(owner, issuance, action, caller_input, resource, decision_id):
    """Retain original transport provenance; a retry never emits another allow."""
    owner._validate_consumption(issuance, action, caller_input, resource)
    invalid = PreparedAuthorizationHandleInvalid("invalid retained submission receipt")
    authority = issuance.authority
    context = authority.context
    digest = authorization_resource_digest(resource)
    project_id = getattr(resource, "scope_project_id", None) or resource.project_id
    if (
        type(resource) is not RESOURCE_BY_ACTION[action]
        or issuance.binding.exact_artifact_context != resource.model_dump(mode="json")
        or issuance.binding.exact_artifact_resource_digest != digest
        or authority.action_id is not action
        or (action is ActionId.SUBMISSION_CREATE and authority.scope_project_id != project_id)
    ):
        raise invalid
    if action is ActionId.SUBMISSION_CREATE:
        if (
            type(context) is not HumanAuthorizationContext
            or resource.actor_profile_id != context.actor_profile_id
            or resource.identity_link_id != context.identity_link_id
            or authority.matched_grant_id is None
            or authority.matched_grant_status != "active"
        ):
            raise invalid
    elif (
        type(context) is not ServiceAuthorizationContext
        or context.service_identity is not ServiceIdentity.ARTIFACT_BINDING
        or authority.artifact_resource_id != resource.resource_id
        or authority.artifact_resource_type != resource.resource_type
    ):
        raise invalid
    event = await owner._authorization._audit.get_authority_event(decision_id)
    expected = {
        "id": str(decision_id), "event_domain": "authority",
        "event_type": "SensitiveAuthorizationAllowed", "actor_ref_kind": "actor_profile",
        "actor_id": str(context.actor_profile_id), "action_id": action.value,
        "permission_id": ACTION_BY_ID[action].permission_id.value,
        "project_id": str(project_id), "resource_type": resource.resource_type,
        "resource_id": str(resource.resource_id), "target_ref_kind": "project",
        "target_ref_id": str(project_id), "denial_code": None,
        "after_facts": {"allowed": True, "resource_context_digest": digest},
    }
    if event is None or any(getattr(event, key, object()) != value for key, value in expected.items()):
        raise invalid
    # Fresh authority may be a replacement grant. The immutable original event
    # retains its original grant and transport IDs; neither is rewritten on retry.
    if (event.matched_grant_id is None) != (action is not ActionId.SUBMISSION_CREATE):
        raise invalid
    if event.request_id is None or event.correlation_id is None:
        raise invalid
