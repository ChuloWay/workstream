"""Explicit real AUTH and CP07 composition in the same root transaction."""

from contextlib import asynccontextmanager
from uuid import uuid4

from sqlalchemy import text

from app.adapters.auth import guide_activation_authorization
from app.adapters.checkers import project_guide_approval_compiler
from app.adapters.contributions import contribution_policy_validation_port
from app.adapters.projects import project_guide_activation_port
from app.adapters.projects.contribution_validation import GuideContributionPolicyValidation
from app.modules.authorization.runtime import HumanAuthorizationContext, ActorStatus, IdentityLinkStatus


@asynccontextmanager
async def service(factory, actor):
    async with factory() as session, session.begin():
        request = uuid4()
        context = HumanAuthorizationContext(
            actor_profile_id=actor.actor_profile_id, identity_link_id=actor.identity_link_id,
            actor_kind=actor.actor_kind, actor_status=ActorStatus.ACTIVE,
            identity_link_status=IdentityLinkStatus.ACTIVE, request_id=request, correlation_id=uuid4(),
        )
        planner, pre, post = project_guide_approval_compiler()
        owner = project_guide_activation_port(
            session,
            contribution=GuideContributionPolicyValidation(contribution_policy_validation_port(session)),
            planner=planner, pre_catalogue=pre, post_catalogue=post,
            authorization=guide_activation_authorization(session, context),
        )
        yield session, owner, request, context


async def activate(factory, actor, command):
    async with service(factory, actor) as (_, owner, request, _):
        return await owner.activate(command, actor=actor, request_id=request)


async def activation_state(factory):
    async with factory() as session:
        return {
            "guides": (await session.execute(text(
                "SELECT id,status,activation_operation_id,contribution_policy_version_id,mutation_generation "
                "FROM project_guides ORDER BY id"
            ))).all(),
            "operations": (await session.execute(text(
                "SELECT operation_id,resource_context_digest,activation_authority_json FROM guide_mutation_idempotency_records "
                "WHERE action_id='project.guide.activate' ORDER BY operation_id"
            ))).all(),
            "events": (await session.execute(text(
                "SELECT id,after_facts,matched_grant_id,correlation_id FROM audit_events "
                "WHERE action_id='project.guide.activate' ORDER BY id"
            ))).all(),
        }
