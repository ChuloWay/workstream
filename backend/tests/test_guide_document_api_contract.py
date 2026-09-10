"""The guide setup API accepts document metadata, never an inline-text fallback."""

import pytest
from pydantic import ValidationError

from app.modules.projects.schemas import (
    ProjectGuideCreate, ProjectGuideUpdate, ProjectGuideResponse, GuideSourceSnapshotItemInput,
)


@pytest.mark.parametrize("schema,payload", [
    (ProjectGuideCreate, {"version": "v0.1"}),
    (ProjectGuideUpdate, {"change_summary": "Corrected source documents"}),
])
@pytest.mark.parametrize("field", ["content_markdown", "retained_content_markdown", "content", "inline_text"])
def test_guide_write_rejects_inline_body_fields(schema, payload, field):
    with pytest.raises(ValidationError) as error:
        schema.model_validate(payload | {field: "Inline guide content"})
    assert any(item["loc"] == (field,) and item["type"] == "extra_forbidden" for item in error.value.errors())


def test_current_guide_response_excludes_retained_body():
    assert "content_markdown" not in ProjectGuideResponse.model_fields
    assert "retained_content_markdown" not in ProjectGuideResponse.model_fields


@pytest.mark.parametrize("patch", [
    {"source_kind": "url_doc"}, {"source_kind": "rubric"},
    {"ingestion_adapter": "manual_import"}, {"media_type": "text/markdown"},
    {"media_type": "text/plain"}, {"media_type": "image/png"},
    {"media_type": "audio/wav"}, {"media_type": "application/vnd.ms-powerpoint"},
])
def test_source_metadata_rejects_superseded_or_unsupported_ingress(patch):
    with pytest.raises(ValidationError):
        GuideSourceSnapshotItemInput.model_validate({
            "source_kind": "document", "source_label": "guide.pdf",
            "ingestion_adapter": "upload", "media_type": "application/pdf", **patch,
        })


@pytest.mark.parametrize("method,suffix", [
    ("GET", "post-submit-checker-policy/setup"),
    ("POST", "post-submit-checker-policy/approve"),
    ("POST", "post-submit-checker-policy/request-correction"),
    ("POST", "source-snapshots/{snapshot_id}/run-sufficiency-agent"),
])
def test_superseded_setup_endpoints_are_not_registered(method, suffix):
    from app.core.config import Settings
    from app.main import create_app

    app = create_app(Settings(environment="test"))
    path = f"/api/v1/projects/{{project_id}}/guides/{{guide_id}}/{suffix}"
    assert method.lower() not in app.openapi().get("paths", {}).get(path, {})
    assert not any(
        getattr(route, "path", None) == path and method in getattr(route, "methods", set())
        for route in app.routes
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("source,message", [
    ("unified_compilation", "unified compilation policy approval is unavailable"),
    ("agent_derivation", "manual policy lineage is required for this approval"),
    ("manual", "manual policy lineage is required for this approval"),
])
async def test_generic_approval_rejects_nonmanual_lineage_before_effects(source, message):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.modules.projects.service import ProjectService, PolicySetupBlocked
    from app.modules.projects.schemas import SubmissionArtifactPolicyApprove
    from app.schemas.auth import ActorContext

    session = SimpleNamespace(commit=AsyncMock(), flush=AsyncMock())
    service = ProjectService(session)
    guide = SimpleNamespace(id="guide", project_id="project", status="draft")
    policy = SimpleNamespace(id="policy", project_id="project", guide_id="guide",
                             lifecycle_status="draft", derivation_source=source)
    service._lock_project_guide_for_setup = AsyncMock(return_value=guide)
    service._repo = SimpleNamespace(lock_submission_artifact_policy=AsyncMock(return_value=policy))
    actor = ActorContext(actor_id="manager", external_subject="manager",
                         external_issuer="https://identity.test", roles=("project_manager",),
                         auth_source="dev_mock")
    with pytest.raises(PolicySetupBlocked, match=message):
        await service.approve_submission_artifact_policy(
            actor, "project", "guide", "policy", SubmissionArtifactPolicyApprove(),
        )
    service._repo.lock_submission_artifact_policy.assert_awaited_once_with("policy")
    assert policy.lifecycle_status == "draft"
    session.commit.assert_not_awaited()
    session.flush.assert_not_awaited()


def test_current_setup_response_excludes_superseded_post_policy_step():
    from app.modules.projects.schemas import ProjectSetupRunResponse
    assert "output_post_submit_checker_policy_id" not in ProjectSetupRunResponse.model_fields
    assert "post_submit_derivation_summary" not in ProjectSetupRunResponse.model_fields


def test_superseded_activation_implementation_is_absent():
    from app.modules.projects.service import ProjectService
    assert not hasattr(ProjectService, "activate_guide")
    assert callable(ProjectService.validate_activation_ready)
