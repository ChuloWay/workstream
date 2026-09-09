"""Guide readiness and persisted policy-summary custody guards."""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.core.hashing import canonical_json_hash
from app.modules.projects import service as project_service_module
from app.modules.projects.service import GuideActivationBlocked, ProjectService
from app.modules.projects.post_submit_policy import (
    build_project_post_submit_checker_spec, compile_project_post_submit_checker_spec,
)
from app.db import session as db_session
from app.modules.projects.models import PostSubmitCheckerPolicy, ProjectGuide, ProjectSetupRun
from app.modules.tasks.models import AuditEvent
from httpx import AsyncClient
from sqlalchemy import select
from projects.client_fixtures import (
    auth_headers, project_client as project_client,
    project_database_env as project_database_env,
)
from projects.guide_fixtures import create_project, create_guide, complete_guide_payload
from projects.policy_bundle_fixtures import create_approved_policy_bundle
from project_create_fixtures import activate_guide_for_downstream_test


@pytest.fixture(autouse=True)
def clear_settings_after_test() -> Iterator[None]:
    """Preserve the originating module's settings-cache cleanup."""
    try:
        yield
    finally:
        get_settings.cache_clear()


def _post_submit_policy(
    guide: SimpleNamespace,
    snapshot: SimpleNamespace,
    effective: SimpleNamespace,
    pre_submit: SimpleNamespace,
) -> SimpleNamespace:
    """Bind post-submit readiness to the same guide and pre-submit lineage."""
    compiled = compile_project_post_submit_checker_spec(
        project_id=guide.project_id, guide_version=guide.version,
        spec=build_project_post_submit_checker_spec(
            project_id=guide.project_id, guide_version=guide.version,
        ),
    )
    return SimpleNamespace(
        id=str(uuid4()),
        project_id=guide.project_id,
        guide_id=guide.id,
        guide_version="v1",
        source_snapshot_id=snapshot.id,
        source_snapshot_hash=snapshot.bundle_hash,
        effective_policy_id=effective.id,
        effective_policy_hash=effective.effective_policy_hash,
        pre_submit_checker_policy_id=pre_submit.id,
        pre_submit_checker_bundle_hash=pre_submit.compiled_bundle_hash,
        lifecycle_status="approved",
        approved_by_role="project_manager",
        approved_by_actor="actor-1",
        approved_at=datetime.now(UTC),
        policy_body=compiled.policy_body,
        policy_hash=compiled.policy_hash,
        required_checkers=compiled.required_checkers,
        warning_checkers=compiled.warning_checkers,
        blocking_severities=list(compiled.blocking_severities),
    )


def _review_and_revision_policies() -> tuple[SimpleNamespace, SimpleNamespace]:
    """Supply complete review/revision facts without executing either lifecycle."""
    review = SimpleNamespace(
        human_review_required=True,
        semantics_format="v2",
        semantics_status="complete",
        policy_hash=f"sha256:{'c' * 64}",
        review_preference_window_seconds=60,
        review_lease_duration_seconds=60,
        max_active_review_leases_per_reviewer=1,
        self_review_allowed=False,
        reject_policy="allowed",
        finding_evidence_requirement="required",
        requires_second_review=False,
        allowed_decisions=["accept", "needs_revision", "reject"],
        minimum_finding_fields=["summary"],
    )
    revision = SimpleNamespace(
        semantics_status="complete",
        policy_hash=f"sha256:{'d' * 64}",
        max_revision_rounds=2,
        revision_deadline_hours=24,
        allowed_resubmission_states=["needs_revision"],
        reviewer_reassignment_rule="same_reviewer",
    )
    return review, revision


def _activation_ready_bundle() -> dict[str, Any]:
    """Build one internally consistent activation bundle for fast boundary tests."""
    project_id, guide_id, snapshot_id = (str(uuid4()) for _ in range(3))
    snapshot_hash = f"sha256:{'a' * 64}"
    submission_body = {"allowed_extensions": [".zip"]}
    submission_hash = canonical_json_hash(submission_body)
    effective_body = {"allowed_extensions": [".zip"], "max_bytes": 10}
    effective_hash = canonical_json_hash(effective_body)
    checker_bundle = {"checks": ["archive_safety"]}
    checker_hash = canonical_json_hash(checker_bundle)
    guide = SimpleNamespace(id=guide_id, project_id=project_id, version="v1")
    snapshot = SimpleNamespace(
        id=snapshot_id,
        project_id=project_id,
        guide_id=guide_id,
        guide_version="v1",
        bundle_hash=snapshot_hash,
    )
    sufficiency = SimpleNamespace(
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=snapshot_hash,
        status="passed",
        warnings_acknowledged_by_actor=None,
        warnings_acknowledged_at=None,
        warnings_acknowledged_by_role=None,
    )
    submission = SimpleNamespace(
        id=str(uuid4()),
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=snapshot_hash,
        lifecycle_status="approved",
        derivation_source="manual",
        policy_body=submission_body,
        policy_hash=submission_hash,
        approved_by_actor="actor-1",
        approved_at=datetime.now(UTC),
        approved_by_role="project_manager",
    )
    effective = SimpleNamespace(
        id=str(uuid4()),
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=snapshot_hash,
        lifecycle_status="approved",
        effective_policy=effective_body,
        effective_policy_hash=effective_hash,
        submission_artifact_policy_id=submission.id,
        submission_artifact_policy_hash=submission_hash,
    )
    pre_submit = SimpleNamespace(
        id=str(uuid4()),
        source_snapshot_id=snapshot_id,
        source_snapshot_hash=snapshot_hash,
        effective_policy_id=effective.id,
        effective_policy_hash=effective_hash,
        lifecycle_status="compiled",
        compiled_bundle=checker_bundle,
        compiled_bundle_hash=checker_hash,
    )
    post_submit = _post_submit_policy(guide, snapshot, effective, pre_submit)
    review, revision = _review_and_revision_policies()
    payment = SimpleNamespace(
        base_amount=Decimal("1.00"),
        currency="USD",
        payout_type="fixed",
        accepted_payment_rule="pay base amount",
    )
    return {
        "guide": guide,
        "source_snapshot": snapshot,
        "sufficiency_report": sufficiency,
        "submission_artifact_policy": submission,
        "effective_policy": effective,
        "pre_submit_checker_policy": pre_submit,
        "post_submit_checker_policy": post_submit,
        "review_policy": review,
        "revision_policy": revision,
        "payment_policy": payment,
    }


def _set_activation_fact(bundle: dict[str, Any], fact: str, value: Any) -> None:
    target_name, attribute = fact.split(".", 1)
    setattr(bundle[target_name], attribute, value)


@pytest.mark.parametrize(
    ("fact", "value", "message"),
    [
        ("source_snapshot.project_id", "other", "snapshot project mismatch"),
        ("source_snapshot.guide_id", "other", "snapshot is not current"),
        ("sufficiency_report.source_snapshot_id", "other", "stale snapshot"),
        ("sufficiency_report.source_snapshot_hash", "other", "snapshot hash mismatch"),
        ("sufficiency_report.status", "blocked", "blocking gaps"),
        (
            "submission_artifact_policy.lifecycle_status",
            "draft",
            "approved submission artifact policy",
        ),
        ("submission_artifact_policy.source_snapshot_id", "other", "bound to a stale snapshot"),
        ("submission_artifact_policy.source_snapshot_hash", "other", "snapshot hash mismatch"),
        ("submission_artifact_policy.policy_hash", f"sha256:{'e' * 64}", "body hash mismatch"),
        ("submission_artifact_policy.approved_by_actor", None, "approval provenance"),
        ("submission_artifact_policy.approved_by_role", "submitter", "approver role is invalid"),
        ("effective_policy.lifecycle_status", "draft", "effective.*not approved"),
        ("effective_policy.source_snapshot_id", "other", "effective.*stale snapshot"),
        ("effective_policy.source_snapshot_hash", "other", "effective.*hash mismatch"),
        ("effective_policy.effective_policy_hash", f"sha256:{'e' * 64}", "body hash mismatch"),
        ("effective_policy.submission_artifact_policy_id", "other", "wrong policy"),
        ("effective_policy.submission_artifact_policy_hash", "other", "hash provenance mismatch"),
        ("pre_submit_checker_policy.source_snapshot_id", "other", "pre-submit.*stale snapshot"),
        ("pre_submit_checker_policy.source_snapshot_hash", "other", "pre-submit.*hash mismatch"),
        ("pre_submit_checker_policy.effective_policy_id", "other", "wrong effective policy"),
        ("pre_submit_checker_policy.effective_policy_hash", "other", "bundle provenance mismatch"),
        ("pre_submit_checker_policy.lifecycle_status", "draft", "compiled project pre-submit"),
        ("pre_submit_checker_policy.compiled_bundle_hash", "", "compiled bundle hash is required"),
        ("pre_submit_checker_policy.compiled_bundle", {}, "compiled bundle is required"),
        ("post_submit_checker_policy.guide_id", "other", "post-submit.*guide mismatch"),
        (
            "post_submit_checker_policy.source_snapshot_id",
            "other",
            "post-submit.*snapshot mismatch",
        ),
        ("post_submit_checker_policy.effective_policy_id", "other", "wrong effective policy"),
        ("post_submit_checker_policy.pre_submit_checker_policy_id", "other", "wrong pre-submit"),
        (
            "post_submit_checker_policy.pre_submit_checker_bundle_hash",
            "other",
            "pre-submit hash mismatch",
        ),
        ("post_submit_checker_policy.lifecycle_status", "compiled", "approved post-submit"),
        ("post_submit_checker_policy.approved_by_actor", None, "approval provenance"),
        ("post_submit_checker_policy.approved_by_role", "submitter", "approval role is invalid"),
        ("review_policy.allowed_decisions", [], "allowed decisions"),
        ("review_policy.allowed_decisions", ["maybe"], "invalid decisions"),
        ("revision_policy.max_revision_rounds", 0, "revision policy is incomplete"),
        (
            "revision_policy.allowed_resubmission_states",
            ["accepted"],
            "invalid resubmission states",
        ),
        ("payment_policy.base_amount", Decimal("-1"), "payment policy is incomplete"),
        ("payment_policy.currency", "", "payment policy is incomplete"),
    ],
)
def test_activation_readiness_rejects_broken_chain_fact(
    monkeypatch: pytest.MonkeyPatch,
    fact: str,
    value: Any,
    message: str,
) -> None:
    bundle = _activation_ready_bundle()
    _set_activation_fact(bundle, fact, value)
    service = ProjectService(cast(Any, None))
    monkeypatch.setattr(
        service,
        "_merge_effective_submission_artifact_policy",
        lambda _body: deepcopy(bundle["effective_policy"].effective_policy),
    )
    monkeypatch.setattr(
        project_service_module,
        "require_complete_policy",
        lambda **_kwargs: None,
    )

    with pytest.raises(GuideActivationBlocked, match=message):
        service.validate_activation_ready(**bundle)


def test_activation_readiness_accepts_complete_chain_without_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _activation_ready_bundle()
    service = ProjectService(cast(Any, None))
    monkeypatch.setattr(
        service,
        "_merge_effective_submission_artifact_policy",
        lambda _body: deepcopy(bundle["effective_policy"].effective_policy),
    )
    monkeypatch.setattr(project_service_module, "require_complete_policy", lambda **_: None)

    bundle["payment_policy"] = None
    service.validate_activation_ready(**bundle, require_payment_policy=False)


@pytest.mark.parametrize("operation", ["approve", "correct", "activate"])
@pytest.mark.parametrize("field", ["required_checkers", "warning_checkers", "blocking_severities"])
async def test_persisted_policy_sidecar_cross_denies_project_write(
    project_client: AsyncClient, operation: str, field: str,
) -> None:
    """Valid persisted setup reaches summary validation before any owner mutation."""
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    bundle = await create_approved_policy_bundle(
        project_client, project["id"], guide["id"],
        approve_post_submit_checker=operation == "activate",
    )
    policy_id = bundle["post_submit_checker_policy"]["id"]
    async with db_session.get_session_factory()() as session:
        policy = await session.get(PostSubmitCheckerPolicy, policy_id)
        setup = await session.scalar(select(ProjectSetupRun).where(
            ProjectSetupRun.output_post_submit_checker_policy_id == policy_id,
        ))
        assert policy is not None and setup is not None
        persisted_guide = await session.get(ProjectGuide, guide["id"])
        assert persisted_guide is not None
        service = ProjectService(session)
        await service._validate_current_post_submit_policy_setup(persisted_guide, setup, policy)
        locked_body, locked_hash = policy.policy_body, policy.policy_hash
        initial_policy_status = policy.lifecycle_status
        initial_setup = (setup.status, setup.output_post_submit_checker_policy_id)
        audit_ids = sorted(await session.scalars(select(AuditEvent.id)))
        setattr(policy, field, [*getattr(policy, field),
            "medium" if field == "blocking_severities" else "check_acceptance_criteria_present"])
        await session.commit()

    if operation == "activate":
        response = await activate_guide_for_downstream_test(
            db_session.get_session_factory(), project_id=project["id"], guide_id=guide["id"],
        )
    else:
        suffix = "approve" if operation == "approve" else "request-correction"
        response = await project_client.post(
            f"/api/v1/projects/{project['id']}/guides/{guide['id']}/post-submit-checker-policy/{suffix}",
            headers=auth_headers(),
            json={} if operation == "approve" else {"correction_reason": "Clarify evidence"},
        )
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "post-submit checker policy hash is invalid"
    async with db_session.get_session_factory()() as session:
        policy = await session.get(PostSubmitCheckerPolicy, policy_id)
        setup = await session.get(ProjectSetupRun, setup.id)
        persisted_guide = await session.get(ProjectGuide, guide["id"])
        assert policy is not None and setup is not None and persisted_guide is not None
        assert (policy.policy_body, policy.policy_hash) == (locked_body, locked_hash)
        assert policy.lifecycle_status == initial_policy_status
        assert (setup.status, setup.output_post_submit_checker_policy_id) == initial_setup
        assert persisted_guide.status == "draft"
        assert sorted(await session.scalars(select(AuditEvent.id))) == audit_ids
