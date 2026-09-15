"""AUTH custody over PROJECTS' sole complete activation facts contract."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.modules.authorization.catalogue import ActionId
from app.modules.projects.api.guide_activation import GuideActivationFacts, GuideActivationLocator


def activation_selectors(locator):
    """Bind the exact request identity before acquiring product locks."""
    if type(locator) is not GuideActivationLocator:
        raise ValueError("invalid activation locator")
    parsed = GuideActivationLocator.model_validate(locator.model_dump(), strict=True)
    return {"operation_family": "guide_activation", **parsed.model_dump(mode="json")}


class ProjectGuideActivationResourceContext(BaseModel):
    """Closed complete owner facts, with no second policy readiness definition."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    resource_type: Literal["project_guide_activation"]
    resource_id: UUID
    scope_project_id: UUID
    facts: GuideActivationFacts

    @model_validator(mode="after")
    def validate_identity(self):
        """Revalidate the entire owner tree and its operation/project/guide links."""
        if type(self.facts) is not GuideActivationFacts:
            raise ValueError("invalid activation facts")
        # Round-trip the complete tree: earlier public nested types need not enable
        # instance revalidation, and model_copy/model_construct can bypass it.
        facts = GuideActivationFacts.model_validate(self.facts.model_dump(), strict=True)
        activation_selectors(facts.locator)
        target = facts.receipt.command.target.proposal
        if (
            self.resource_type != "project_guide_activation"
            or self.resource_id != facts.locator.guide_id
            or self.scope_project_id != facts.locator.project_id
            or facts.locator.guide_id != target.guide_id
            or facts.locator.project_id != target.project_id
            or facts.locator.operation_id != facts.receipt.operation_id
        ):
            raise ValueError("activation resource identity mismatch")
        return self


def activation_resource(facts):
    """Wrap only canonical PROJECTS facts and preserve their digest owner."""
    if type(facts) is not GuideActivationFacts:
        raise ValueError("invalid activation facts")
    return ProjectGuideActivationResourceContext(
        resource_type="project_guide_activation", resource_id=facts.locator.guide_id,
        scope_project_id=facts.locator.project_id, facts=facts,
    )


def parse_activation_prepare(action, caller_input, scope, context):
    """Bind the closed operation to the authenticated request and root scope."""
    if action != ActionId.PROJECT_GUIDE_ACTIVATE:
        return None
    value = dict(caller_input.request_value)
    if value.pop("operation_family", None) != "guide_activation":
        raise ValueError("invalid activation family")
    locator = GuideActivationLocator.model_validate(value)
    if (
        locator.action_id != action
        or locator.actor_profile_id != context.actor_profile_id
        or locator.identity_link_id != context.identity_link_id
        or locator.request_id != context.request_id
        or locator.operation_id != context.correlation_id
        or locator.operation_id != caller_input.idempotency_key
        or locator.project_id != scope.project_id
    ):
        raise ValueError("activation preparation differs from custody")
    return activation_selectors(locator)


def activation_matches(binding, resource):
    """Fence activation and sibling resources in both directions."""
    exact = type(resource) is ProjectGuideActivationResourceContext
    if exact != (binding is not None):
        return False
    if not exact:
        return True
    try:
        resource.validate_identity()
        return binding == activation_selectors(resource.facts.locator)
    except (AttributeError, TypeError, ValueError):
        return False
