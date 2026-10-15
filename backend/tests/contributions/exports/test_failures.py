"""Serialization and explicit refusal roll back staged read ALLOW evidence."""

import pytest
from sqlalchemy import text

from app.api.deps import contribution_exports
from app.modules.contributions.api.records import ContributionExportTooLarge
from app.modules.contributions.records.read_repository import ContributionReadRepository
from tests.contributions.records.support import (
    authorized_submitter_source, reviewer_contribution_source, insert_record, rows,
)
from .support import source_actor, export_audits, export_path, prepared_reviewer_sibling


async def test_failed_first_page_rolls_back_snapshot_and_allow_then_retry_commits_once(
    tmp_path, auth_database_env, admin_access, monkeypatch,
):
    """A serialization error and a 40001 after allocation cannot leak a slot."""
    async with reviewer_contribution_source(tmp_path, auth_database_env) as h:
        async with h.factory() as session, session.begin():
            await insert_record(session, h.reviewer_record)
        sibling = await prepared_reviewer_sibling(h)
        async with h.factory() as session, session.begin():
            await insert_record(session, sibling)
        project = h.reviewer_record.project_id
        reader = await admin_access.signed.actor("snapshot-rollback-reader")
        await admin_access.signed.grant(admin_access.admin, reader,
                                       role="project_manager", project_id=project)
        path = export_path(project)

        async def snapshot_count():
            async with h.factory() as session:
                return await session.scalar(text(
                    "SELECT count(*) FROM public.contribution_export_snapshots"
                ))

        with monkeypatch.context() as patch:
            def fail_csv(projection):
                assert len(projection.items) == 1 and projection.next_cursor
                raise TypeError("controlled CSV failure after snapshot allocation")

            patch.setattr(contribution_exports, "contribution_export_csv", fail_csv)
            failed = await admin_access.signed.client.get(
                path, params={"format": "csv", "limit": 1}, headers=reader.headers,
            )
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "contribution_export_unavailable"
        assert await snapshot_count() == 0
        assert await export_audits(h.factory) == []

        original = ContributionReadRepository._load_records
        attempts = []

        async def refuse_once(repository, selected, ids):
            attempts.append(tuple(ids))
            if len(attempts) == 1:
                await repository._session.execute(text(
                    "DO $$ BEGIN RAISE EXCEPTION 'controlled snapshot refusal' "
                    "USING ERRCODE = '40001'; END $$"
                ))
            return await original(repository, selected, ids)

        with monkeypatch.context() as patch:
            patch.setattr(ContributionReadRepository, "_load_records", refuse_once)
            accepted = await admin_access.signed.client.get(
                path, params={"limit": 1}, headers=reader.headers,
            )
        assert accepted.status_code == 200 and accepted.json()["next_cursor"], accepted.text
        assert len(attempts) == 2 and attempts[0] == attempts[1]
        assert await snapshot_count() == 1
        evidence = await export_audits(h.factory)
        assert len(evidence) == 1 and evidence[0]["after_facts"]["allowed"] is True


async def test_csv_serialization_failure_commits_neither_allow_nor_partial_body(
    tmp_path, auth_database_env, signed_access, live_acceptance_lifecycle, monkeypatch,
):
    async with authorized_submitter_source(tmp_path, auth_database_env, paid=True) as h:
        actor = await source_actor(signed_access, h)
        async with h.factory() as session:
            before = {table: await rows(session, table) for table in
                      ("contribution_records", "compensation_awards", "final_acceptances")}
        serialized = []
        def failed_serialization(projection):
            assert projection.items[0].contribution_id == h.submitter_record.id
            serialized.append(projection.items[0].contribution_id)
            raise TypeError("deliberate serialization failure")
        monkeypatch.setattr(contribution_exports, "contribution_export_csv", failed_serialization)
        response = await signed_access.client.get("/api/v1/actors/me/contributions?format=csv", headers=actor.headers)
        assert response.status_code == 503 and response.headers["content-type"].startswith("application/json")
        assert serialized == [h.submitter_record.id]
        assert await export_audits(h.factory) == []
        async with h.factory() as session:
            assert {table: await rows(session, table) for table in before} == before


async def test_over_limit_refusal_rolls_back_allow_and_never_starts_serialization(
    tmp_path, auth_database_env, signed_access, live_acceptance_lifecycle, monkeypatch,
):
    async with authorized_submitter_source(tmp_path, auth_database_env) as h:
        actor = await source_actor(signed_access, h)
        async def refuse(repository, selected):
            raise ContributionExportTooLarge("deliberate owner refusal")
        def forbidden_serialization(projection):
            pytest.fail("refused selection started serialization")
        monkeypatch.setattr(ContributionReadRepository, "read", refuse)
        monkeypatch.setattr(contribution_exports, "contribution_export_csv", forbidden_serialization)
        response = await signed_access.client.get("/api/v1/actors/me/contributions?format=csv", headers=actor.headers)
        assert response.status_code == 422 and response.json()["error"]["code"] == "contribution_export_too_large"
        assert await export_audits(h.factory) == []


@pytest.mark.parametrize("code,failures,expected,calls", [
    ("40001", 1, 200, 2),
    ("40001", 2, 503, 2),
    ("23514", 1, 503, 1),
    ("40P01", 1, 503, 1),
])
async def test_driver_error_retry_is_bounded_and_preserves_one_fresh_decision(
    tmp_path, auth_database_env, signed_access, live_acceptance_lifecycle, monkeypatch,
    code, failures, expected, calls,
):
    """Server-raised codes prove retry classification, not an actual deadlock."""
    async with authorized_submitter_source(tmp_path, auth_database_env) as h:
        actor = await source_actor(signed_access, h)
        original = ContributionReadRepository.read
        attempts = []

        async def controlled_driver_failure(repository, selected):
            attempts.append(selected)
            if len(attempts) <= failures:
                # AUTH already staged ALLOW in this attempt's actual root.
                # Each fixed SQLSTATE comes from PostgreSQL.
                await repository._session.execute(text(
                    "DO $$ BEGIN RAISE EXCEPTION 'controlled export refusal' "
                    "USING ERRCODE = '" + code + "'; END $$"
                ))
            return await original(repository, selected)

        monkeypatch.setattr(ContributionReadRepository, "read", controlled_driver_failure)
        response = await signed_access.client.get(
            "/api/v1/actors/me/contributions", headers=actor.headers,
        )
        assert response.status_code == expected, response.text
        assert len(attempts) == calls
        assert all(selected == attempts[0] for selected in attempts)
        evidence = await export_audits(h.factory)
        assert len(evidence) == int(expected == 200)
        if expected == 200:
            assert response.json()["items"][0]["contribution_id"] == str(h.submitter_record.id)
            assert evidence[0]["after_facts"]["allowed"] is True
        else:
            assert response.json()["error"]["code"] == "contribution_export_unavailable"
