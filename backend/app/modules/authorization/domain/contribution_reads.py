"""Exact self ownership and deliberately distinct PM/Finance export coverage."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.modules.authorization.catalogue import ActionAvailability, ActionId
from app.modules.authorization.domain.audit import AuthorizationDenialCode, MatchedAuthorityKind
from app.modules.authorization.schemas import AdminRole

_STRICT = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")


class ContributionSelfReadResourceContext(BaseModel):
    """The caller's own facts, including any optional project filter in the digest."""

    model_config = _STRICT
    resource_type: Literal["actor_profile"] = "actor_profile"
    resource_id: UUID
    actor_profile_id: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def exact_actor(self):
        """Self reads cannot name a second contributor."""
        if self.resource_id != self.actor_profile_id:
            raise ValueError("contribution self resource differs from caller")
        return self


class ContributionProjectReadResourceContext(BaseModel):
    """One exact project's historical facts; the digest binds the selected query."""

    model_config = _STRICT
    resource_type: Literal["project"] = "project"
    resource_id: UUID
    scope_project_id: UUID
    actor_profile_id: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def exact_project(self):
        """Project disclosure always selects the same resource and grant scope."""
        if self.resource_id != self.scope_project_id:
            raise ValueError("contribution project resource differs from scope")
        return self


CONTRIBUTION_READ_RESOURCE_BY_ACTION = {
    ActionId.CONTRIBUTION_READ_SELF: ContributionSelfReadResourceContext,
    ActionId.CONTRIBUTION_READ_PROJECT: ContributionProjectReadResourceContext,
}


async def contribution_read_denial(action, resource, context, repository, refresh, lifecycle):
    """Hold current actor/grant/Project locks through the caller's response commit."""
    from app.modules.authorization.runtime import (
        HumanAuthorizationContext, PreparedAuthorizationUnsupported,
    )

    refused = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    expected = CONTRIBUTION_READ_RESOURCE_BY_ACTION.get(action.action_id)
    if (not isinstance(context, HumanAuthorizationContext) or expected is None
            or type(resource) is not expected):
        return refused, context, None, None, None, False
    try:
        resource = expected.model_validate(resource)
    except ValidationError:
        return refused, context, None, None, None, False
    if resource.actor_profile_id != context.actor_profile_id:
        return refused, context, None, None, None, False
    if action.availability is not ActionAvailability.ACTIVE:
        return AuthorizationDenialCode.ACTION_UNAVAILABLE, context, None, None, None, False
    locked = await repository.lock_request_actor(context.identity_link_id, context.actor_profile_id)
    try:
        context = refresh(locked, context)
    except PreparedAuthorizationUnsupported as exc:
        return exc.denial_code, context, None, None, None, True
    denial = lifecycle(context)
    if denial is not None:
        return denial, context, None, None, None, True
    if action.action_id is ActionId.CONTRIBUTION_READ_SELF:
        return None, context, MatchedAuthorityKind.ACTOR_SELF, None, None, True
    # Canonical PM coverage includes system scope. Finance disclosure explicitly
    # requires a grant on this project, even when a system Finance grant exists.
    grant = await repository.find_effective_grant(
        context.actor_profile_id, action.permission_id,
        scope_project_id=resource.scope_project_id, for_update=True,
        allowed_roles=frozenset({AdminRole.PROJECT_MANAGER}),
    )
    if grant is None:
        grant = await repository.find_effective_grant(
            context.actor_profile_id, action.permission_id,
            scope_project_id=resource.scope_project_id, exact_project_scope=True,
            for_update=True, allowed_roles=frozenset({AdminRole.FINANCE_AUTHORITY}),
        )
    if grant is None:
        return AuthorizationDenialCode.PERMISSION_NOT_GRANTED, context, None, None, None, True
    project = await repository.lock_project(resource.scope_project_id)
    if project is None:
        return AuthorizationDenialCode.RESOURCE_NOT_FOUND, context, None, None, None, True
    return (None, context, MatchedAuthorityKind.ADMIN_ROLE_GRANT, UUID(str(grant.id)),
            resource.scope_project_id, True)
