"""Activation migration preserves prior rows and refuses loss of immutable evidence."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migration_fixtures import (
    run_alembic_revision,
    current_schema_revision,
    run_guarded_revision_downgrade,
)
from app.modules.projects.guide_activation.custody import load_guide_activation
from app.modules.projects.models import ProjectGuide
from .pg_support import activation_case, activation_service

PRIOR = "0022_adapter_binding_audit_resource"
OWN = "0023_guide_activation_custody"


@pytest.mark.postgres_schema_contract
async def test_empty_migration_roundtrip_restores_prior_schema(clean_postgres_database):
    from scripts.schema_baseline_manifest import build_manifest

    # Exact prior owner schema, not just a successful Alembic exit.
    engine = create_async_engine(clean_postgres_database)
    try:
        await run_alembic_revision("downgrade", PRIOR)
        prior = await build_manifest(clean_postgres_database)
        await run_alembic_revision("upgrade", OWN)
        await run_alembic_revision("downgrade", PRIOR)
        assert await build_manifest(clean_postgres_database) == prior
        await run_alembic_revision("upgrade", OWN)
    finally:
        await engine.dispose()


@pytest.mark.postgres_schema_contract
async def test_retained_active_guide_upgrades_without_invented_binding(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (
        factory,
        command,
        actor,
        grant,
        _,
        policy,
    ):
        await run_alembic_revision("downgrade", PRIOR)
        async with factory() as session, session.begin():
            # Construct the actual pre-CP07 retained shape under its old schema.
            await session.execute(
                text("ALTER TABLE project_guides DISABLE TRIGGER guide_mutation_product_custody")
            )
            await session.execute(
                text("ALTER TABLE project_guides DISABLE TRIGGER guide_lineage_lifecycle_guard")
            )
            await session.execute(
                text(
                    "UPDATE project_guides SET status='active',approved_by=:actor,effective_at=now() WHERE id=:id"
                ),
                dict(actor=str(actor.actor_profile_id), id=str(command.target.proposal.guide_id)),
            )
            await session.execute(
                text("ALTER TABLE project_guides ENABLE TRIGGER guide_lineage_lifecycle_guard")
            )
            await session.execute(
                text("ALTER TABLE project_guides ENABLE TRIGGER guide_mutation_product_custody")
            )
            await session.execute(
                text("UPDATE projects SET status='active' WHERE id=:id"),
                dict(id=str(command.target.proposal.project_id)),
            )
        async with factory() as session:
            before = await session.scalar(
                text("SELECT row_to_json(g)::jsonb FROM project_guides g WHERE id=:id"),
                dict(id=str(command.target.proposal.guide_id)),
            )
        await run_alembic_revision("upgrade", OWN)
        async with factory() as session:
            after = await session.scalar(
                text("SELECT row_to_json(g)::jsonb FROM project_guides g WHERE id=:id"),
                dict(id=str(command.target.proposal.guide_id)),
            )
            assert {
                k: v
                for k, v in after.items()
                if k
                not in {
                    "activation_operation_id",
                    "contribution_policy_id",
                    "contribution_policy_version_id",
                }
            } == before
            assert all(
                after[k] is None
                for k in (
                    "activation_operation_id",
                    "contribution_policy_id",
                    "contribution_policy_version_id",
                )
            )
            with pytest.raises(ValueError, match="binding unavailable"):
                await load_guide_activation(
                    session, await session.get(ProjectGuide, str(command.target.proposal.guide_id))
                )

        from tests.projects.guide_compilation.proposals.public_support import proposal_client
        from .test_successor import successor_command

        async with proposal_client(factory, actor) as client:
            response = await client.get(
                f"/api/v1/projects/{command.target.proposal.project_id}/active-guide"
            )
            assert response.status_code == 404
        successor = await successor_command(factory, command, actor, grant, policy)
        successor = successor.model_copy(
            update={
                "expected_previous_active_guide_id": command.target.proposal.guide_id,
                "expected_previous_active_guide_generation": before["mutation_generation"],
            }
        )
        async with factory() as session, session.begin():
            receipt = await activation_service(session, actor, successor, grant).activate(
                successor, actor=actor, request_id=uuid4()
            )
        async with factory() as session:
            retained = await session.get(ProjectGuide, str(command.target.proposal.guide_id))
            assert retained.status == "superseded"
            assert retained.activation_operation_id is None
            assert retained.contribution_policy_id is None
            assert retained.contribution_policy_version_id is None
            assert retained.superseded_at == receipt.effective_at
        async with proposal_client(factory, actor) as client:
            response = await client.get(
                f"/api/v1/projects/{command.target.proposal.project_id}/active-guide"
            )
            assert response.status_code == 200, response.text
            assert response.json()["guide"]["id"] == str(successor.target.proposal.guide_id)


async def test_downgrade_refuses_committed_activation(clean_postgres_database):
    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        async with factory() as session, session.begin():
            receipt = await activation_service(session, actor, command, grant).activate(
                command, actor=actor, request_id=uuid4()
            )
        with pytest.raises(RuntimeError, match="guide activation evidence prevents downgrade"):
            await run_guarded_revision_downgrade(clean_postgres_database, OWN)
        async with factory() as session:
            assert (
                await session.scalar(text("SELECT version_num FROM alembic_version"))
                == current_schema_revision()
            )
            assert (
                await load_guide_activation(
                    session, await session.get(ProjectGuide, str(command.target.proposal.guide_id))
                )
                == receipt
            )


async def test_downgrade_refuses_activation_audit_without_a_binding(clean_postgres_database):
    from app.modules.audit.schemas import AuthorityEventType, ActorReferenceKind
    from app.modules.audit.service import AuditService
    from tests.test_audit import _authority_input

    async with activation_case(clean_postgres_database) as (factory, command, actor, grant, _, _):
        value = _authority_input(
            AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
            actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
            actor_ref=str(actor.actor_profile_id),
            project_id=str(command.target.proposal.project_id),
            resource_type="project_guide_activation",
            resource_id=str(command.target.proposal.guide_id),
            target_ref_kind="project",
            target_ref_id=str(command.target.proposal.project_id),
            action_id="project.guide.activate",
            permission_id="project.guide.manage",
            denial_code="permission_not_granted",
        )
        async with factory() as session, session.begin():
            await AuditService(session).add_authority_event(value)
        async with factory() as session:
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM guide_mutation_idempotency_records WHERE action_id='project.guide.activate'"
                    )
                )
                == 0
            )
        with pytest.raises(RuntimeError, match="guide activation evidence prevents downgrade"):
            await run_guarded_revision_downgrade(clean_postgres_database, OWN)
