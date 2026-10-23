"""One current system-wide project reader, never a contributor grant list."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.modules.authorization.catalogue import ActionAvailability, ActionId
from app.modules.authorization.domain.audit import AuthorizationDenialCode, MatchedAuthorityKind
from app.modules.authorization.schemas import AdminRole


class ProjectCatalogueResourceContext(BaseModel):
    """Bind the page query to the caller, without selecting another actor."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")
    resource_type: Literal["project_catalogue"] = "project_catalogue"
    resource_id: UUID
    actor_profile_id: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def exact_actor(self):
        if self.resource_id != self.actor_profile_id:
            raise ValueError("project catalogue differs from caller")
        return self


SYSTEM_PROJECT_READ_ROLES = frozenset({
    AdminRole.PROJECT_MANAGER, AdminRole.OPERATOR,
    AdminRole.FINANCE_AUTHORITY, AdminRole.AUDIT_AUTHORITY,
})


async def project_catalogue_read_denial(action, resource, context, repository, refresh, lifecycle):
    """Hold the actor and matched system grant until the identity page commits."""
    from app.modules.authorization.runtime import HumanAuthorizationContext, PreparedAuthorizationUnsupported

    refused = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    if (
        action.action_id is not ActionId.PROJECT_CATALOGUE_LIST
        or not isinstance(context, HumanAuthorizationContext)
        or type(resource) is not ProjectCatalogueResourceContext
    ):
        return refused, context, None, None, None, False
    try:
        resource = ProjectCatalogueResourceContext.model_validate(resource)
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
    grant = await repository.find_effective_grant(
        context.actor_profile_id, action.permission_id, scope_project_id=None,
        system_scope_only=True, for_update=True, allowed_roles=SYSTEM_PROJECT_READ_ROLES,
    )
    if grant is None:
        return AuthorizationDenialCode.PERMISSION_NOT_GRANTED, context, None, None, None, True
    return None, context, MatchedAuthorityKind.ADMIN_ROLE_GRANT, UUID(str(grant.id)), None, True
