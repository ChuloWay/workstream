"""Public admission-backed intake against real TASK/ART owners and PostgreSQL."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.core.identifiers import new_record_id
from app.api.deps.rate_controls import get_rate_control_service
from app.db.session import get_db_session
from app.main import create_app
from app.modules.artifacts.models import ArtifactPutAttempt, SubmissionBundleAdmission
from app.modules.checkers.models import CheckerRun, SelectedPreSubmitRun
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.models import Submission
from app.modules.tasks.models import WorkstreamTask
from app.modules.api_controls.service import AUTHORIZATION_READ_SCOPE, RateControlService
from app.modules.actors.models import ActorProfile
from tests.tasks.test_submission_lineage import _prepared_packet
from tests.test_artifact_admission import _context, _seed_human_actor
from tests.submission_preparation_auth_helpers import install_submitter_grant
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.post_submit_routing.support import revision_archive
from tests.tasks.submission_lineage_support import _verified_admission
from tests.test_submission_predecessor_custody import (
    _fixture_revision_context, _replacement_request,
)


@asynccontextmanager
async def _client(h, monkeypatch, database_url, *, subject=None):
    """Use a normal development bearer for the seeded exact human identity."""
    actor = getattr(h, "actor_context", None) or h.context
    monkeypatch.setenv("WORKSTREAM_AUTH_PROVIDER", "dev")
    monkeypatch.setenv("WORKSTREAM_ENVIRONMENT", "test")
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", database_url)
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_TOKEN", "public-intake-token")
    subject = subject or f"human-{actor.actor_profile_id}"
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", subject)
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ISSUER", "https://issuer.example.test")
    monkeypatch.setenv(
        "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET",
        "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=",
    )
    monkeypatch.setenv(
        "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET",
        "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA=",
    )
    get_settings.cache_clear()
    settings_values = h.settings.model_dump()
    settings_values.update({
        "auth_provider": "dev",
        "environment": "test",
        "database_url": database_url,
        "dev_auth_token": "public-intake-token",
        "dev_auth_subject": subject,
        "dev_auth_issuer": "https://issuer.example.test",
    })
    settings = Settings(_env_file=None, **settings_values)
    assert settings.api_rate_limit_key_secret is not None
    assert settings.pagination_cursor_hmac_secret is not None
    assert settings.database_url == database_url
    rate_control = RateControlService(h.factory)
    preflight = await rate_control.consume(
        control_scope=AUTHORIZATION_READ_SCOPE,
        issuer="https://issuer.example.test",
        subject=subject,
        limit=settings.api_authorization_read_rate_limit,
        window_seconds=settings.api_authorization_read_rate_window_seconds,
        secret=settings.api_rate_limit_key_secret,
    )
    assert preflight.allowed
    app = create_app(settings)
    assert app.state.auth_configuration_valid

    async def session():
        async with h.factory() as value:
            yield value

    app.dependency_overrides[get_db_session] = session
    app.dependency_overrides[get_rate_control_service] = lambda: rate_control
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver",
            headers={"Authorization": "Bearer public-intake-token"},
        ) as client:
            yield client
    finally:
        get_settings.cache_clear()


def _payload(request, admission_id):
    return {
        "assignment_id": str(request.assignment_id),
        "admission_id": str(admission_id),
        "predecessor_submission_id": (
            str(request.predecessor_submission_id)
            if request.predecessor_submission_id is not None else None
        ),
        "summary": request.summary,
        "contributor_attestation": request.contributor_attestation,
    }


async def test_public_initial_submission_replays_and_recovers_ready_upload(
    isolated_database_env, tmp_path, monkeypatch,
):
    async with _prepared_packet(isolated_database_env, tmp_path) as h:
        route = f"/api/v1/tasks/{h.task_id}/submissions"
        async with _client(h, monkeypatch, isolated_database_env) as client:
            duplicate = await client.post(
                f"/api/v1/tasks/{h.task_id}/submission-bundle-preparations",
                headers=[
                    ("Authorization", "Bearer public-intake-token"),
                    ("Content-Type", "application/zip"),
                    ("X-Task-Assignment-Id", str(h.assignment_id)),
                    ("Idempotency-Key", str(h.preparation_request.idempotency_key)),
                    ("Idempotency-Key", str(h.preparation_request.idempotency_key)),
                ],
                content=h.archive_bytes,
            )
            assert duplicate.status_code == 422, duplicate.text
            assert duplicate.json()["error"]["code"] == "submission_preparation_headers_invalid"

            # Losing a ready response can be recovered with the exact ZIP and key.
            from app.adapters.artifacts.local import LocalStorageAdapter
            from app.modules.artifacts.selected_pre_submit_execution import SelectedPreSubmitExecutionService

            async def no_new_put(*_args, **_kwargs):
                raise AssertionError("ready replay invoked a second provider PUT")

            async def no_new_checker(*_args, **_kwargs):
                raise AssertionError("ready replay invoked selected PRE again")

            with monkeypatch.context() as patch:
                patch.setattr(LocalStorageAdapter, "put", no_new_put)
                patch.setattr(SelectedPreSubmitExecutionService, "execute", no_new_checker)
                prepared = await client.post(
                    f"/api/v1/tasks/{h.task_id}/submission-bundle-preparations",
                    headers={
                        "Content-Type": "application/zip",
                        "X-Task-Assignment-Id": str(h.assignment_id),
                        "Idempotency-Key": str(h.preparation_request.idempotency_key),
                        "X-Submission-Summary": h.preparation_request.summary,
                        "X-Contributor-Attestation": h.preparation_request.contributor_attestation,
                    },
                    content=h.archive_bytes,
                )
            assert prepared.status_code == 202, prepared.text
            assert prepared.json()["submission_bundle_preparation_status"] == "ready"
            assert prepared.json()["admission_id"] == str(h.admission_id)
            assert prepared.json()["replayed"] is True

            foreign_context = _context()
            async with h.factory.begin() as session:
                await _seed_human_actor(session, foreign_context)
                task = await session.get(WorkstreamTask, str(h.task_id))
                await install_submitter_grant(await session.connection(), {
                    "project": task.project_id,
                    "actor": str(foreign_context.actor_profile_id),
                })
            with monkeypatch.context() as foreign_patch:
                async with _client(
                    h, foreign_patch, isolated_database_env,
                    subject=f"human-{foreign_context.actor_profile_id}"
                ) as foreign:
                    denied_actor = await foreign.post(route, json=_payload(h.creation, h.admission_id))
                    assert denied_actor.status_code == 404, denied_actor.text
                    assert denied_actor.json()["error"]["code"] == "submission_unavailable"

            uncaused = _payload(h.creation, h.admission_id)
            uncaused["predecessor_submission_id"] = str(new_record_id())
            denied_predecessor = await client.post(route, json=uncaused)
            assert denied_predecessor.status_code in {404, 409}, denied_predecessor.text

            client_owned = _payload(h.creation, h.admission_id)
            client_owned["package_uri"] = "s3://caller-controlled/bundle.zip"
            denied_uri = await client.post(route, json=client_owned)
            assert denied_uri.status_code == 422, denied_uri.text

            created = await client.post(route, json=_payload(h.creation, h.admission_id))
            assert created.status_code == 201, created.text
            result = created.json()
            assert result["admission_id"] == str(h.admission_id)
            assert result["submission_version"] == 1
            assert result["submission_id"]

            replay = await client.post(route, json=_payload(h.creation, h.admission_id))
            assert replay.status_code == 201, replay.text
            assert replay.json() == result

            changed = _payload(h.creation, h.admission_id)
            changed["summary"] += " changed"
            denied = await client.post(route, json=changed)
            assert denied.status_code in {404, 409}, denied.text

            history = await client.get(f"/api/v1/tasks/{h.task_id}/submissions")
            assert history.status_code == 200, history.text
            assert [item["id"] for item in history.json()["items"]] == [result["submission_id"]]

            async with h.factory.begin() as session:
                profile = await session.get(ActorProfile, str(h.context.actor_profile_id))
                profile.status = "suspended"
                profile.suspended_by = "intake-test"
                profile.suspended_at = datetime.now(UTC)
                profile.suspension_reason = "test suspension"
            revoked = await client.post(route, json=_payload(h.creation, h.admission_id))
            assert revoked.status_code in {403, 404}, revoked.text

        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(Submission)) == 1
            assert await session.scalar(select(func.count()).select_from(CheckerRun)) == 1
            assert await session.scalar(select(func.count()).select_from(OutboxEvent)) >= 1
            assert await session.scalar(select(func.count()).select_from(SelectedPreSubmitRun)) == 1
            assert await session.scalar(select(func.count()).select_from(ArtifactPutAttempt).where(
                ArtifactPutAttempt.producer_request_type == "submission_bundle"
            )) == 1
            admission = await session.get(SubmissionBundleAdmission, str(h.admission_id))
            assert admission.status == "consumed"


async def test_public_checker_remediation_uses_exact_predecessor(
    isolated_database_env, tmp_path, monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        await _fixture_revision_context(h)
        request = _replacement_request(
            h, revision_archive(h.data),
            predecessor_id=h.created.submission_id,
            idempotency_key=new_record_id(),
        )
        admission_id = await _verified_admission(
            h.factory, h.store, h.namespace, h.settings, h.actor_context, request,
        )
        route = f"/api/v1/tasks/{request.task_id}/submissions"
        async with _client(h, monkeypatch, isolated_database_env) as client:
            wrong = _payload(request, admission_id)
            wrong["predecessor_submission_id"] = str(new_record_id())
            denied = await client.post(route, json=wrong)
            assert denied.status_code in {404, 409}, denied.text

            created = await client.post(route, json=_payload(request, admission_id))
            assert created.status_code == 201, created.text
            result = created.json()
            assert result["submission_version"] == 2

            replay = await client.post(route, json=_payload(request, admission_id))
            assert replay.status_code == 201 and replay.json() == result

        async with h.factory() as session:
            successor = await session.get(Submission, result["submission_id"])
            assert successor.supersedes_submission_id == str(h.created.submission_id)
            assert successor.submission_bundle_admission_id == str(admission_id)
