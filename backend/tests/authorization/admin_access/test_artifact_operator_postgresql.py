"""Signed public-API proofs for exact ART system Operator authority."""

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db import session as db_session
from app.modules.tasks.models import AuditEvent
from app.modules.artifacts.models import (
    ArtifactPutAttempt,
    ArtifactRecoveryAttempt,
    ArtifactReplica,
    ArtifactVerificationJob,
)
from app.modules.artifacts import router as artifact_router
from app.modules.authorization.artifact_operator_authorization import (
    ArtifactOperatorReadAuthorization,
)
from scripts.bootstrap_access_administrator import _run as run_bootstrap
from tests.authorization.admin_access.support import SignedAccess, create_project, grant_body
from tests.test_artifact_recovery import _context, _exhausted_job, _settings


async def _events(action: str, actor_id) -> list[AuditEvent]:
    async with db_session.get_session_factory()() as session:
        return list(
            (
                await session.scalars(
                    select(AuditEvent)
                    .where(
                        AuditEvent.action_id == action,
                        AuditEvent.actor_id == str(actor_id),
                    )
                    .order_by(AuditEvent.created_at, AuditEvent.id)
                )
            ).all()
        )


async def test_signed_operator_readiness_requires_persisted_exact_system_grant(
    signed_access: SignedAccess,
) -> None:
    admin = await signed_access.actor("artifact-admin")
    operator = await signed_access.actor("artifact-operator", roles=("operator",))
    path = "/api/v1/operator/artifacts/readiness"

    denied = await signed_access.client.get(path, headers=operator.headers)
    assert denied.status_code == 404, denied.text
    denied_events = await _events("operations.artifact_storage_admission.read", operator.id)
    assert len(denied_events) == 1
    assert denied_events[0].denial_code == "permission_not_granted"
    assert denied_events[0].after_facts["resource_context_digest"].startswith("sha256:")

    code, bootstrap = await run_bootstrap(admin.id, execute=True)
    assert code == 0, bootstrap
    project_id = await create_project("artifact-project-scope")
    project_scope = await signed_access.issue(admin, grant_body(operator.id, project_id=project_id))
    assert project_scope.status_code == 422, project_scope.text
    assert project_scope.json()["error"]["code"] == "invalid_role_scope"

    grant_id = await signed_access.grant(admin, operator)
    allowed = await signed_access.client.get(path, headers=operator.headers)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["active"] is False
    events = await _events("operations.artifact_storage_admission.read", operator.id)
    assert len(events) == 2
    assert events[-1].denial_code is None
    assert events[-1].matched_grant_id == grant_id
    assert events[-1].after_facts["resource_context_digest"].startswith("sha256:")

    revoked = await signed_access.revoke(admin, grant_id)
    assert revoked.status_code == 200, revoked.text
    after_revoke = await signed_access.client.get(path, headers=operator.headers)
    assert after_revoke.status_code == 404, after_revoke.text
    events = await _events("operations.artifact_storage_admission.read", operator.id)
    assert len(events) == 3
    assert events[-1].denial_code == "permission_not_granted"


async def test_signed_artifact_read_late_response_failure_rolls_back_allow(
    signed_access: SignedAccess,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = await signed_access.actor("artifact-read-fault-admin")
    operator = await signed_access.actor("artifact-read-fault-operator")
    code, bootstrap = await run_bootstrap(admin.id, execute=True)
    assert code == 0, bootstrap
    await signed_access.grant(admin, operator)
    monkeypatch.setattr(artifact_router, "artifact_provider_readiness", lambda _: {})

    response = await signed_access.client.get(
        "/api/v1/operator/artifacts/readiness", headers=operator.headers
    )
    assert response.status_code == 503, response.text
    assert await _events("operations.artifact_storage_admission.read", operator.id) == []


async def test_signed_artifact_denial_evidence_failure_is_unavailable(
    signed_access: SignedAccess,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operator = await signed_access.actor("artifact-denial-fault-operator")

    async def fail_restage(self: ArtifactOperatorReadAuthorization) -> bool:
        raise RuntimeError("injected audit persistence failure")

    monkeypatch.setattr(ArtifactOperatorReadAuthorization, "restage_denial", fail_restage)
    response = await signed_access.client.get(
        "/api/v1/operator/artifacts/readiness", headers=operator.headers
    )
    assert response.status_code == 503, response.text
    assert await _events("operations.artifact_storage_admission.read", operator.id) == []


async def _assert_signed_resource_reads(
    signed_access: SignedAccess,
    operator,
    grant_id: str,
    source_id: str,
    replica_id: str,
    content_id: str,
    project_id: str,
    task_id: str,
) -> None:
    base = "/api/v1/operator/artifacts"
    job = await signed_access.client.get(
        f"{base}/verification-jobs/{source_id}", headers=operator.headers
    )
    assert job.status_code == 200, job.text
    assert job.json()["status"] == "provider_unavailable"
    job_events = await _events("artifact.verification_job.read", operator.id)
    assert len(job_events) == 1
    assert job_events[0].matched_grant_id == grant_id
    assert job_events[0].after_facts["resource_context_digest"].startswith("sha256:")

    replicas = await signed_access.client.get(
        f"{base}/contents/{content_id}/replicas", headers=operator.headers
    )
    assert replicas.status_code == 200, replicas.text
    assert replicas.json()["items"][0]["id"] == replica_id
    assert len(await _events("artifact.replica.read", operator.id)) == 1
    bindings = await signed_access.client.get(
        f"{base}/bindings",
        headers=operator.headers,
        params={"resource_type": "task", "resource_id": task_id},
    )
    assert bindings.status_code == 200, bindings.text
    assert len(await _events("artifact.binding.read", operator.id)) == 1
    receipts = await signed_access.client.get(
        f"{base}/replicas/{replica_id}/receipts", headers=operator.headers
    )
    assert receipts.status_code == 200, receipts.text
    assert len(await _events("artifact.receipt.read", operator.id)) == 1
    audit = await signed_access.client.get(
        f"{base}/audit-events",
        headers=operator.headers,
        params={"resource_type": "artifact_verification_job", "resource_id": source_id},
    )
    assert audit.status_code == 200, audit.text
    assert len(await _events("artifact.audit.read", operator.id)) == 1
    usage = await signed_access.client.get(
        f"{base}/admission-usage",
        headers=operator.headers,
        params={"project_id": project_id},
    )
    assert usage.status_code == 200, usage.text
    assert usage.json()["items"]
    assert all(item["configured_limit_bytes"] is None for item in usage.json()["items"])
    assert len(await _events("operations.artifact_storage_admission.read", operator.id)) == 1


async def test_signed_artifact_job_read_and_retry_commit_exact_authority(
    signed_access: SignedAccess,
    tmp_path: Path,
) -> None:
    admin = await signed_access.actor("artifact-retry-admin")
    operator = await signed_access.actor("artifact-retry-operator")
    code, bootstrap_result = await run_bootstrap(admin.id, execute=True)
    assert code == 0, bootstrap_result
    grant_id = await signed_access.grant(admin, operator)

    async with db_session.get_session_factory()() as session:
        settings = _settings(tmp_path)
        project_id, task_id, submission_id, source, _, bootstrap = await _exhausted_job(
            session, settings, tmp_path, _context()
        )
        source_id = source.id
        source_cas = source.cas_version
        put_attempt = await session.get(ArtifactPutAttempt, source.originating_put_attempt_id)
        assert put_attempt is not None
        replica = await session.get(ArtifactReplica, put_attempt.replica_id)
        assert replica is not None
        replica_id = replica.id
        content_id = replica.content_id
        await session.rollback()

    try:
        job_path = f"/api/v1/operator/artifacts/verification-jobs/{source_id}"
        await _assert_signed_resource_reads(
            signed_access,
            operator,
            grant_id,
            source_id,
            replica_id,
            content_id,
            project_id,
            task_id,
        )

        payload = {
            "project_id": project_id,
            "task_id": task_id,
            "submission_id": submission_id,
            "reason": "provider still unavailable",
            "client_idempotency_key": "signed-artifact-retry",
            "expected_source_job_cas_version": source_cas,
        }
        retry_path = f"{job_path}/retry"
        created = await signed_access.client.post(
            retry_path, headers=operator.headers, json=payload
        )
        assert created.status_code == 202, created.text
        assert created.json()["replayed"] is False
        recovery = await signed_access.client.get(
            "/api/v1/operator/artifacts/recovery-attempts/" + created.json()["recovery_attempt_id"],
            headers=operator.headers,
        )
        assert recovery.status_code == 200, recovery.text
        assert recovery.json()["source_verification_job_id"] == source_id
        assert len(await _events("artifact.recovery_attempt.read", operator.id)) == 1
        replay = await signed_access.client.post(retry_path, headers=operator.headers, json=payload)
        assert replay.status_code == 202, replay.text
        assert replay.json()["replayed"] is True
        assert {k: v for k, v in created.json().items() if k != "replayed"} == {
            k: v for k, v in replay.json().items() if k != "replayed"
        }
        decisions = await _events("artifact.verification_job.retry", operator.id)
        assert len(decisions) == 3
        assert all(
            row.matched_grant_id == grant_id and row.denial_code is None for row in decisions
        )
        async with db_session.get_session_factory()() as observer:
            attempt = await observer.get(
                ArtifactRecoveryAttempt, created.json()["recovery_attempt_id"]
            )
            assert attempt is not None
            assert attempt.source_verification_job_id == source_id
            assert (
                await observer.scalar(
                    select(func.count(ArtifactRecoveryAttempt.id)).where(
                        ArtifactRecoveryAttempt.source_verification_job_id == source_id
                    )
                )
                == 1
            )
            retry_job = await observer.get(
                ArtifactVerificationJob, created.json()["retry_verification_job_id"]
            )
            assert retry_job is not None and retry_job.parent_verification_job_id == source_id
            initiation = await observer.get(AuditEvent, attempt.initiation_audit_event_id)
            assert initiation is not None
            terminal_id = initiation.event_payload["authorization_decision_id"]
            assert terminal_id in {row.id for row in decisions}
            assert terminal_id != decisions[0].id

        revoked = await signed_access.revoke(admin, grant_id)
        assert revoked.status_code == 200, revoked.text
        denied_replay = await signed_access.client.post(
            retry_path, headers=operator.headers, json=payload
        )
        assert denied_replay.status_code == 404, denied_replay.text
        assert len(await _events("artifact.verification_job.retry", operator.id)) == 4
    finally:
        bootstrap.close()
