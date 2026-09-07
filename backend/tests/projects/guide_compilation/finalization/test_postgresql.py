"""Real finalization persistence, atomic rollback, replay, and resource isolation."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.modules.authorization.api import AuthorizationDenied, setup_finalization_facts_digest
from app.modules.projects.api import ProjectGuideSetupFinalizationError
from app.modules.projects.guide_compilation.finalization import GuideCompilationFinalizationService
from .pg_support import DatabaseAuthorization, database_case, finalize, stored_state


@pytest.mark.parametrize(
    "classification", ["guide_blocked", "draft_ready", "draft_ready_with_warnings"]
)
async def test_finalization_changes_only_allowed_setup_columns(
    clean_postgres_database, classification
):
    async with database_case(clean_postgres_database, classification=classification) as (
        values,
        factory,
        command,
    ):
        before, _, _ = await stored_state(factory, command)
        result = await finalize(factory, values, command)
        after, receipt, count = await stored_state(factory, command)
        changed = {key for key in before if before[key] != after[key]}
        expected = {"status", "current_step", "output_sufficiency_report_id", "finished_at"}
        if classification != "guide_blocked":
            expected.add("output_submission_artifact_policy_id")
        assert changed == expected
        assert after["updated_at"] == before["updated_at"]
        assert result.result_classification == classification
        assert receipt["id"] == result.finalization_id
        assert count == 1


async def test_exact_replay_returns_stored_receipt_without_new_evidence(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        first = await finalize(factory, values, command)
        before = await stored_state(factory, command)
        events = []
        second = await finalize(factory, values, command, events=events)
        assert first == second
        assert await stored_state(factory, command) == before
        assert events == ["prepare", "replay", "close"]


async def test_receipt_created_at_equals_setup_finished_at(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        await finalize(factory, values, command)
        setup, receipt, _ = await stored_state(factory, command)
        assert setup["finished_at"] == receipt["created_at"]
        assert receipt["created_at"] is not None


async def test_late_database_failure_rolls_back_finalization_setup_and_authorization(
    clean_postgres_database,
):
    async with database_case(clean_postgres_database) as (values, factory, command):
        before = await stored_state(factory, command)
        with pytest.raises(DBAPIError):
            async with factory() as session, session.begin():
                authority = DatabaseAuthorization(session, values)
                await GuideCompilationFinalizationService(session, authority).finalize(command)
                await session.execute(text("select 1/0"))
        assert await stored_state(factory, command) == before
        assert authority.events == ["prepare", "consume", "close"]


async def test_closed_authority_is_unusable_after_late_rollback(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        async with factory() as session:
            async with session.begin():
                authority = DatabaseAuthorization(session, values)
                await GuideCompilationFinalizationService(session, authority).finalize(command)
                await session.rollback()
            async with session.begin():
                with pytest.raises(AuthorizationDenied, match="invalid prepared binding"):
                    await authority.handles[0].consume_new(authority.last_facts)
        assert (await stored_state(factory, command))[1:] == (None, 0)


async def test_finalization_never_commits_caller_transaction(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        async with factory() as session:
            async with session.begin():
                await GuideCompilationFinalizationService(
                    session, DatabaseAuthorization(session, values)
                ).finalize(command)
                # Another independent connection cannot see uncommitted receipt or evidence.
                assert (await stored_state(factory, command))[1:] == (None, 0)
                await session.rollback()
        assert (await stored_state(factory, command))[1:] == (None, 0)


@pytest.mark.parametrize("foreign_project", [True, False])
async def test_cross_project_finalization_is_concealed(clean_postgres_database, foreign_project):
    async with database_case(clean_postgres_database) as (values, factory, command):
        project, guide = uuid4(), uuid4()
        async with factory() as session, session.begin():
            await session.execute(text("alter table projects disable trigger user"))
            await session.execute(
                text(
                    "insert into projects(id,name,slug,status) values(:id,'Foreign',:slug,'draft')"
                ),
                {"id": str(project), "slug": str(project)},
            )
            await session.execute(text("alter table projects enable trigger user"))
            await session.execute(text("alter table project_guides disable trigger user"))
            await session.execute(
                text(
                    "insert into project_guides(id,project_id,version,status,content_markdown,created_by) "
                    "values(:id,:project,'foreign-v1','draft','Foreign guide','test')"
                ),
                {
                    "id": str(guide),
                    "project": str(project if foreign_project else command.project_id),
                },
            )
            await session.execute(text("alter table project_guides enable trigger user"))
        forged = command.model_copy(
            update={
                "project_id": project if foreign_project else command.project_id,
                "guide_id": guide,
            }
        )
        before = await stored_state(factory, command)
        with pytest.raises(ProjectGuideSetupFinalizationError, match="^source_state_unavailable$"):
            await finalize(factory, values, forged)
        assert await stored_state(factory, command) == before


async def test_finalization_digest_matches_postgresql(clean_postgres_database):
    async with database_case(clean_postgres_database) as (values, factory, command):
        async with factory() as session, session.begin():
            authority = DatabaseAuthorization(session, values)
            await GuideCompilationFinalizationService(session, authority).finalize(command)
            digest = await session.scalar(
                text(
                    "select project_guide_finalization_digest(r) from project_guide_setup_finalizations r"
                )
            )
            assert digest == setup_finalization_facts_digest(authority.last_facts)


async def test_finalization_audit_resource_vocabulary_matches_database(clean_postgres_database):
    from app.modules.audit.schemas import _RESOURCE_TYPES
    from app.modules.authorization.domain.audit import CONTEXT_DIGEST_RESOURCE_TYPES

    resource = "project_guide_setup_finalization"
    assert resource in _RESOURCE_TYPES and resource in CONTEXT_DIGEST_RESOURCE_TYPES
    async with database_case(clean_postgres_database) as (_, factory, _):
        async with factory() as session:
            definition = await session.scalar(
                text(
                    "select pg_get_constraintdef(oid) from pg_constraint "
                    "where conrelid='audit_events'::regclass and conname='ck_audit_events_authority_privacy_bounds'"
                )
            )
        assert resource in definition
