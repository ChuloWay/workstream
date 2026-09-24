"""Public principal/key rejection, concurrency, and schema validation."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
import pytest
from sqlalchemy import func, select, text

from app.core.config import Settings
from app.db import session as db_session
from app.main import create_app
from app.api.deps.authorization import get_authorization_actor
from app.modules.authorization.catalogue import ActionId
from app.modules.projects.models import (
    SubmissionArtifactPolicy,
    SubmissionPolicyMutationIdempotencyRecord,
)
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import (
    SubmissionArtifactPolicyCreate,
    SubmissionArtifactPolicyUpdate,
)
from app.modules.projects.submission_policy_mutation_service import (
    SubmissionPolicyMutationService,
)
from projects.client_fixtures import (
    auth_headers,
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
    project_database_env as project_database_env,  # noqa: F401
    project_client as project_client_fixture,  # noqa: F401
)
from projects.guide_fixtures import (
    complete_guide_payload,
    create_guide,
    create_project,
    read_guide_source_snapshot,
)
from projects.submission_policy_mutations import rows
from projects.submission_policy_fixtures import (
    create_submission_artifact_policy,
    create_sufficiency_report,
    project_submission_artifact_policy_body,
)
from committed_guide_fixtures import create_compiled_report_fixture


def request(command):
    path = f"/api/v1/projects/{rows.PROJECT}/guides/{rows.GUIDE}/submission-artifact-policies"
    if command == "post":
        return path, {
            "source_snapshot_id": str(rows.SNAPSHOT),
            "policy_version": "manual-v1",
            "policy_body": project_submission_artifact_policy_body(),
        }
    return path + f"/{rows.POLICY}", {
        "expected_policy_hash": rows.predecessor().policy_hash,
        "successor_policy_version": "manual-v2",
    }


async def assert_single_policy_effect(project, guide, action, key, expected_rows, command):
    async with db_session.get_session_factory()() as session:
        policies = list(
            (
                await session.scalars(
                    select(SubmissionArtifactPolicy).where(
                        SubmissionArtifactPolicy.project_id == project["id"],
                        SubmissionArtifactPolicy.guide_id == guide["id"],
                    )
                )
            ).all()
        )
        replay_count = await session.scalar(
            select(func.count())
            .select_from(SubmissionPolicyMutationIdempotencyRecord)
            .where(
                SubmissionPolicyMutationIdempotencyRecord.project_id == project["id"],
                SubmissionPolicyMutationIdempotencyRecord.action_id == action,
                SubmissionPolicyMutationIdempotencyRecord.idempotency_key == key,
                SubmissionPolicyMutationIdempotencyRecord.status == "committed",
            )
        )
        pending_count = await session.scalar(
            select(func.count())
            .select_from(SubmissionPolicyMutationIdempotencyRecord)
            .where(
                SubmissionPolicyMutationIdempotencyRecord.project_id == project["id"],
                SubmissionPolicyMutationIdempotencyRecord.action_id == action,
                SubmissionPolicyMutationIdempotencyRecord.status == "pending",
            )
        )
    assert len(policies) == expected_rows
    assert replay_count == 1
    assert pending_count == 0
    assert all(UUID(policy.id).version == 7 for policy in policies)
    if command == "update":
        assert sum(policy.lifecycle_status == "superseded" for policy in policies) == 1
        assert sum(policy.supersedes_policy_id is not None for policy in policies) == 1


@pytest.mark.parametrize("command", ["create", "update"])
async def test_same_actor_key_concurrent_requests_converge_with_current_authority(
    project_client_fixture: AsyncClient,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    """Independent request sessions retain one exact effect and replay receipt."""
    project = await create_project(project_client_fixture)
    guide = await create_guide(project_client_fixture, project["id"], complete_guide_payload())
    snapshot = await read_guide_source_snapshot(project["id"], guide["id"])
    report = await create_sufficiency_report(
        project_client_fixture, project["id"], guide["id"], snapshot["id"]
    )
    await create_compiled_report_fixture(report["id"], snapshot["id"])
    path = f"/api/v1/projects/{project['id']}/guides/{guide['id']}/submission-artifact-policies"
    expected_rows = 1
    if command == "create":
        method = "post"
        payload = {
            "source_snapshot_id": snapshot["id"],
            "policy_version": "manual-concurrent-v1",
            "policy_body": project_submission_artifact_policy_body(),
            "change_summary": "Concurrent exact creation.",
        }
        action = ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_CREATE.value
    else:
        predecessor = await create_submission_artifact_policy(
            project_client_fixture, project["id"], guide["id"], snapshot["id"]
        )
        method = "patch"
        path += f"/{predecessor['id']}"
        payload = {
            "expected_policy_hash": predecessor["policy_hash"],
            "successor_policy_version": "manual-concurrent-v2",
            "change_summary": "Concurrent exact replacement.",
        }
        action = ActionId.PROJECT_SUBMISSION_ARTIFACT_POLICY_UPDATE.value
        expected_rows = 2
    original_prepare = SubmissionPolicyMutationService._prepare
    first_pair_ready = asyncio.Event()
    preparations: list[tuple[int, int, UUID, UUID]] = []

    async def synchronized_prepare(self, prepared, action_id, caller, project_id, resource):
        backend_pid = await self._session.scalar(text("SELECT pg_backend_pid()"))
        candidate_policy_id = resource.successor_policy_id or resource.policy_id
        preparations.append(
            (
                id(self._session),
                backend_pid,
                resource.operation_id,
                candidate_policy_id,
            )
        )
        if len(preparations) <= 2:
            if len(preparations) == 2:
                first_pair_ready.set()
            await asyncio.wait_for(first_pair_ready.wait(), timeout=10)
        return await original_prepare(self, prepared, action_id, caller, project_id, resource)

    monkeypatch.setattr(SubmissionPolicyMutationService, "_prepare", synchronized_prepare)
    key = str(uuid4())
    headers = auth_headers() | {"Idempotency-Key": key}

    first, second = await asyncio.gather(
        project_client_fixture.request(method, path, headers=headers, json=payload),
        project_client_fixture.request(method, path, headers=headers, json=payload),
    )

    expected_status = 201 if command == "create" else 200
    assert first.status_code == second.status_code == expected_status, (first.text, second.text)
    assert first.json() == second.json()
    assert len(preparations) == 3
    assert len({value[0] for value in preparations[:2]}) == 2
    assert len({value[1] for value in preparations[:2]}) == 2
    assert len({value[2] for value in preparations[:2]}) == 2
    assert len({value[3] for value in preparations[:2]}) == 2
    assert all(value.version == 7 for entry in preparations for value in entry[2:])
    assert preparations[2][2:] in {entry[2:] for entry in preparations[:2]}
    assert UUID(first.json()["id"]) in {entry[3] for entry in preparations[:2]}
    await assert_single_policy_effect(project, guide, action, key, expected_rows, command)


@pytest.mark.parametrize("command", ["post", "patch"])
async def test_public_mutation_conceals_service_before_owner_lookup(monkeypatch, command):
    app = create_app(Settings(environment="test"))

    async def service_actor():
        return SimpleNamespace(profile=SimpleNamespace(actor_kind="service"))

    lookup = AsyncMock(side_effect=AssertionError("service reached product lookup"))
    app.dependency_overrides[get_authorization_actor] = service_actor
    monkeypatch.setattr(ProjectRepository, "get_project", lookup)
    path, payload = request(command)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.request(
            command, path, json=payload, headers={"Idempotency-Key": str(rows.KEY)}
        )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "project_authorization_resource_not_found"
    lookup.assert_not_awaited()


@pytest.mark.parametrize("command", ["post", "patch"])
@pytest.mark.parametrize("key", [None, "not-a-uuid"])
async def test_invalid_key_precedes_actor_resolution(command, key):
    app = create_app(Settings(environment="test"))
    calls = []

    async def forbidden_actor():
        calls.append("actor")
        raise AssertionError("invalid key reached actor resolution")

    app.dependency_overrides[get_authorization_actor] = forbidden_actor
    path, payload = request(command)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.request(
            command, path, json=payload, headers={} if key is None else {"Idempotency-Key": key}
        )
    assert response.status_code == 422
    assert calls == []


def test_create_schema_rejects_malformed_snapshot():
    _, payload = request("post")
    payload["source_snapshot_id"] = "not-a-uuid"
    with pytest.raises(ValidationError):
        SubmissionArtifactPolicyCreate.model_validate(payload)


def test_create_schema_rejects_empty_policy_version():
    _, payload = request("post")
    payload["policy_version"] = ""
    with pytest.raises(ValidationError):
        SubmissionArtifactPolicyCreate.model_validate(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"successor_policy_version": "v2"},
        {"expected_policy_hash": "not-a-digest", "successor_policy_version": "v2"},
        {"expected_policy_hash": "sha256:" + "0" * 64},
        {"expected_policy_hash": "sha256:" + "0" * 64, "successor_policy_version": ""},
    ],
)
def test_update_schema_rejects_invalid_precondition(payload):
    with pytest.raises(ValidationError):
        SubmissionArtifactPolicyUpdate.model_validate(payload)
