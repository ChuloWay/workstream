"""Exact ContributionPolicy mutation parsing for PREP custody."""

from collections.abc import Mapping
from uuid import UUID

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.contribution_policies import (
    CONTRIBUTION_POLICY_MUTATION_ACTIONS,
    CONTRIBUTION_POLICY_RESOURCE_BY_ACTION,
)
from app.modules.authorization.runtime import (
    PreparedAuthorizationHandleInvalid,
    authorization_resource_digest,
)


def parse_prepared_contribution_policy(
    action_id: ActionId, request_value: Mapping[str, object]
) -> dict[str, object]:
    """Bind one exact action-specific resource and its canonical context digest."""
    if action_id not in CONTRIBUTION_POLICY_MUTATION_ACTIONS:
        return {}
    try:
        value = dict(request_value)
        for name in (
            "resource_id",
            "scope_project_id",
            "contribution_policy_version_id",
            "operation_id",
        ):
            value[name] = UUID(str(value[name]))
        if "adapter_binding_ids" in value:
            value["adapter_binding_ids"] = tuple(
                UUID(str(item)) for item in value["adapter_binding_ids"]
            )
        resource = CONTRIBUTION_POLICY_RESOURCE_BY_ACTION[action_id].model_validate(value)
    except (KeyError, TypeError, ValueError) as exc:
        raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle") from exc
    return {
        "contribution_policy_context": resource.model_dump(mode="json"),
        "contribution_policy_resource_digest": authorization_resource_digest(resource),
    }


def prepared_contribution_policy_matches(
    action_id: ActionId, context: dict | None, digest: str | None, resource: object
) -> bool:
    """Reject sibling classes, substituted facts, or altered context hashes."""
    return type(resource) is CONTRIBUTION_POLICY_RESOURCE_BY_ACTION.get(action_id) and (
        context == resource.model_dump(mode="json")
        and digest == authorization_resource_digest(resource)
    )
