"""Actual kernel reachability/audit projection; PostgreSQL custody is separate proof."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.authorization.contribution_read import ContributionReadAuthorization
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.schemas import AdminRole
from app.modules.contributions.api.records import ContributionReadDenied, ContributionReadRequest
from tests.authorization.test_contribution_read_scope import Grants, principal


class Audit:
    def __init__(self):
        self.events = []

    async def add_authority_event(self, event):
        self.events.append(event)


@pytest.mark.parametrize("audience", ["self", "project"])
async def test_kernel_reaches_read_evaluator_and_stages_exact_query_evidence(audience):
    context = principal()
    grants = Grants(context, role=AdminRole.PROJECT_MANAGER)
    grants.scope = grants.project_id
    async with AsyncSession() as session:
        kernel = AuthorizationService(session, context, admin_repository=grants)
        kernel._audit = Audit()
        selected = ContributionReadRequest(audience=audience, actor_profile_id=context.actor_profile_id,
                                           project_id=grants.project_id if audience == "project" else None)
        await ContributionReadAuthorization(kernel).authorize(selected)
    event, = kernel._audit.events
    assert str(event.action_id) == f"contribution.read_{audience}"
    assert event.permission_id == event.action_id
    assert event.after_facts["allowed"] is True
    assert event.after_facts["resource_context_digest"].startswith("sha256:")
    assert event.resource_type == ("project" if audience == "project" else "actor_profile")
    assert event.resource_id == str(grants.project_id if audience == "project" else context.actor_profile_id)
    if audience == "project":
        assert event.project_id == str(grants.project_id)
        assert event.target_ref_kind == "project" and event.target_ref_id == str(grants.project_id)
        assert event.matched_grant_id == str(grants.grant_id)
    else:
        assert event.project_id is event.matched_grant_id is None


async def test_kernel_denial_for_system_only_finance_has_no_project_target_facts():
    context = principal()
    grants = Grants(context, role=AdminRole.FINANCE_AUTHORITY, scope="system")
    async with AsyncSession() as session:
        kernel = AuthorizationService(session, context, admin_repository=grants)
        kernel._audit = Audit()
        with pytest.raises(ContributionReadDenied):
            await ContributionReadAuthorization(kernel).authorize(ContributionReadRequest(
                audience="project", actor_profile_id=context.actor_profile_id, project_id=grants.project_id,
            ))
    event, = kernel._audit.events
    assert event.after_facts["allowed"] is False
    assert event.after_facts["resource_context_digest"].startswith("sha256:")
    assert event.project_id is event.resource_type is event.resource_id is None
    assert event.target_ref_kind is event.target_ref_id is event.matched_grant_id is None
