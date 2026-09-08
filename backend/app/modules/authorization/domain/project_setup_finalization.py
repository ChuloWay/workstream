"""Closed finalization resources bound to canonical fixed-service PREP custody."""

from __future__ import annotations

from dataclasses import replace
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.modules.authorization.api.project_setup_finalization import (
    ProjectSetupFinalizationFacts,
    ProjectSetupFinalizationLocator,
    setup_finalization_authority_digest,
    setup_finalization_identity,
)
from app.modules.authorization.catalogue import ActionId

_STRICT = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProjectSetupFinalizationPrepareContext(BaseModel):
    """Bind only selectors known before POL acquires product locks."""

    model_config = _STRICT
    binding_kind: Literal["project_guide_setup_finalization"] = "project_guide_setup_finalization"
    project_id: UUID
    operation_id: UUID
    correlation_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    service_identity: Literal["workstream.project.setup"] = "workstream.project.setup"


class ProjectSetupFinalizationResourceContext(BaseModel):
    """Complete immutable public facts for the sole finalization resource."""

    model_config = _STRICT
    resource_type: Literal["project_guide_setup_finalization"] = "project_guide_setup_finalization"
    resource_id: UUID
    scope_project_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    service_identity: Literal["workstream.project.setup"] = "workstream.project.setup"
    facts: ProjectSetupFinalizationFacts

    @model_validator(mode="after")
    def require_exact_identity(self):
        """Revalidate public scalars and deterministic identity without private POL reads."""
        facts = replace(self.facts)
        identity = setup_finalization_identity(
            facts.setup_run_id, facts.setup_generation, facts.compilation_id
        )
        if identity != (facts.finalization_id, facts.operation_id, facts.correlation_id):
            raise ValueError("finalization identity is inconsistent")
        if self.resource_id != facts.finalization_id or self.scope_project_id != facts.project_id:
            raise ValueError("finalization resource identity is inconsistent")
        return self


def finalization_prepare_context(
    locator: ProjectSetupFinalizationLocator, actor_profile_id: UUID, identity_link_id: UUID
) -> ProjectSetupFinalizationPrepareContext:
    """Create the narrow preparation binding from canonical resolved identity."""
    return ProjectSetupFinalizationPrepareContext(
        project_id=locator.project_id,
        operation_id=locator.operation_id,
        correlation_id=locator.correlation_id,
        actor_profile_id=actor_profile_id,
        identity_link_id=identity_link_id,
    )


def finalization_resource_context(
    facts: ProjectSetupFinalizationFacts, actor_profile_id: UUID, identity_link_id: UUID
) -> ProjectSetupFinalizationResourceContext:
    """Build the exact final resource without accepting another public fact kind."""
    if type(facts) is not ProjectSetupFinalizationFacts:
        raise ValueError("invalid finalization facts")
    return ProjectSetupFinalizationResourceContext(
        resource_id=facts.finalization_id,
        scope_project_id=facts.project_id,
        actor_profile_id=actor_profile_id,
        identity_link_id=identity_link_id,
        facts=facts,
    )


def finalization_resource_digest(resource: ProjectSetupFinalizationResourceContext) -> str:
    """Use the public canonical authority digest shared with POL and database custody."""
    return setup_finalization_authority_digest(
        resource.facts, resource.actor_profile_id, resource.identity_link_id
    )


def finalization_context_matches(prepared: dict | None, resource: object) -> bool:
    """Reject resource-kind substitution and bind every prepared selector."""
    exact = isinstance(resource, ProjectSetupFinalizationResourceContext)
    if exact != (prepared is not None):
        return False
    if not exact:
        return True
    try:
        resource.require_exact_identity()
        return prepared == finalization_prepare_context(
            ProjectSetupFinalizationLocator(
                project_id=resource.scope_project_id,
                operation_id=resource.facts.operation_id,
                correlation_id=resource.facts.correlation_id,
            ),
            resource.actor_profile_id,
            resource.identity_link_id,
        ).model_dump(mode="json")
    except (TypeError, ValueError):
        return False


def parse_finalization_prepare(
    action: ActionId,
    request_value: object,
    *,
    actor_profile_id: UUID,
    identity_link_id: UUID,
    service_identity: object,
    request_id: UUID,
    correlation_id: UUID,
    scope_project_id: UUID | None,
    idempotency_key: UUID,
) -> dict | None:
    """Compare caller preparation to actual private PREP identity and request custody."""
    tagged = isinstance(request_value, dict) and request_value.get("binding_kind") == (
        "project_guide_setup_finalization"
    )
    if action is not ActionId.PROJECT_SETUP_RUN_UPDATE:
        if tagged:
            raise ValueError("finalization preparation requires its exact action")
        return None
    if not tagged:
        raise ValueError("finalization preparation is required")
    parsed = ProjectSetupFinalizationPrepareContext.model_validate_json(json.dumps(request_value))
    if (
        parsed.actor_profile_id != actor_profile_id
        or parsed.identity_link_id != identity_link_id
        or parsed.service_identity != service_identity
        or parsed.project_id != scope_project_id
        or parsed.operation_id != request_id
        or parsed.correlation_id != correlation_id
        or parsed.operation_id != idempotency_key
    ):
        raise ValueError("finalization preparation differs from private custody")
    return parsed.model_dump(mode="json")


def finalization_replay_event_matches(
    event: Any,
    *,
    actor_profile_id: UUID,
    action_id: ActionId,
    permission_id: str,
    request_id: UUID,
    correlation_id: UUID,
    resource: ProjectSetupFinalizationResourceContext,
) -> bool:
    """Require the complete original allow envelope, including absence of a denial."""
    expected = {
        "event_domain": "authority",
        "event_type": "SensitiveAuthorizationAllowed",
        "actor_ref_kind": "actor_profile",
        "actor_id": str(actor_profile_id),
        "action_id": action_id.value,
        "permission_id": permission_id,
        "project_id": str(resource.scope_project_id),
        "resource_type": resource.resource_type,
        "resource_id": str(resource.resource_id),
        "request_id": str(request_id),
        "correlation_id": str(correlation_id),
        "denial_code": None,
    }
    if event is None or any(
        not hasattr(event, key) or getattr(event, key) != value for key, value in expected.items()
    ):
        return False
    after = getattr(event, "after_facts", None)
    return (
        isinstance(after, dict)
        and set(after) == {"allowed", "resource_context_digest"}
        and after.get("allowed") is True
        and (after.get("resource_context_digest") == finalization_resource_digest(resource))
    )
