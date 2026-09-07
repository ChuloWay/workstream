"""Public principal/key rejection and schema validation before mutation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
import pytest

from app.core.config import Settings
from app.main import create_app
from app.api.deps.authorization import get_authorization_actor
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import (
    SubmissionArtifactPolicyCreate,
    SubmissionArtifactPolicyUpdate,
)
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.submission_policy_mutations import rows
from projects.submission_policy_fixtures import project_submission_artifact_policy_body


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
