"""Fresh shared PREP custody over retained guide and post-policy decisions."""

from app.modules.authorization.catalogue import (
    GUIDE_PROPOSAL_ACTION_IDS,
    POST_POLICY_MUTATION_ACTION_IDS,
    SERVICE_ACTIONS_BY_IDENTITY,
)

from uuid import UUID

from app.modules.authorization.catalogue import ACTION_BY_ID, ActionId
from app.modules.authorization.domain.guide_activation import activation_matches, parse_activation_prepare
from app.modules.authorization.domain.guide_proposals import (
    proposal_matches,
    parse_proposal_prepare,
)
from app.modules.authorization.runtime import (
    PreparedAuthorizationHandleInvalid,
    ServiceAuthorizationContext,
)
from app.modules.authorization.domain.post_policy import (
    DERIVE,
    parse_post_policy_prepare,
    post_policy_matches,
)
from app.modules.authorization.domain.prepared_service import project_setup_resource_matches
from app.modules.actors.api import ServiceIdentity


def parse_review_bindings(action, caller_input, scope, context):
    """Parse exact guide operations sharing the manager permission."""
    try:
        return {
            "activation_prepare_context": parse_activation_prepare(action, caller_input, scope, context),
            "proposal_prepare_context": parse_proposal_prepare(
                action, caller_input, scope, context
            ),
            "post_policy_prepare_context": parse_post_policy_prepare(
                action, caller_input, scope, context
            ),
        }
    except (AttributeError, TypeError, ValueError) as exc:
        raise PreparedAuthorizationHandleInvalid("invalid prepared review handle") from exc


def review_context_matches(binding, resource):
    return activation_matches(binding.activation_prepare_context, resource) and proposal_matches(binding.proposal_prepare_context, resource) and post_policy_matches(
        binding.post_policy_prepare_context,
        resource,
    )


def replay_authority_matches(authority, action, resource):
    """Fresh PREP has locked the current principal and the exact project grant."""
    if authority.action_id is not action or authority.scope_project_id != resource.scope_project_id:
        return False
    if isinstance(authority.context, ServiceAuthorizationContext):
        return (
            action == DERIVE
            and authority.context.service_identity == ServiceIdentity.PROJECT_SETUP
            and action in SERVICE_ACTIONS_BY_IDENTITY[ServiceIdentity.PROJECT_SETUP]
            and authority.matched_grant_id is None
            and project_setup_resource_matches(action, resource, authority.scope_project_id) is True
        )
    return (
        action != DERIVE
        and authority.matched_grant_id is not None
        and authority.matched_grant_status == "active"
        and authority.matched_grant_scope_project_id == resource.scope_project_id
    )


async def validate_review_replay(owner, issuance, action, caller_input, resource, decision_id):
    """Validate the exact original allow under freshly locked project-manager authority."""
    invalid = PreparedAuthorizationHandleInvalid("invalid prepared proposal replay")
    if (
        action not in GUIDE_PROPOSAL_ACTION_IDS | POST_POLICY_MUTATION_ACTION_IDS | {ActionId.PROJECT_GUIDE_ACTIVATE}
        or issuance.binding.action_id is not action
        or owner._binding(action, caller_input, issuance.binding.scope) != issuance.binding
        or owner._root_transaction() is not issuance.transaction
        or owner._scope_from_resource(action, resource) != issuance.binding.scope
        or not review_context_matches(issuance.binding, resource)
    ):
        raise invalid
    authority = issuance.authority
    if not replay_authority_matches(authority, action, resource):
        raise invalid
    event = await owner._authorization._audit.get_authority_event(decision_id)
    locator = resource.facts.locator
    expected = {
        "event_domain": "authority",
        "event_type": "SensitiveAuthorizationAllowed",
        "actor_ref_kind": "actor_profile",
        "actor_id": str(locator.actor_profile_id),
        "action_id": action.value,
        "permission_id": ACTION_BY_ID[action].permission_id.value,
        "project_id": str(locator.project_id),
        "resource_type": resource.resource_type,
        "resource_id": str(resource.resource_id),
        "correlation_id": str(locator.operation_id),
        "target_ref_kind": "project",
        "target_ref_id": str(locator.project_id),
        "denial_code": None,
        "after_facts": {"allowed": True, "resource_context_digest": resource.facts.digest},
    }
    if event is None or any(
        not hasattr(event, k) or getattr(event, k) != v for k, v in expected.items()
    ):
        raise invalid
    try:
        if UUID(str(event.id)) != decision_id:
            raise ValueError("decision mismatch")
        UUID(str(event.request_id))
        if action == DERIVE:
            if event.matched_grant_id is not None:
                raise ValueError("service grant mismatch")
        else:
            UUID(str(event.matched_grant_id))
    except (AttributeError, TypeError, ValueError) as exc:
        raise invalid from exc
