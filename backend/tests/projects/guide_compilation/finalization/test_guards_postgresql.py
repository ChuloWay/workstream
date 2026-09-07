"""Direct SQL probes distinguish database custody from service-side validation."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.projects.guide_compilation.finalization_payloads import (
    compose_facts,
    new_row,
    require_source_shape,
)
from app.modules.projects.guide_compilation.repository import GuideCompilationRepository
from ..helpers import seed_database
from .pg_support import DatabaseAuthorization, database_case, finalize, stored_state


async def pending_receipt(session, values, command):
    """Produce valid authority/receipt inputs without running finalization persistence."""
    from app.modules.authorization.api import (
        ProjectSetupFinalizationLocator,
        setup_finalization_identity,
    )

    repo = GuideCompilationRepository(session)
    attempt = await repo.finalization_attempt_id(command)
    view = await repo.lock_finalization(command, attempt)
    facts = compose_facts(view, require_source_shape(view))
    authority = DatabaseAuthorization(session, values)
    _, operation, _ = setup_finalization_identity(
        command.setup_run_id, command.setup_generation, command.compilation_id
    )
    async with authority.prepare_setup_finalization(
        ProjectSetupFinalizationLocator(project_id=command.project_id, operation_id=operation)
    ) as handle:
        receipt = await handle.consume_new(facts)
    return new_row(facts, receipt), view.setup


async def sql_transition(session, command, row, *, extra="", changes=None):
    """Execute the complete transition with independently selectable malformed fields."""
    values = dict(
        status=row.setup_outcome,
        current_step="guide_sufficiency"
        if row.setup_outcome == "sufficiency_blocked"
        else "submission_artifact_policy_derivation",
        output_sufficiency_report_id=row.sufficiency_report_id,
        output_submission_artifact_policy_id=row.artifact_policy_id,
        finished_at=datetime(2000, 1, 1, tzinfo=UTC),
    )
    values.update(changes or {})
    assignments = ",".join(f"{column}=:{column}" for column in values)
    await session.execute(
        text("update project_setup_runs set " + assignments + extra + " where id=:id"),
        {**values, "id": str(command.setup_run_id)},
    )


@pytest.mark.parametrize("project", [False, True])
async def test_direct_setup_finalization_without_receipt_is_rejected(
    clean_postgres_database, project
):
    async with database_case(clean_postgres_database, project=project) as (_, factory, command):
        before = await stored_state(factory, command)
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                await session.execute(
                    text(
                        "update project_setup_runs set status='sufficiency_blocked',"
                        "current_step='guide_sufficiency',finished_at=transaction_timestamp() where id=:id"
                    ),
                    {"id": str(command.setup_run_id)},
                )
        assert await stored_state(factory, command) == before


async def test_direct_finalization_receipt_without_setup_transition_is_rejected(
    clean_postgres_database,
):
    async with database_case(clean_postgres_database) as (values, factory, command):
        before = await stored_state(factory, command)
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                row, _ = await pending_receipt(session, values, command)
                session.add(row)
                await session.flush()
                # Prove insertion succeeded, so failure belongs to the deferred pair guard.
                assert row.created_at is not None
        assert await stored_state(factory, command) == before


@pytest.mark.parametrize(
    "extra",
    [
        ",updated_at=transaction_timestamp()+interval '1 day'",
        ",created_by='forged'",
        ",error_code='forged'",
    ],
)
async def test_direct_finalization_with_extra_setup_field_mutation_is_rejected(
    clean_postgres_database, extra
):
    async with database_case(clean_postgres_database) as (values, factory, command):
        before = await stored_state(factory, command)
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                row, _ = await pending_receipt(session, values, command)
                session.add(row)
                await session.flush()
                await sql_transition(session, command, row, extra=extra)
        assert await stored_state(factory, command) == before


@pytest.mark.parametrize(
    "field",
    ["output_sufficiency_report_id", "output_submission_artifact_policy_id", "current_step"],
)
async def test_direct_partial_setup_finalization_is_rejected(clean_postgres_database, field):
    async with database_case(clean_postgres_database) as (values, factory, command):
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                row, _ = await pending_receipt(session, values, command)
                session.add(row)
                await session.flush()
                await sql_transition(session, command, row, changes={field: None})


async def test_finalization_created_at_is_postgresql_owned(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        async with factory() as session, session.begin():
            row, _ = await pending_receipt(session, values, command)
            row.created_at = datetime(2000, 1, 1, tzinfo=UTC)
            session.add(row)
            await session.flush()
            await session.refresh(row)
            tx = await session.scalar(text("select transaction_timestamp()"))
            assert row.created_at == tx
            await sql_transition(session, command, row)


async def test_finalization_finished_at_is_postgresql_owned(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        async with factory() as session, session.begin():
            row, _ = await pending_receipt(session, values, command)
            session.add(row)
            await session.flush()
            await sql_transition(session, command, row)
            actual = await session.scalar(
                text("select finished_at from project_setup_runs where id=:id"),
                {"id": str(command.setup_run_id)},
            )
            assert actual == await session.scalar(text("select transaction_timestamp()"))


@pytest.mark.parametrize(
    "statement",
    [
        "update project_guide_setup_finalizations set setup_outcome=setup_outcome",
        "delete from project_guide_setup_finalizations",
        "truncate project_guide_setup_finalizations",
        "update project_setup_runs set updated_at=updated_at",
        "delete from project_setup_runs",
        "truncate project_setup_runs cascade",
    ],
)
async def test_finalized_setup_cannot_be_rewritten(clean_postgres_database, statement):
    async with database_case(clean_postgres_database) as (values, factory, command):
        await finalize(factory, values, command)
        before = await stored_state(factory, command)
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                await session.execute(text(statement))
        assert await stored_state(factory, command) == before


@pytest.mark.parametrize(
    "field",
    [
        "compilation_id",
        "sufficiency_operation_id",
        "sufficiency_report_id",
        "artifact_policy_operation_id",
        "artifact_policy_id",
        "actor_profile_id",
        "identity_link_id",
        "source_state_digest",
        "result_hash",
        "facts_digest",
        "authority_resource_digest",
    ],
)
async def test_receipt_compilation_attempt_setup_tuple_must_match(clean_postgres_database, field):
    async with database_case(clean_postgres_database) as (values, factory, command):
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                row, _ = await pending_receipt(session, values, command)
                original = getattr(row, field)
                value = "sha256:" + "f" * 64 if field.endswith(("hash", "digest")) else uuid4()
                if isinstance(original, str) and not field.endswith(("hash", "digest")):
                    value = str(value)
                setattr(row, field, value)
                session.add(row)
                await session.flush()


@pytest.mark.parametrize("classification", ["guide_blocked", "draft_ready"])
async def test_nullable_finalization_custody_cannot_bypass_guards(
    clean_postgres_database, classification
):
    async with database_case(clean_postgres_database, classification=classification) as (
        values,
        factory,
        command,
    ):
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                row, _ = await pending_receipt(session, values, command)
                row.artifact_policy_operation_id = (
                    uuid4() if classification == "guide_blocked" else None
                )
                session.add(row)
                await session.flush()


async def test_legacy_setup_transition_needs_no_finalization_receipt(clean_postgres_database):
    values = await seed_database(clean_postgres_database)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            await session.execute(
                text(
                    "update project_setup_runs set status='sufficiency_blocked',current_step='guide_sufficiency',"
                    "finished_at=transaction_timestamp() where id=:id"
                ),
                {"id": str(values["setup_1"])},
            )
        async with factory() as session:
            assert (
                await session.scalar(
                    text("select status from project_setup_runs where id=:id"),
                    {"id": str(values["setup_1"])},
                )
                == "sufficiency_blocked"
            )
    finally:
        await engine.dispose()
