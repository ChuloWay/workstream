"""Serialization and explicit refusal roll back staged read ALLOW evidence."""

import pytest

from app.api.deps import contribution_exports
from app.modules.contributions.api.records import ContributionExportTooLarge
from app.modules.contributions.records.read_repository import ContributionReadRepository
from tests.contributions.records.support import authorized_submitter_source, rows
from .support import source_actor, export_audits


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
