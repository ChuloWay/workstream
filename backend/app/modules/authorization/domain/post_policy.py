"""Exact finalized post-policy facts and closed request-local PREP selectors."""

from dataclasses import fields
import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.modules.authorization.api.post_policy import (
    PostPolicyAuthorizationFacts,
    PostPolicyAuthorizationLocator,
)
from app.modules.authorization.catalogue import ActionId, POST_POLICY_ACTION_IDS

_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
READ = ActionId.PROJECT_GUIDE_COMPILATION_REVIEW_PACKAGE_READ
DERIVE = ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_DERIVE


def validate_locator(locator):
    """Reject lookalike selectors before any product lock or authority decision."""
    if type(locator) is not PostPolicyAuthorizationLocator:
        raise ValueError("invalid post-policy locator")
    for field in fields(locator):
        value = getattr(locator, field.name)
        if field.name == "action_id":
            if value not in POST_POLICY_ACTION_IDS:
                raise ValueError("invalid post-policy action")
        elif not isinstance(value, UUID):
            raise ValueError("invalid post-policy selector")
    return locator


def post_policy_selectors(locator):
    """Keep sibling proposal reads in a distinct prepared-operation family."""
    validate_locator(locator)
    return {
        "operation_family": "post_policy",
        **{field.name: str(getattr(locator, field.name)) for field in fields(locator)},
    }


class PostPolicyResourceContext(BaseModel):
    """AUTH validates exact custody; PROJECTS remains the policy/lifecycle owner."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    resource_type: str
    resource_id: UUID
    scope_project_id: UUID
    facts: PostPolicyAuthorizationFacts

    @model_validator(mode="after")
    def validate_identity(self):
        """Validate every independent typed commitment and the action resource."""
        f = self.facts
        if type(f) is not PostPolicyAuthorizationFacts:
            raise ValueError("invalid post-policy facts")
        locator = validate_locator(f.locator)
        for field in fields(f):
            value = getattr(f, field.name)
            if field.name.endswith("_id") and not isinstance(value, UUID):
                raise ValueError("invalid post-policy identity")
            if field.name.endswith(("_hash", "_digest")) and (
                not isinstance(value, str) or not _HASH.fullmatch(value)
            ):
                raise ValueError("invalid post-policy digest")
        if type(f.setup_generation) is not int or f.setup_generation < 1:
            raise ValueError("invalid post-policy generation")
        if not isinstance(f.guide_version, str) or not f.guide_version.strip():
            raise ValueError("invalid post-policy guide version")
        action = ActionId(locator.action_id)
        states = (
            {"compiled", "approved", "superseded"}
            if action == READ
            else (
                {"compiled", "approved"}
                if action == ActionId.PROJECT_POST_SUBMIT_CHECKER_POLICY_CORRECTION_REQUEST
                else {"compiled"}
            )
        )
        if f.lifecycle_status not in states:
            raise ValueError("invalid post-policy lifecycle")
        if (
            self.resource_id != f.policy_id
            or self.scope_project_id != locator.project_id
            or self.resource_type != resource_kind(action)
        ):
            raise ValueError("post-policy resource identity mismatch")
        return self


def resource_kind(action):
    return (
        "project_guide_compilation_review_package"
        if action == READ
        else "project_post_submit_checker_policy_mutation"
    )


def post_policy_resource(facts):
    """Preserve the public owner's exact digest and selected policy identity."""
    if type(facts) is not PostPolicyAuthorizationFacts:
        raise ValueError("invalid post-policy facts")
    locator = validate_locator(facts.locator)
    return PostPolicyResourceContext(
        resource_type=resource_kind(locator.action_id),
        resource_id=facts.policy_id,
        scope_project_id=locator.project_id,
        facts=facts,
    )


def parse_post_policy_prepare(action, caller_input, scope, context):
    """Bind the operation family to actual authenticated request and root scope."""
    if action not in POST_POLICY_ACTION_IDS:
        return None
    value = dict(caller_input.request_value)
    if action == READ and "operation_family" not in value:
        return None
    if value.pop("operation_family", None) != "post_policy":
        raise ValueError("invalid post-policy family")
    locator = PostPolicyAuthorizationLocator(
        **{name: raw if name == "action_id" else UUID(str(raw)) for name, raw in value.items()}
    )
    validate_locator(locator)
    if (
        locator.action_id != action
        or locator.actor_profile_id != context.actor_profile_id
        or locator.identity_link_id != context.identity_link_id
        or locator.request_id != context.request_id
        or locator.operation_id != context.correlation_id
        or locator.project_id != scope.project_id
        or locator.operation_id != caller_input.idempotency_key
    ):
        raise ValueError("post-policy preparation differs from custody")
    return post_policy_selectors(locator)


def post_policy_matches(binding, resource):
    """Reject sibling contexts and changed selectors in both directions."""
    exact = type(resource) is PostPolicyResourceContext
    if exact != (binding is not None):
        return False
    if not exact:
        return True
    try:
        resource.validate_identity()
        return binding == post_policy_selectors(resource.facts.locator)
    except (AttributeError, TypeError, ValueError):
        return False
