"""Exact system-Operator resources for uncertain post-submit delivery recovery."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.authorization.catalogue import ActionAvailability, ActionId
from app.modules.authorization.domain.audit import AuthorizationDenialCode, MatchedAuthorityKind
from app.modules.authorization.schemas import AdminRole
from app.modules.checkers.api.delivery_reconciliation import PostSubmitDeliveryPreparation


POST_SUBMIT_DELIVERY_LIST_ACTION = ActionId.OPERATIONS_POST_SUBMIT_DELIVERY_LIST
POST_SUBMIT_DELIVERY_RECONCILE_ACTION = (
    ActionId.OPERATIONS_POST_SUBMIT_DELIVERY_RECONCILE
)
POST_SUBMIT_DELIVERY_READ_ACTIONS = frozenset({POST_SUBMIT_DELIVERY_LIST_ACTION})
POST_SUBMIT_DELIVERY_MUTATION_ACTIONS = frozenset(
    {POST_SUBMIT_DELIVERY_RECONCILE_ACTION}
)


class PostSubmitDeliveryReadResourceContext(BaseModel):
    """Bind one exact project and privacy-bounded delivery page."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal["project"] = "project"
    resource_id: UUID
    scope_project_id: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def exact_project(self):
        if self.resource_id != self.scope_project_id:
            raise ValueError("post-submit delivery project differs")
        return self


class PostSubmitDeliveryResourceContext(BaseModel):
    """Bind the Operator decision to one exact terminal original and command."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal["outbox_delivery"] = "outbox_delivery"
    resource_id: UUID
    scope_project_id: UUID
    identity_link_id: UUID
    preparation: PostSubmitDeliveryPreparation

    @model_validator(mode="after")
    def exact_source(self):
        if (
            self.resource_id != self.preparation.source.event_id
            or self.scope_project_id != self.preparation.source.project_id
        ):
            raise ValueError("post-submit delivery resource differs")
        return self


POST_SUBMIT_DELIVERY_RESOURCE_BY_ACTION = {
    POST_SUBMIT_DELIVERY_RECONCILE_ACTION: PostSubmitDeliveryResourceContext
}


async def post_submit_delivery_read_denial(
    action, resource, context, repository, refresh, lifecycle,
):
    """Qualify current human, system Operator grant and project without row locks."""
    from app.modules.authorization.runtime import (
        HumanAuthorizationContext,
        PreparedAuthorizationUnsupported,
    )

    refused = AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    if (
        action.action_id not in POST_SUBMIT_DELIVERY_READ_ACTIONS
        or not isinstance(context, HumanAuthorizationContext)
        or type(resource) is not PostSubmitDeliveryReadResourceContext
    ):
        return refused, context, None, None, None, False
    if action.availability is not ActionAvailability.ACTIVE:
        return AuthorizationDenialCode.ACTION_UNAVAILABLE, context, None, None, None, False
    locked = await repository.read_request_actor(
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
        for_update=False,
        allowed_roles=frozenset({AdminRole.OPERATOR}),
    )
    if grant is None:
        return AuthorizationDenialCode.PERMISSION_NOT_GRANTED, context, None, None, None, True
    if not await repository.project_exists(resource.scope_project_id):
        return AuthorizationDenialCode.RESOURCE_NOT_FOUND, context, None, None, None, True
    return (
        None,
        context,
        MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        UUID(str(grant.id)),
        resource.scope_project_id,
        True,
    )
