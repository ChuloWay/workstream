"""Automatic request proof using real authorized source mutations and ART material."""

from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.modules.actors.models import ActorProfile, ActorIdentityLink
from app.modules.artifacts.guide_sufficiency_material import SqlAlchemyGuideSufficiencyMaterialAdapter
from app.modules.authorization.api import ActorIdentityFacts, ActorKind, AuthorizationDenied
from app.modules.checkers.catalogue import build_pre_submission_checker_catalogue, project_guide_pre_submission_capabilities
from app.modules.projects.guide_compilation.automatic_request import AutomaticCompilationInputs
from app.modules.projects.models import ProjectSetupRun
from app.modules.projects.post_submit_policy import project_guide_post_submission_capabilities

from tests.projects.client_fixtures import project_client, project_database_env  # noqa: F401
from tests.projects.guide_fixtures import create_project, create_guide, create_source_snapshot, complete_guide_payload
from tests.verified_guide_fixtures import create_verified_material_fixture
from .test_authorized_execution_service import _execution_service


@pytest.fixture
async def automatic_source(project_client, project_database_env, monkeypatch):  # noqa: F811
    monkeypatch.setenv("WORKSTREAM_PROJECT_SETUP_PIPELINE_AUTOSTART", "true")
    get_settings.cache_clear()
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    snapshot = await create_source_snapshot(project_client, project["id"], guide["id"])
    engine = create_async_engine(project_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        setup = await session.scalar(select(ProjectSetupRun).where(ProjectSetupRun.source_snapshot_id == snapshot["id"]))
        profile = await session.scalar(select(ActorProfile).where(ActorProfile.service_identity == "workstream.project.setup"))
        link = await session.scalar(select(ActorIdentityLink).where(ActorIdentityLink.actor_profile_id == profile.id))
        actor = ActorIdentityFacts(UUID(profile.id), UUID(link.id), ActorKind.SERVICE, "workstream.project.setup")
        setup_id = UUID(setup.id)
    try:
        yield factory, actor, setup_id, snapshot
    finally:
        await engine.dispose()


def automatic_service(session, actor):
    inputs = AutomaticCompilationInputs(
        SqlAlchemyGuideSufficiencyMaterialAdapter(session),
        project_guide_pre_submission_capabilities(build_pre_submission_checker_catalogue()),
        project_guide_post_submission_capabilities(),
    )
    return _execution_service(session, actor, automatic_inputs=inputs)


@pytest.mark.asyncio
async def test_automatic_source_requires_material_then_persists_one_request_and_replays(automatic_source):
    factory, actor, setup_id, snapshot = automatic_source
    from app.interfaces.artifact_operations import GuideSufficiencyMaterialUnavailable
    async with factory() as session:
        with pytest.raises(GuideSufficiencyMaterialUnavailable):
            await automatic_service(session, actor).request_automatic(actor=actor, setup_run_id=setup_id)
    await create_verified_material_fixture(snapshot["id"])
    async with factory() as session:
        first = await automatic_service(session, actor).request_automatic(actor=actor, setup_run_id=setup_id)
        replay = await automatic_service(session, actor).request_automatic(actor=actor, setup_run_id=setup_id)
        assert first == replay
        row = (await session.execute(text("select request_trigger,source_mutation_operation_id,source_authorization_decision_event_id from project_guide_compilation_request_operations"))).one()
        assert row.request_trigger == "automatic_source_ready"
        assert row.source_mutation_operation_id is not None and row.source_authorization_decision_event_id is not None
        assert await session.scalar(text("select count(*) from project_guide_compilation_attempts")) == 1
        assert await session.scalar(text("select count(*) from audit_events where action_id='project.guide_compilation.request_automatic'")) == 1


@pytest.mark.asyncio
async def test_revoked_service_cannot_recover_automatic_request(automatic_source):
    factory, actor, setup_id, snapshot = automatic_source
    await create_verified_material_fixture(snapshot["id"])
    async with factory() as session:
        await automatic_service(session, actor).request_automatic(actor=actor, setup_run_id=setup_id)
    async with factory() as session, session.begin():
        await session.execute(text("update actor_identity_links set status='revoked',revoked_by='test',revoked_at=now(),revoked_reason='test revocation' where id=:id"), {"id":str(actor.identity_link_id)})
    async with factory() as session:
        with pytest.raises(AuthorizationDenied):
            await automatic_service(session, actor).request_automatic(actor=actor, setup_run_id=setup_id)
        assert await session.scalar(text("select count(*) from audit_events where action_id='project.guide_compilation.request_automatic'")) == 1


@pytest.mark.asyncio
async def test_concurrent_automatic_callbacks_share_one_attempt(automatic_source):
    import asyncio
    factory, actor, setup_id, snapshot = automatic_source
    await create_verified_material_fixture(snapshot["id"])
    async def request():
        async with factory() as session:
            return await automatic_service(session, actor).request_automatic(actor=actor, setup_run_id=setup_id)
    first, second = await asyncio.gather(request(), request())
    assert first == second
    async with factory() as session:
        assert await session.scalar(text("select count(*) from project_guide_compilation_attempts")) == 1
        assert await session.scalar(text("select count(*) from project_guide_compilation_request_operations")) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("column", ["source_mutation_operation_id", "source_authorization_decision_event_id"])
async def test_direct_insert_rejects_forged_source_origin(automatic_source, column):
    from uuid import uuid4
    from sqlalchemy.exc import IntegrityError
    from app.modules.projects.guide_compilation.models import ProjectGuideCompilationRequestOperation
    factory, actor, setup_id, snapshot = automatic_source
    await create_verified_material_fixture(snapshot["id"])
    async with factory() as session:
        await automatic_service(session, actor).request_automatic(actor=actor, setup_run_id=setup_id)
        row = await session.scalar(select(ProjectGuideCompilationRequestOperation))
        values = {c.name: getattr(row,c.name) for c in row.__table__.columns}
        await session.rollback()
        forged = {**values,column:uuid4() if column.endswith("operation_id") else str(uuid4())}
        with pytest.raises(IntegrityError, match="automatic compilation origin lineage is invalid"):
            async with session.begin():
                await session.execute(ProjectGuideCompilationRequestOperation.__table__.insert().values(**forged))
        # The exact persisted tuple clears the origin guard and reaches uniqueness.
        with pytest.raises(IntegrityError, match="duplicate key value"):
            async with session.begin():
                await session.execute(ProjectGuideCompilationRequestOperation.__table__.insert().values(**values))


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["project_id", "guide_id", "source_snapshot_id", "setup_run_id", "setup_generation"])
async def test_sql_origin_rejects_each_foreign_lineage_selector(automatic_source, field):
    from dataclasses import replace
    from uuid import uuid4
    from app.modules.projects.guide_compilation.repository import GuideCompilationIntegrityError, GuideCompilationRepository
    factory, actor, setup_id, snapshot = automatic_source
    await create_verified_material_fixture(snapshot["id"])
    async with factory() as session, session.begin():
        facts, _identity, origin = await automatic_service(session,actor)._automatic_inputs.resolve(session,setup_id)
    async with factory() as session:
        changed = replace(facts, **{field: facts.setup_generation + 1 if field == "setup_generation" else uuid4()})
        with pytest.raises(GuideCompilationIntegrityError, match="origin unavailable"):
            async with session.begin():
                await GuideCompilationRepository(session).require_automatic_request_origin(changed,origin)
        async with session.begin():
            await GuideCompilationRepository(session).require_automatic_request_origin(facts,origin)
        assert await session.scalar(text("select count(*) from project_guide_compilation_request_operations")) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value,error", [
    ("request_trigger", "project_manager", "request trigger is invalid"),
    ("actor_profile_id", "00000000-0000-0000-0000-000000000001", "audit event is invalid"),
    ("request_facts_digest", "sha256:" + "0"*64, "facts digest is invalid"),
    ("identity_link_id", "00000000-0000-0000-0000-000000000001", "service authority is invalid"),
])
async def test_direct_automatic_insert_requires_exact_authority_and_content(automatic_source, field, value, error):
    from sqlalchemy.exc import IntegrityError
    from app.modules.projects.guide_compilation.models import ProjectGuideCompilationRequestOperation
    factory, actor, setup_id, snapshot = automatic_source
    await create_verified_material_fixture(snapshot["id"])
    async with factory() as session:
        await automatic_service(session,actor).request_automatic(actor=actor,setup_run_id=setup_id)
        row = await session.scalar(select(ProjectGuideCompilationRequestOperation))
        values = {c.name:getattr(row,c.name) for c in row.__table__.columns}
        await session.rollback()
        with pytest.raises(IntegrityError, match=error):
            async with session.begin():
                await session.execute(ProjectGuideCompilationRequestOperation.__table__.insert().values(**{**values,field:value}))
        with pytest.raises(IntegrityError, match="duplicate key value"):
            async with session.begin():
                await session.execute(ProjectGuideCompilationRequestOperation.__table__.insert().values(**values))


@pytest.mark.asyncio
async def test_original_manager_revocation_does_not_rewrite_source_consent(automatic_source):
    factory, actor, setup_id, snapshot = automatic_source
    await create_verified_material_fixture(snapshot["id"])
    async with factory() as session, session.begin():
        setup = await session.get(ProjectSetupRun,str(setup_id))
        await session.execute(text("update actor_identity_links set status='revoked',revoked_by='test',revoked_at=now(),revoked_reason='test revocation' where id=:id"), {"id":setup.authorized_via_identity_link_id})
    async with factory() as session:
        receipt = await automatic_service(session,actor).request_automatic(actor=actor,setup_run_id=setup_id)
        assert receipt.classification == "compilation_reserved"
        row = (await session.execute(text("select actor_profile_id,source_authorization_decision_event_id from project_guide_compilation_request_operations"))).one()
        assert row.actor_profile_id == str(actor.actor_profile_id)
        assert row.source_authorization_decision_event_id == setup.authorization_decision_event_id


@pytest.mark.asyncio
@pytest.mark.postgres_schema_contract
async def test_retained_automatic_evidence_prevents_origin_downgrade(automatic_source, migration_lock):
    import asyncio
    from alembic import command
    from alembic.config import Config
    factory, actor, setup_id, snapshot = automatic_source
    await create_verified_material_fixture(snapshot["id"])
    async with factory() as session:
        await automatic_service(session,actor).request_automatic(actor=actor,setup_run_id=setup_id)
    def downgrade():
        with migration_lock():
            command.downgrade(Config("alembic.ini"), "0012_contribution_policy_audit_resource")
    with pytest.raises(RuntimeError, match="automatic compilation evidence prevents downgrade"):
        await asyncio.to_thread(downgrade)
    async with factory() as session:
        assert await session.scalar(text("select version_num from alembic_version")) == "0013_compilation_request_origin"
        assert await session.scalar(text("select count(*) from project_guide_compilation_request_operations")) == 1
