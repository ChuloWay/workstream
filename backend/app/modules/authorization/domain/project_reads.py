"""Existing canonical project-read evaluation, owned by AUTH."""

from app.modules.authorization.catalogue import ActionAvailability
from app.modules.authorization.domain.audit import AuthorizationDenialCode, MatchedAuthorityKind
from app.modules.authorization.runtime import HumanAuthorizationContext, ProjectReadResourceContext


async def project_read_denial(action, resource, context, repository, revalidate_actor, lifecycle_denial):
    """Authorize one canonical project through admin or contributor grants."""
    if not isinstance(context, HumanAuthorizationContext) or not isinstance(
        resource, ProjectReadResourceContext
    ):
        return AuthorizationDenialCode.RESOURCE_GUARD_DENIED, context, None, None, None, False
    if action.availability is not ActionAvailability.ACTIVE:
        return AuthorizationDenialCode.ACTION_UNAVAILABLE, context, None, None, None, False
    if revalidate_actor is None:
        return AuthorizationDenialCode.RESOURCE_GUARD_DENIED, context, None, None, None, False
    context = await revalidate_actor(context, resource)
    lifecycle = lifecycle_denial(context)
    if lifecycle is not None:
        return lifecycle, context, None, None, None, True
    if not resource.project_exists:
        return (
            AuthorizationDenialCode.RESOURCE_NOT_FOUND,
            context,
            None,
            None,
            None,
            True,
        )
    # Keep the matched grant stable through response projection and commit so a
    # concurrent revoke cannot authorize a stale read from this transaction.
    admin_grant = await repository.find_effective_grant(
        context.actor_profile_id,
        action.permission_id,
        scope_project_id=resource.scope_project_id,
        system_scope_only=False,
        for_update=True,
    )
    if admin_grant is not None:
        return (
            None,
            context,
            MatchedAuthorityKind.ADMIN_ROLE_GRANT,
            admin_grant.id,
            resource.scope_project_id,
            True,
        )
    project_grant = await repository.find_active_project_role_any(
        project_id=resource.scope_project_id,
        actor_profile_id=context.actor_profile_id,
        for_update=True,
    )
    if project_grant is not None:
        return (
            None,
            context,
            MatchedAuthorityKind.PROJECT_ROLE_GRANT,
            project_grant.id,
            resource.scope_project_id,
            True,
        )
    out_of_scope = await repository.has_effective_permission_any_scope(
        context.actor_profile_id, action.permission_id
    ) or await repository.has_active_project_role_any_project(context.actor_profile_id)
    return (
        AuthorizationDenialCode.SCOPE_NOT_AUTHORIZED
        if out_of_scope
        else AuthorizationDenialCode.PERMISSION_NOT_GRANTED,
        context,
        None,
        None,
        None,
        True,
    )
