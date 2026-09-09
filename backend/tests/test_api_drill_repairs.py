"""PostgreSQL regressions for the bounded external API drill repairs."""

from uuid import uuid4

from httpx import AsyncClient
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db import session as db_session
from app.main import create_app
from app.modules.audit.schemas import ActorReferenceKind, AuthorityAuditEventInput, AuthorityEventType
from app.modules.authorization.catalogue import PermissionId
from app.modules.authorization.models import ProjectRoleGrant
from app.modules.projects.models import (
    GuideMutationIdempotencyRecord,
    Project,
    ProjectCreateIdempotencyRecord,
    ProjectGuide,
)
from projects.client_fixtures import (
    auth_headers,
    project_client as project_client,
    project_database_env as project_database_env,
)
from projects.guide_fixtures import complete_guide_payload, create_guide, create_project


def test_api_drill_request_limits_are_exposed_in_openapi() -> None:
    schemas = create_app().openapi()["components"]["schemas"]

    assert schemas["ProjectRole"]["enum"] == ["submitter", "reviewer"]
    project = schemas["ProjectCreate"]["properties"]
    guide_create = schemas["ProjectGuideCreate"]["properties"]
    guide_update_schema = schemas["ProjectGuideUpdate"]
    guide_update = guide_update_schema["properties"]

    assert project["name"]["maxLength"] == 200
    assert project["slug"]["maxLength"] == 120
    assert guide_create["version"]["maxLength"] == 50
    assert "content_markdown" not in guide_update_schema.get("required", [])
    assert guide_update["content_markdown"]["type"] == "string"
    assert "anyOf" not in guide_update["content_markdown"]
    assert "default" not in guide_update["content_markdown"]
    assert {item.get("type") for item in guide_update["change_summary"]["anyOf"]} == {
        "null",
        "string",
    }


async def test_exact_unicode_project_and_guide_limits_persist_unchanged(
    project_client: AsyncClient,
) -> None:
    project_payload = {
        "name": "界" * 200,
        "slug": "ø" * 120,
        "description": "Exact character-limit proof",
    }
    project_response = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json=project_payload,
    )
    assert project_response.status_code == 201, project_response.text
    assert project_response.json()["name"] == project_payload["name"]
    assert project_response.json()["slug"] == project_payload["slug"]

    version = "版" * 50
    guide_response = await project_client.post(
        f"/api/v1/projects/{project_response.json()['id']}/guides",
        headers=auth_headers(),
        json=complete_guide_payload(version),
    )
    assert guide_response.status_code == 201, guide_response.text
    assert guide_response.json()["version"] == version

    async with db_session.get_session_factory()() as session:
        persisted_project = await session.get(Project, project_response.json()["id"])
        persisted_guide = await session.get(ProjectGuide, guide_response.json()["id"])
        assert persisted_project is not None
        assert persisted_guide is not None
        assert persisted_project.name == project_payload["name"]
        assert persisted_project.slug == project_payload["slug"]
        assert persisted_guide.version == version


@pytest.mark.parametrize(("field", "limit"), [("name", 200), ("slug", 120)])
async def test_project_overflow_has_no_state_and_same_key_recovers(
    project_client: AsyncClient,
    field: str,
    limit: int,
) -> None:
    key = uuid4()
    payload = {
        "name": "Overflow candidate",
        "slug": f"overflow-{uuid4()}",
    }
    payload[field] = "x" * (limit + 1)
    rejected = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(key)},
        json=payload,
    )
    assert rejected.status_code == 422, rejected.text

    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(Project)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectCreateIdempotencyRecord)
                .where(ProjectCreateIdempotencyRecord.idempotency_key == key)
            )
            == 0
        )

    recovered_payload = {
        "name": "Recovered project",
        "slug": f"recovered-{uuid4()}",
    }
    recovered = await project_client.post(
        "/api/v1/projects",
        headers=auth_headers() | {"Idempotency-Key": str(key)},
        json=recovered_payload,
    )
    assert recovered.status_code == 201, recovered.text
    assert recovered.json()[field] == recovered_payload[field]


async def test_guide_version_overflow_has_no_state_and_same_key_recovers(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client, name="Guide version recovery")
    key = uuid4()
    rejected = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers() | {"Idempotency-Key": str(key)},
        json=complete_guide_payload("v" * 51),
    )
    assert rejected.status_code == 422, rejected.text

    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectGuide)
                .where(ProjectGuide.project_id == project["id"])
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(GuideMutationIdempotencyRecord)
                .where(GuideMutationIdempotencyRecord.idempotency_key == key)
            )
            == 0
        )

    recovered = await project_client.post(
        f"/api/v1/projects/{project['id']}/guides",
        headers=auth_headers() | {"Idempotency-Key": str(key)},
        json=complete_guide_payload("recovered-v1"),
    )
    assert recovered.status_code == 201, recovered.text
    assert recovered.json()["version"] == "recovered-v1"


async def test_guide_content_null_has_no_state_then_recovery_and_omission_succeed(
    project_client: AsyncClient,
) -> None:
    project = await create_project(project_client, name="Guide content recovery")
    seed_payload = complete_guide_payload() | {
        "review_policy": None,
        "revision_policy": None,
        "payment_policy": None,
    }
    guide = await create_guide(project_client, project["id"], seed_payload)
    path = f"/api/v1/projects/{project['id']}/guides/{guide['id']}"
    key = uuid4()
    async with db_session.get_session_factory()() as session:
        seeded = await session.get(ProjectGuide, guide["id"])
        assert seeded is not None
        seeded_updated_at = seeded.updated_at

    rejected = await project_client.patch(
        path,
        headers=auth_headers() | {"Idempotency-Key": str(key)},
        json={"content_markdown": None},
    )
    assert rejected.status_code == 422, rejected.text

    async with db_session.get_session_factory()() as session:
        persisted = await session.get(ProjectGuide, guide["id"])
        assert persisted is not None
        assert persisted.content_markdown == guide["content_markdown"]
        assert persisted.updated_at == seeded_updated_at
        assert (
            await session.scalar(
                select(func.count())
                .select_from(GuideMutationIdempotencyRecord)
                .where(GuideMutationIdempotencyRecord.idempotency_key == key)
            )
            == 0
        )

    replacement = f"{guide['content_markdown']}\n\nValid replacement."
    recovered = await project_client.patch(
        path,
        headers=auth_headers() | {"Idempotency-Key": str(key)},
        json={"content_markdown": replacement},
    )
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["content_markdown"] == replacement

    summary_only = await project_client.patch(
        path,
        headers=auth_headers(),
        json={"change_summary": None},
    )
    assert summary_only.status_code == 200, summary_only.text
    assert summary_only.json()["content_markdown"] == replacement
    assert summary_only.json()["change_summary"] is None

    async with db_session.get_session_factory()() as session:
        persisted = await session.get(ProjectGuide, guide["id"])
        assert persisted is not None
        assert persisted.content_markdown == replacement
        assert persisted.change_summary is None
        record = await session.scalar(
            select(GuideMutationIdempotencyRecord).where(
                GuideMutationIdempotencyRecord.idempotency_key == key
            )
        )
        assert record is not None
        assert record.status == "committed"


async def test_unsupported_adjudicator_role_is_rejected_without_grant(
    project_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await create_project(project_client, name="Unsupported role")
    target_subject = f"role-target-{uuid4()}"
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", target_subject)
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "contributor")
    get_settings.cache_clear()
    target_admission = await project_client.get("/api/v1/auth/me", headers=auth_headers())
    assert target_admission.status_code == 200, target_admission.text
    target_actor_id = target_admission.json()["actor_id"]

    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_SUBJECT", "project-manager-subject")
    monkeypatch.setenv("WORKSTREAM_DEV_AUTH_ROLES", "project_manager")
    get_settings.cache_clear()
    key = uuid4()
    payload = {
        "target_actor_profile_id": target_actor_id,
        "role": "adjudicator",
        "qualification": {
            "skills_snapshot": {
                "availability": "available",
                "reference_ids": ["skill:opaque"],
                "unavailable_reason": None,
            },
            "reputation_snapshot": {
                "availability": "unavailable",
                "reference_ids": [],
                "unavailable_reason": "no_record",
            },
            "prior_project_work_refs": [],
            "external_expertise_refs": [],
        },
        "reason": "Current v0.1 role vocabulary regression",
    }
    headers = auth_headers() | {"Idempotency-Key": str(key)}
    response = await project_client.post(
        f"/api/v1/projects/{project['id']}/role-grants",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["details"]["errors"][0]["loc"] == ["body", "role"]

    async with db_session.get_session_factory()() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectRoleGrant)
                .where(
                    ProjectRoleGrant.project_id == project["id"],
                    ProjectRoleGrant.actor_profile_id == target_actor_id,
                )
            )
            == 0
        )

    accepted = await project_client.post(
        f"/api/v1/projects/{project['id']}/role-grants",
        headers=headers,
        json=payload | {"role": "reviewer"},
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["actor_profile_id"] == target_actor_id
    assert accepted.json()["role"] == "reviewer"

    async with db_session.get_session_factory()() as session:
        grant = await session.scalar(
            select(ProjectRoleGrant).where(
                ProjectRoleGrant.project_id == project["id"],
                ProjectRoleGrant.actor_profile_id == target_actor_id,
                ProjectRoleGrant.role == "reviewer",
                ProjectRoleGrant.status == "active",
            )
        )
        assert grant is not None



def test_adjudicator_invalidation_audit_facts_are_rejected() -> None:
    """Unsupported role facts cannot enter the typed authority audit contract."""
    project_id, event_id = uuid4(), uuid4()
    projection = {
        "role": "reviewer", "scope_type": "project", "scope_id": str(project_id),
        "future_obligation": "rev_reviewer_obligation",
    }
    event = AuthorityAuditEventInput(
        event_id=event_id,
        event_type=AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED,
        entity_type="authority_invalidation",
        entity_id=str(event_id),
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(uuid4()),
        request_id=uuid4(),
        correlation_id=uuid4(),
        permission_id=PermissionId.PROJECT_ROLE_GRANT_MANAGE,
        project_id=str(project_id),
        resource_type="actor_profile",
        resource_id=str(uuid4()),
        target_ref_kind="project_role_grant",
        target_ref_id=str(uuid4()),
        reason="authority_state_changed",
        idempotency_reference=uuid4(),
        invalidation_cause_event_id=uuid4(),
        invalidation_target_kind="actor_profile",
        invalidation_target_ref=str(uuid4()),
        before_facts={"effective": True, **projection},
        after_facts={"effective": False, **projection},
    )
    unsupported = projection | {"role": "adjudicator", "future_obligation": "none"}
    with pytest.raises(ValidationError):
        AuthorityAuditEventInput.model_validate(event.model_dump() | {
            "before_facts": {"effective": True, **unsupported},
            "after_facts": {"effective": False, **unsupported},
        })
