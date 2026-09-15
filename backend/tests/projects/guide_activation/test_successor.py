"""A distinct, fully prepared guide supersedes exactly the selected predecessor."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.api.post_policy import PostPolicyApproval
from app.modules.projects.guide_activation.custody import load_guide_activation
from app.modules.projects.models import ProjectGuide
from tests.projects.guide_compilation.helpers import ids, service_actor
from tests.projects.guide_compilation.proposals.pg_support import (
    seed_selected_review_revision_inputs,
)
from tests.projects.guide_compilation.proposals.public_support import proposal_client
from tests.projects.post_policy.pg_support import prepare_post_policy, operate
from .pg_support import activation_case, activation_command, activation_service
from .source_fixtures import create_compiled_guide


async def successor_command(factory, command, actor, grant, policy):
    values = {**ids(), "project": command.target.proposal.project_id}
    async with factory() as session:
        actor_id, link_id = (
            await session.execute(
                select(ActorProfile.id, ActorIdentityLink.id)
                .join(ActorIdentityLink, ActorIdentityLink.actor_profile_id == ActorProfile.id)
                .where(ActorProfile.service_identity == "workstream.project.setup")
            )
        ).one()
    values.update(actor=UUID(actor_id), link=UUID(link_id))
    values, finalization = await create_compiled_guide(factory, values, actor, version="v2")
    await seed_selected_review_revision_inputs(factory, finalization, actor)
    _, derived = await prepare_post_policy(
        factory, finalization, actor, grant, service_actor(values)
    )
    approved = await operate(
        factory,
        actor,
        values["project"],
        grant,
        "approve",
        PostPolicyApproval(target=derived.target, idempotency_key=uuid4()),
    )
    return await activation_command(factory, approved, policy)


async def test_distinct_guide_supersession_and_historical_replay(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (
        factory,
        first,
        actor,
        grant,
        world,
        policy,
    ):
        async with factory() as session, session.begin():
            receipt = await activation_service(session, actor, first, grant).activate(
                first, actor=actor, request_id=uuid4()
            )
        next_command = await successor_command(factory, first, actor, grant, policy)
        assert next_command.target.proposal.guide_id != first.target.proposal.guide_id
        # A manager cannot accidentally replace a guide they did not explicitly select.
        with pytest.raises(GuideProposalError, match="proposal_stale"):
            async with factory() as session, session.begin():
                await activation_service(session, actor, next_command, grant).activate(
                    next_command, actor=actor, request_id=uuid4()
                )
        next_command = next_command.model_copy(
            update={
                "expected_previous_active_guide_id": first.target.proposal.guide_id,
                "expected_previous_active_guide_generation": receipt.activation_generation,
            }
        )
        async with factory() as session, session.begin():
            successor = await activation_service(session, actor, next_command, grant).activate(
                next_command, actor=actor, request_id=uuid4()
            )
        async with factory() as session:
            old = await session.get(ProjectGuide, str(first.target.proposal.guide_id))
            current = await session.get(ProjectGuide, str(next_command.target.proposal.guide_id))
            assert old.status == "superseded" and current.status == "active"
            assert old.superseded_at == current.effective_at == successor.effective_at
            assert await load_guide_activation(session, old) == receipt
            assert await load_guide_activation(session, current) == successor
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM project_guides WHERE status='active'")
                )
                == 1
            )
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM guide_mutation_idempotency_records WHERE action_id='project.guide.activate'"
                    )
                )
                == 2
            )
        async with proposal_client(factory, actor) as client:
            response = await client.get(
                f"/api/v1/projects/{first.target.proposal.project_id}/active-guide"
            )
            assert response.status_code == 200, response.text
            assert response.json()["guide"]["id"] == str(next_command.target.proposal.guide_id)
        async with factory() as session, session.begin():
            await world.service(session).retire(world.request("retire", policy))
        for command, expected in ((first, receipt), (next_command, successor)):
            async with factory() as session, session.begin():
                assert (
                    await activation_service(session, actor, command, grant).activate(
                        command, actor=actor, request_id=uuid4()
                    )
                    == expected
                )
