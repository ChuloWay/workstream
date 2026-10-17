"""Exact system-Operator authority for terminal checker retry-source discovery."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.authorization.catalogue import ActionAvailability, ActionId
from app.modules.authorization.domain.audit import AuthorizationDenialCode, MatchedAuthorityKind
from app.modules.authorization.schemas import AdminRole


CHECKER_RETRY_SOURCE_LIST_ACTION = ActionId.OPERATIONS_CHECKER_RETRY_SOURCE_LIST
CHECKER_RETRY_READ_ACTIONS = frozenset({CHECKER_RETRY_SOURCE_LIST_ACTION})


class CheckerRetrySourceReadResourceContext(BaseModel):
    """Bind one exact project and privacy-bounded page request."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    resource_type: Literal["project"] = "project"
    resource_id: UUID
    scope_project_id: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def exact_project(self):
        if self.resource_id != self.scope_project_id:
            raise ValueError("checker retry discovery project differs")
        return self


async def checker_retry_read_denial(
    action, resource, context, repository, refresh, lifecycle,
):
    """Lock actor, exact system Operator grant and selected Project before disclosure."""
    from app.modules.authorization.runtime import (
        HumanAuthorizationContext, PreparedAuthorizationUnsupported,
    )

    refused = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    if (
        action.action_id not in CHECKER_RETRY_READ_ACTIONS
        or not isinstance(context, HumanAuthorizationContext)
        or type(resource) is not CheckerRetrySourceReadResourceContext
    ):
        return refused, context, None, None, None, False
    if action.availability is not ActionAvailability.ACTIVE:
        return AuthorizationDenialCode.ACTION_UNAVAILABLE, context, None, None, None, False
    locked = await repository.lock_request_actor(
        context.identity_link_id, context.actor_profile_id,
    )
    try:
        context = refresh(locked, context)
    except PreparedAuthorizationUnsupported as exc:
        return exc.denial_code, context, None, None, None, True
    denial = lifecycle(context)
    if denial is not None:
        return denial, context, None, None, None, True
    grant = await repository.find_effective_grant(
        context.actor_profile_id,
        action.permission_id,
        scope_project_id=resource.scope_project_id,
        system_scope_only=True,
        for_update=True,
        allowed_roles=frozenset({AdminRole.OPERATOR}),
    )
    if grant is None:
        return (
            AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
            context, None, None, None, True,
        )
    project = await repository.lock_project(resource.scope_project_id)
    if project is None:
        return AuthorizationDenialCode.RESOURCE_NOT_FOUND, context, None, None, None, True
    return (
        None,
        context,
        MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        UUID(str(grant.id)),
        resource.scope_project_id,
        True,
    )
