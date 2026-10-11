"""Closed evaluator scope proof; PostgreSQL authority custody remains separate."""

from types import SimpleNamespace

import pytest

from app.core.identifiers import new_record_id
from app.modules.authorization.catalogue import ACTION_BY_ID, ActionId
from app.modules.authorization.domain.audit import AuthorizationDenialCode, MatchedAuthorityKind
from app.modules.authorization.domain.contribution_reads import (
    ContributionProjectReadResourceContext, ContributionSelfReadResourceContext,
    contribution_read_denial,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.runtime import (
    ActorKind, ActorStatus, HumanAuthorizationContext, IdentityLinkStatus,
)
from app.modules.authorization.schemas import AdminRole


def principal():
    return HumanAuthorizationContext(
        actor_profile_id=new_record_id(), actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE, identity_link_id=new_record_id(),
        identity_link_status=IdentityLinkStatus.ACTIVE, request_id=new_record_id(),
        correlation_id=new_record_id(),
    )


class Grants:
    def __init__(self, context, *, role=None, scope=None, suspended=False):
        self.context, self.role, self.scope = context, role, scope
        self.grant_id, self.project_id = new_record_id(), new_record_id()
        self.calls = []
        self.suspended = suspended

    async def lock_request_actor(self, link_id, actor_id):
        assert (link_id, actor_id) == (self.context.identity_link_id, self.context.actor_profile_id)
        self.calls.append("actor")
        return (
            SimpleNamespace(id=str(link_id), actor_profile_id=str(actor_id), status="active"),
            SimpleNamespace(id=str(actor_id), actor_kind="human",
                            status="suspended" if self.suspended else "active"),
        )

    async def find_effective_grant(self, actor_id, permission, **filters):
        assert actor_id == self.context.actor_profile_id
        assert filters["for_update"] is True
        self.calls.append((filters["allowed_roles"], filters.get("exact_project_scope", False)))
        if self.role not in filters["allowed_roles"]:
            return None
        selected = filters["scope_project_id"]
        if self.scope == selected or self.scope == "system" and not filters.get("exact_project_scope", False):
            return SimpleNamespace(id=str(self.grant_id))
        return None

    async def lock_project(self, project_id):
        assert project_id == self.project_id
        self.calls.append("project")
        return SimpleNamespace(id=str(project_id), status="archived")


async def evaluate(repository, *, own=False, resource=None):
    context = repository.context
    action = ActionId.CONTRIBUTION_READ_SELF if own else ActionId.CONTRIBUTION_READ_PROJECT
    if resource is None:
        args = dict(resource_id=context.actor_profile_id if own else repository.project_id,
                    actor_profile_id=context.actor_profile_id, request_digest="sha256:" + "a" * 64)
        resource = (ContributionSelfReadResourceContext(**args) if own else
                    ContributionProjectReadResourceContext(scope_project_id=repository.project_id, **args))
    return await contribution_read_denial(
        ACTION_BY_ID[action], resource, context, repository,
        AuthorizationService._locked_human_context, AuthorizationService._lifecycle_denial,
    )


@pytest.mark.parametrize("role,scope,allowed", [
    (AdminRole.PROJECT_MANAGER, "system", True),
    (AdminRole.PROJECT_MANAGER, "project", True),
    (AdminRole.FINANCE_AUTHORITY, "project", True),
    (AdminRole.FINANCE_AUTHORITY, "system", False),
    (AdminRole.FINANCE_AUTHORITY, "foreign", False),
    (AdminRole.PROJECT_MANAGER, "foreign", False),
    (AdminRole.OPERATOR, "system", False),
    (AdminRole.AUDIT_AUTHORITY, "project", False),
])
async def test_pm_coverage_and_exact_project_finance_are_distinct(role, scope, allowed):
    repository = Grants(principal(), role=role)
    repository.scope = repository.project_id if scope == "project" else scope
    result = await evaluate(repository)
    assert (result[0] is None) is allowed
    assert repository.calls[0] == "actor"
    if allowed:
        assert result[2:5] == (MatchedAuthorityKind.ADMIN_ROLE_GRANT, repository.grant_id,
                              repository.project_id)
        assert repository.calls[-1] == "project"
    else:
        assert result[0] is AuthorizationDenialCode.PERMISSION_NOT_GRANTED
        assert "project" not in repository.calls
    if role is not AdminRole.PROJECT_MANAGER or not allowed:
        assert repository.calls[-1 if not allowed else -2] == (
            frozenset({AdminRole.FINANCE_AUTHORITY}), True,
        )


async def test_self_read_needs_live_actor_but_no_contributor_grant():
    repository = Grants(principal())
    result = await evaluate(repository, own=True)
    assert result[0] is None and result[2:5] == (MatchedAuthorityKind.ACTOR_SELF, None, None)
    assert repository.calls == ["actor"]
    repository.suspended = True
    result = await evaluate(repository, own=True)
    assert result[0] is AuthorizationDenialCode.ACTOR_SUSPENDED


async def test_foreign_actor_or_copied_scope_is_refused_before_authority_queries():
    repository = Grants(principal())
    resource = ContributionProjectReadResourceContext(
        resource_id=repository.project_id, scope_project_id=repository.project_id,
        actor_profile_id=repository.context.actor_profile_id, request_digest="sha256:" + "a" * 64,
    )
    for changed in ({"actor_profile_id": new_record_id()}, {"scope_project_id": new_record_id()}):
        result = await evaluate(repository, resource=resource.model_copy(update=changed))
        assert result[0] is AuthorizationDenialCode.RESOURCE_GUARD_DENIED
    assert repository.calls == []
