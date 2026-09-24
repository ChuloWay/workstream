"""Focused ART adapter proofs for AUTH submission preparation."""

from app.core.identifiers import new_record_id
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.adapters import artifacts as artifact_adapters
from app.modules.artifacts.authorization import PreparedSubmissionBundlePreparationAuthorization
from app.modules.artifacts.schemas import (
    ArtifactAuthorityDeniedError,
    SubmissionBundleDurableIntentAuthorityFacts,
)
from app.modules.authorization.runtime import PreparedAuthorizationInput


def _sha(value: str) -> str:
    return "sha256:" + value * 64


def test_artifact_adapter_composes_active_preparation_authority() -> None:
    session, context = object(), object()
    authority = artifact_adapters.get_submission_bundle_preparation_authorization(session, context)
    assert type(authority) is PreparedSubmissionBundlePreparationAuthorization
    assert authority._session is session
    assert authority._context is context


@pytest.mark.asyncio
async def test_final_preparation_rejects_cross_request_facts() -> None:
    authority = object.__new__(PreparedSubmissionBundlePreparationAuthorization)
    project_id, actor_id, link_id, task_id, assignment_id = (new_record_id() for _ in range(5))
    authority._input = PreparedAuthorizationInput(
        idempotency_key=new_record_id(),
        request_value={
            "scope_project_id": str(project_id),
            "actor_profile_id": str(actor_id),
            "identity_link_id": str(link_id),
            "task_id": str(task_id),
            "assignment_id": str(assignment_id),
            "predecessor_submission_id": None,
        },
    )
    facts = SubmissionBundleDurableIntentAuthorityFacts(
        actor_profile_id=actor_id,
        identity_link_id=link_id,
        project_id=project_id,
        task_id=task_id,
        assignment_id=new_record_id(),
        predecessor_submission_id=None,
        predecessor_submission_version=None,
        pre_submit_evidence_set_id=new_record_id(),
        prepared_generation_id=new_record_id(),
        guide_id=new_record_id(),
        guide_version="v1",
        source_snapshot_id=new_record_id(),
        source_snapshot_sha256=_sha("1"),
        effective_policy_id=new_record_id(),
        effective_policy_sha256=_sha("2"),
        pre_submit_policy_id=new_record_id(),
        pre_submit_policy_sha256=_sha("3"),
        effective_plan_sha256=_sha("4"),
        semantic_manifest_id=new_record_id(),
        semantic_manifest_sha256=_sha("5"),
        archive_sha256=_sha("6"),
        archive_byte_count=42,
        media_type="application/zip",
        storage_scheme="s3",
        operation_identity=_sha("7"),
        replay_durable_intent_id=None,
    )
    with pytest.raises(ArtifactAuthorityDeniedError):
        await authority.prepare_final(facts=facts)


@pytest.mark.asyncio
async def test_preflight_rejects_nonhuman_context_before_database_access() -> None:
    authority = object.__new__(PreparedSubmissionBundlePreparationAuthorization)
    authority._context = object()
    authority._session = SimpleNamespace(begin=AsyncMock())

    with pytest.raises(ArtifactAuthorityDeniedError):
        await authority.preflight(request=SimpleNamespace(actor=object()))


@pytest.mark.asyncio
async def test_final_preparation_requires_preflight_input() -> None:
    authority = object.__new__(PreparedSubmissionBundlePreparationAuthorization)
    authority._input = None

    with pytest.raises(ArtifactAuthorityDeniedError):
        await authority.prepare_final(facts=object())
