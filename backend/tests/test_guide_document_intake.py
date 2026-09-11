"""One public guide create owns its complete immutable document declaration."""

from uuid import uuid4
from types import SimpleNamespace
import os
import hashlib
import pytest

from sqlalchemy import select

from app.db import session as db_session
from app.modules.projects.models import (
    GuideMutationIdempotencyRecord,
    GuideSourceSnapshot,
    ProjectSetupRun,
)
from projects.client_fixtures import (
    auth_headers,
    project_client as project_client,
    project_database_env as _project_database_env,
)
from projects.guide_fixtures import create_project

base_project_database_env = _project_database_env


@pytest.fixture
def project_database_env(base_project_database_env, monkeypatch, tmp_path):
    from app.core.config import get_settings

    values = {
        "ARTIFACT_STORE_BACKEND": "s3_compatible",
        "ARTIFACT_S3_PROVIDER_PROFILE": "minio",
        "ARTIFACT_S3_REGION": "us-east-1",
        "ARTIFACT_S3_BUCKET": "workstream-artifacts",
        "ARTIFACT_S3_ENDPOINT_URL": os.environ.get(
            "WORKSTREAM_TEST_MINIO_ENDPOINT", "http://localhost:9000"
        ),
        "ARTIFACT_S3_PRIVATE_PREFIX": f"guide-intake/{uuid4().hex}",
        "ARTIFACT_S3_ADDRESSING_STYLE": "path",
        "ARTIFACT_S3_CREDENTIAL_MODE": "local_static",
        "ARTIFACT_S3_ACCESS_KEY_ID": "workstream-minio",
        "ARTIFACT_S3_SECRET_ACCESS_KEY": "workstream-minio-secret-key",
        "ARTIFACT_SCRATCH_ROOT": str(tmp_path / "scratch"),
        "CELERY_TASK_ALWAYS_EAGER": "false",
    }
    for scope in ("TASK", "PRODUCER", "PROJECT", "DEPLOYMENT"):
        values[f"ARTIFACT_ADMISSION_{scope}_MAXIMUM_BYTES"] = str(1024 * 1024)
    for name, value in values.items():
        monkeypatch.setenv("WORKSTREAM_" + name, value)
    get_settings.cache_clear()
    yield base_project_database_env
    get_settings.cache_clear()


async def test_create_declares_document_set_and_replays_exact_ids(project_client):
    project = await create_project(project_client)
    path = f"/api/v1/projects/{project['id']}/guides"
    payload = {
        "version": "initial",
        "task_examples": [{"content": "Review a claim using the guide."}],
        "documents": [
            {"label": "z-guide.pdf", "media_type": "application/pdf"},
            {"label": "a-appendix.pdf", "media_type": "application/pdf"},
        ],
    }
    headers = auth_headers() | {"Idempotency-Key": str(uuid4())}
    created = await project_client.post(path, headers=headers, json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert [item["label"] for item in body["documents"]] == ["z-guide.pdf", "a-appendix.pdf"]
    assert [item["order"] for item in body["documents"]] == [0, 1]
    assert body["setup"]["status"] == "awaiting_documents"
    assert "source_snapshot_id" not in body
    replay = await project_client.post(path, headers=headers, json=payload)
    assert replay.status_code == 201, replay.text
    assert replay.json() == body
    conflict = await project_client.post(
        path, headers=headers, json=payload | {"documents": payload["documents"][::-1]}
    )
    assert conflict.status_code == 409, conflict.text
    async with db_session.get_session_factory()() as session:
        snapshots = (
            await session.scalars(
                select(GuideSourceSnapshot).where(GuideSourceSnapshot.guide_id == body["id"])
            )
        ).all()
        setups = (
            await session.scalars(
                select(ProjectSetupRun).where(ProjectSetupRun.guide_id == body["id"])
            )
        ).all()
        mutations = (
            await session.scalars(
                select(GuideMutationIdempotencyRecord).where(
                    GuideMutationIdempotencyRecord.project_id == project["id"]
                )
            )
        ).all()
        assert len(snapshots) == len(setups) == 1
        assert {row.action_id for row in mutations} == {
            "project.guide.create",
            "project.guide_source_snapshot.create",
        }
        assert len(mutations) == 2
        assert all(row.status == "committed" for row in mutations)
        assert len({row.idempotency_key for row in mutations}) == 1
        assert setups[0].source_snapshot_id == snapshots[0].id


@pytest.mark.parametrize(
    "invalid", ["content_type", "project", "guide", "document", "key", "declared_size"]
)
async def test_upload_rejects_invalid_request_before_reading_body(project_client, invalid):
    project = await create_project(project_client)
    created = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json={
            "version": "initial",
            "task_examples": [{"content": "Review a claim."}],
            "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}],
        },
    )
    assert created.status_code == 201, created.text
    guide = created.json()
    read = False

    async def body():
        nonlocal read
        read = True
        raise AssertionError("invalid upload must not read the request body")
        yield b""

    selectors = {
        "project": project["id"],
        "guide": guide["id"],
        "document": guide["documents"][0]["document_id"],
    }
    headers = auth_headers() | {"Content-Type": "application/pdf"}
    if invalid in selectors:
        selectors[invalid] = str(uuid4())
    elif invalid == "content_type":
        headers["Content-Type"] = "text/plain"
    elif invalid == "key":
        headers["Idempotency-Key"] = "invalid-key"
    else:
        headers["Content-Length"] = str(1024 * 1024 * 1024)
    response = await project_client.post(
        f"/api/v1/projects/{selectors['project']}/guides/{selectors['guide']}/documents/{selectors['document']}/content",
        headers=headers,
        content=body(),
    )
    assert response.status_code == {"key": 422, "declared_size": 413}.get(invalid, 404), (
        response.text
    )
    assert read is False


@pytest.mark.parametrize("recover_callback", [False, True])
async def test_all_documents_stored_dispatches_once_through_minio(
    project_client, monkeypatch, recover_callback
):
    from app.core.config import get_settings
    from app.modules.actors.service_identities import ServiceIdentity
    from app.modules.artifacts.models import ArtifactReplica, ArtifactPutAttempt
    from app.workers.project_setup import run_project_guide_compilation
    from app.adapters.artifacts import internal_workers
    from tests.test_s3_artifact_store import provision_minio_bucket, initialize_minio_store

    await provision_minio_bucket.__wrapped__()
    deliveries = []

    def publish(*, args, task_id):
        deliveries.append((args, task_id))
        return SimpleNamespace(id=task_id)

    monkeypatch.setattr(run_project_guide_compilation, "apply_async", publish)
    provision = await project_client.post(
        "/api/v1/service-actors",
        headers=auth_headers(),
        json={
            "service_identity": ServiceIdentity.ARTIFACT_PUT_RESOLVER.value,
            "subject": "guide-intake-test-put-resolver",
            "reason": "Isolated guide upload proof.",
        },
    )
    assert provision.status_code == 201, provision.text
    project = await create_project(project_client)
    created = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json={
            "version": "initial",
            "task_examples": [{"content": "Review a claim."}],
            "documents": [
                {"label": name, "media_type": "application/pdf"}
                for name in ("guide.pdf", "appendix.pdf")
            ],
        },
    )
    assert created.status_code == 201, created.text
    guide = created.json()
    originals = [b"%PDF-1.7\nGuide fixture\n%%EOF", b"%PDF-1.7\nAppendix fixture\n%%EOF"]
    for index, (document, original) in enumerate(zip(guide["documents"], originals, strict=True)):
        path = f"/api/v1/projects/{project['id']}/guides/{guide['id']}/documents/{document['document_id']}/content"
        headers = auth_headers() | {"Content-Type": "application/pdf"}
        real_callback = internal_workers.continue_guide_setup_after_stored_document
        if index == 1 and recover_callback:

            async def unavailable_callback(_attempt_id):
                raise RuntimeError("injected callback failure")

            monkeypatch.setattr(
                internal_workers, "continue_guide_setup_after_stored_document", unavailable_callback
            )
        response = await project_client.post(path, headers=headers, content=original)
        if index == 1 and recover_callback:
            assert deliveries == []
            monkeypatch.setattr(
                internal_workers, "continue_guide_setup_after_stored_document", real_callback
            )

            async def recover(attempt_id):
                from uuid import UUID

                await real_callback(UUID(attempt_id))

            assert await internal_workers.scan_guide_setup_continuations(recover) == 1
            assert await internal_workers.scan_guide_setup_continuations(recover) == 0
        assert response.status_code == 202, response.text
        assert response.json()["sha256"] == "sha256:" + hashlib.sha256(original).hexdigest()
        assert set(response.json()) == {"document_id", "sha256", "byte_count", "status", "replayed"}
        assert len(deliveries) == index
        replay = await project_client.post(path, headers=headers, content=original)
        assert replay.status_code == 202, replay.text
        assert replay.json()["replayed"] is True
        assert len(deliveries) == index
        async with db_session.get_session_factory()() as session:
            run = await session.get(ProjectSetupRun, guide["setup"]["id"])
            assert run.status == ("awaiting_documents" if index == 0 else "queued")
    async with db_session.get_session_factory()() as session:
        attempts = (
            await session.scalars(
                select(ArtifactPutAttempt).where(ArtifactPutAttempt.project_id == project["id"])
            )
        ).all()
        replicas = (await session.scalars(select(ArtifactReplica))).all()
        assert len(attempts) == len(replicas) == 2
    store = initialize_minio_store(private_prefix=get_settings().artifact_s3_private_prefix)
    try:
        stored = [
            b"".join([chunk async for chunk in store.open(row.provider_object_ref)])
            for row in replicas
        ]
        assert set(stored) == set(originals)
    finally:
        store.close()


async def test_create_replay_requires_current_manager_authority(project_client):
    from datetime import datetime, UTC
    from app.modules.authorization.models import AdminRoleGrant

    project = await create_project(project_client)
    path = f"/api/v1/projects/{project['id']}/guides"
    payload = {
        "version": "initial",
        "task_examples": [{"content": "Review a claim."}],
        "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}],
    }
    headers = auth_headers()
    first = await project_client.post(path, headers=headers, json=payload)
    assert first.status_code == 201, first.text
    async with db_session.get_session_factory()() as session:
        grants = (
            await session.scalars(
                select(AdminRoleGrant).where(
                    AdminRoleGrant.role == "project_manager",
                    AdminRoleGrant.status == "active",
                )
            )
        ).all()
        assert grants
        for grant in grants:
            grant.status = "revoked"
            grant.version += 1
            grant.revoked_by_actor_profile_id = grant.target_actor_profile_id
            grant.revoked_by_admin_role_grant_id = grant.granted_by_admin_role_grant_id
            grant.revoked_reason = "Current-authority replay proof"
            grant.revoked_at = datetime.now(UTC)
        await session.commit()
    replay = await project_client.post(path, headers=headers, json=payload)
    assert replay.status_code == 403, replay.text
    assert "permission_not_granted" in replay.text
    async with db_session.get_session_factory()() as session:
        rows = (
            await session.scalars(
                select(GuideMutationIdempotencyRecord).where(
                    GuideMutationIdempotencyRecord.project_id == project["id"],
                )
            )
        ).all()
        assert len(rows) == 2
        assert all(row.status == "committed" for row in rows)


async def test_late_create_failure_rolls_back_both_authorities_and_all_product_rows(
    project_client, monkeypatch
):
    from sqlalchemy import func
    from app.modules.projects.repository import ProjectRepository
    from app.modules.projects.models import ProjectGuide, GuideSourceSnapshotItem
    from app.modules.tasks.models import AuditEvent

    project = await create_project(project_client)
    async with db_session.get_session_factory()() as session:
        before = await session.scalar(select(func.count()).select_from(AuditEvent))

    async def fail_setup(self, setup_run):
        raise RuntimeError("injected late setup write failure")

    monkeypatch.setattr(ProjectRepository, "add_project_setup_run", fail_setup)
    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers(),
        json={
            "version": "initial",
            "task_examples": [{"content": "Review a claim."}],
            "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}],
        },
    )
    assert response.status_code == 500, response.text
    async with db_session.get_session_factory()() as session:
        for model in (
            ProjectGuide,
            GuideSourceSnapshot,
            GuideSourceSnapshotItem,
            ProjectSetupRun,
            GuideMutationIdempotencyRecord,
        ):
            assert await session.scalar(select(func.count()).select_from(model)) == 0
        assert await session.scalar(select(func.count()).select_from(AuditEvent)) == before


async def test_concurrent_create_replays_one_paired_operation(project_client):
    import asyncio

    project = await create_project(project_client)
    payload = {
        "version": "initial",
        "task_examples": [{"content": "Review a claim."}],
        "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}],
    }
    path = f"/api/v1/projects/{project['id']}/guides"
    headers = auth_headers()
    results = await asyncio.gather(
        *(project_client.post(path, headers=headers, json=payload) for _ in range(2))
    )
    assert [result.status_code for result in results] == [201, 201], [
        result.text for result in results
    ]
    assert results[0].json() == results[1].json()


@pytest.mark.parametrize("guard_enabled", [True, False])
async def test_database_rejects_individually_valid_but_cross_key_creation_pair(
    project_client, monkeypatch, guard_enabled
):
    """Both decisions and rows are valid; only their shared replay key is wrong."""
    from app.modules.projects.guide_mutation_repository import GuideMutationRepository
    from sqlalchemy import func
    from app.modules.projects.models import ProjectGuide

    project = await create_project(project_client)
    original = GuideMutationRepository.reserve

    async def cross_key(self, **values):
        if values["action_id"] == "project.guide_source_snapshot.create":
            values["idempotency_key"] = uuid4()
        return await original(self, **values)

    monkeypatch.setattr(GuideMutationRepository, "reserve", cross_key)
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.exc import IntegrityError

    errors = []
    original_commit = AsyncSession.commit

    async def observe_commit(self):
        try:
            return await original_commit(self)
        except IntegrityError as error:
            errors.append(str(error.orig))
            raise

    monkeypatch.setattr(AsyncSession, "commit", observe_commit)
    guarded_tables = (
        "project_guides",
        "guide_source_snapshots",
        "guide_mutation_idempotency_records",
    )
    try:
        if not guard_enabled:
            async with db_session.get_session_factory()() as session, session.begin():
                for table in guarded_tables:
                    await session.execute(
                        text(f"alter table {table} disable trigger require_document_creation_pair")
                    )
        response = await project_client.post(
            f"/api/v1/projects/{project['id']}/guides",
            headers=auth_headers(),
            json={
                "version": "cross-key",
                "task_examples": [{"content": "Review a claim."}],
                "documents": [{"label": "guide.pdf", "media_type": "application/pdf"}],
            },
        )
        if guard_enabled:
            assert response.status_code == 503, response.text
            assert len(errors) == 1
            assert "guide document creation pair is invalid" in errors[0]
        else:
            # Discriminating mutation: all unchanged authority/lineage guards pass.
            assert response.status_code == 201, response.text
            assert errors == []
        async with db_session.get_session_factory()() as session:
            for model, count in (
                (ProjectGuide, 1),
                (GuideSourceSnapshot, 1),
                (ProjectSetupRun, 1),
                (GuideMutationIdempotencyRecord, 2),
            ):
                assert await session.scalar(select(func.count()).select_from(model)) == (
                    0 if guard_enabled else count
                )
    finally:
        if not guard_enabled:
            async with db_session.get_session_factory()() as session, session.begin():
                for table in guarded_tables:
                    await session.execute(
                        text(f"alter table {table} enable trigger require_document_creation_pair")
                    )
