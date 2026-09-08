"""PostgreSQL proof of all five operations through production AUTH composition."""

from dataclasses import replace

import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.modules.contributions.api import ContributionPolicyConflict, ContributionPolicyUnavailable
from app.modules.tasks.models import AuditEvent
from .postgresql_support import world, snapshot


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ("system", "project"))
@pytest.mark.parametrize("compensated", (False, True))
async def test_each_policy_action_executes_with_exact_finance_scope_and_audit(
    admin_access, scope, compensated
):
    target = await world(admin_access, scope)
    prior = None
    for operation in ("create_draft", "update_draft", "publish", "retire"):
        request = target.request(operation, prior, compensated=compensated)
        prior = await target.execute(operation, request)
        assert prior.actor_profile_id == target.context.actor_profile_id
        assert prior == await target.execute(operation, request)
        view = await target.execute("read", target.request("read", prior))
        assert view.contribution_policy_version_id == prior.contribution_policy_version_id
    async with db_session.get_session_factory()() as session:
        events = (
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.project_id == str(target.project),
                    AuditEvent.action_id.like("contribution.policy.%"),
                )
            )
        ).all()
    assert {e.action_id for e in events} == {
        "contribution.policy." + op
        for op in ("read", "create_draft", "update_draft", "publish", "retire")
    }
    for event in events:
        assert event.matched_grant_id == target.grant
        assert event.actor_id == str(target.context.actor_profile_id)
        assert event.actor_ref_kind == "actor_profile"
        assert event.request_id == str(target.context.request_id)
        assert event.correlation_id == str(target.context.correlation_id)
        assert event.denial_code is None
        assert event.resource_type == "contribution_policy"
        assert event.resource_id == str(prior.contribution_policy_id)
        assert event.after_facts["allowed"] is True
        assert event.after_facts["resource_context_digest"].startswith("sha256:")


@pytest.mark.asyncio
async def test_policy_revoked_grant_denies_fresh_mutation_and_exact_replay(admin_access):
    target = await world(admin_access)
    request = target.request("create_draft")
    result = await target.execute("create_draft", request)
    response = await admin_access.signed.revoke(admin_access.admin, target.grant)
    assert response.status_code == 200, response.text
    before = await snapshot(target.project)
    with pytest.raises(ContributionPolicyConflict):
        await target.execute("create_draft", request)
    with pytest.raises((ContributionPolicyConflict, ContributionPolicyUnavailable)):
        await target.execute("update_draft", target.request("update_draft", result))
    assert await snapshot(target.project) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("create_draft", "update_draft", "publish", "retire"))
async def test_policy_failure_rolls_back_product_and_authority_evidence(admin_access, operation):
    target = await world(admin_access)
    prior = None
    for setup in ("create_draft", "update_draft", "publish"):
        if setup == operation:
            break
        prior = await target.execute(setup, target.request(setup, prior))
    request = target.request(operation, prior)
    before = await snapshot(target.project)
    with pytest.raises(RuntimeError, match="caller failure after complete policy effect"):
        async with db_session.get_session_factory()() as session, session.begin():
            result = await getattr(target.service(session), operation)(request)
            assert result.operation_id == request.operation_id
            assert await session.scalar(
                select(AuditEvent.id).where(
                    AuditEvent.project_id == str(target.project),
                    AuditEvent.action_id == "contribution.policy." + operation,
                )
            )
            raise RuntimeError("caller failure after complete policy effect")
    assert await snapshot(target.project) == before
    control = await target.execute(operation, request)
    assert control.operation_id == request.operation_id


@pytest.mark.asyncio
async def test_policy_conflicting_replay_cannot_change_committed_effect(admin_access):
    target = await world(admin_access)
    request = target.request("create_draft")
    result = await target.execute("create_draft", request)
    before = await snapshot(target.project)
    with pytest.raises(ContributionPolicyConflict):
        await target.execute("create_draft", replace(request, name="Different policy"))
    assert await snapshot(target.project) == before
    assert await target.execute("create_draft", request) == result
