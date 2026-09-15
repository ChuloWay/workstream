"""Real activation transaction, exact replay and default-deny controls."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.api.guide_proposals import GuideProposalError
from app.modules.projects.guide_activation.custody import load_guide_activation
from app.modules.projects.models import ProjectGuide
from .pg_support import activation_case, activation_service


async def test_complete_activation_and_exact_replay(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (
        factory,
        command,
        actor,
        grant,
        world,
        policy,
    ):
        async with factory() as session:
            for table in ("payment_policies", "workstream_tasks", "submissions"):
                assert await session.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        async with factory() as session, session.begin():
            receipt = await activation_service(session, actor, command, grant).activate(
                command, actor=actor, request_id=uuid4()
            )
        async with factory() as session, session.begin():
            guide = await session.get(ProjectGuide, str(command.target.proposal.guide_id))
            assert guide.status == "active"
            assert guide.contribution_policy_version_id == command.contribution_policy_version_id
            assert await load_guide_activation(session, guide) == receipt
            assert (
                await session.scalar(
                    text("SELECT status FROM projects WHERE id=:id"), dict(id=guide.project_id)
                )
                == "active"
            )
        async with factory() as session, session.begin():
            replay = await activation_service(session, actor, command, grant).activate(
                command, actor=actor, request_id=uuid4()
            )
            assert replay == receipt
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM guide_mutation_idempotency_records WHERE action_id='project.guide.activate'"
                    )
                )
                == 1
            )
        from tests.projects.guide_compilation.proposals.public_support import proposal_client

        async with proposal_client(factory, actor) as client:
            response = await client.get(
                f"/api/v1/projects/{command.target.proposal.project_id}/active-guide"
            )
            assert response.status_code == 200, response.text
            assert response.json()["guide"]["contribution_policy_version_id"] == str(
                command.contribution_policy_version_id
            )
        async with factory() as session, session.begin():
            await world.service(session).retire(world.request("retire", policy))
        async with proposal_client(factory, actor) as client:
            after_retirement = await client.get(
                f"/api/v1/projects/{command.target.proposal.project_id}/active-guide"
            )
            assert after_retirement.status_code == 200, after_retirement.text
            assert after_retirement.json() == response.json()
        async with factory() as session, session.begin():
            assert (
                await activation_service(session, actor, command, grant).activate(
                    command, actor=actor, request_id=uuid4()
                )
                == receipt
            )


async def test_activation_default_authority_is_unavailable(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        async with factory() as session, session.begin():
            with pytest.raises(GuideProposalError, match="authority_unavailable"):
                await activation_service(session, actor, command, grant, authority=False).activate(
                    command, actor=actor, request_id=uuid4()
                )
        async with factory() as session:
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM guide_mutation_idempotency_records WHERE action_id='project.guide.activate'"
                    )
                )
                == 0
            )
            guide = await session.get(ProjectGuide, str(command.target.proposal.guide_id))
            assert guide.status == "draft" and guide.activation_operation_id is None
