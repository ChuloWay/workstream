"""Signed public-API proofs for exact ART system Operator authority."""

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy import func, select, text

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink
from app.modules.tasks.models import AuditEvent
from app.modules.artifacts.models import (
    ArtifactBinding,
    ArtifactOperationReceipt,
    ArtifactPutAttempt,
    ArtifactRecoveryAttempt,
    ArtifactReplica,
    ArtifactVerificationJob,
)
from app.modules.artifacts import router as artifact_router
from app.modules.artifacts.operator import ArtifactOperatorService
from app.modules.artifacts.repository import ArtifactRepository
from app.modules.authorization.artifact_operator_authorization import (
    ArtifactOperatorReadAuthorization,
)
from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.domain.artifact_operator import (
    ArtifactOperatorReadResourceContext,
    ArtifactOperatorRetryResourceContext,
)
from app.modules.authorization.domain.resource_digest import authorization_resource_digest
from scripts.bootstrap_access_administrator import _run as run_bootstrap
from tests.authorization.admin_access.support import SignedAccess, SignedActor, create_project, grant_body
from tests.authorization.admin_access.concurrency_support import ordered_owner_calls
from tests.authorization.contribution_policies.audit_schema_support import clone_decision
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.authentication.support import issue_asymmetric_token
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


def _assert_exact_read_event(
    row: AuditEvent,
    *,
    actor: SignedActor,
    grant_id: str,
    link_id: UUID,
    request_id: UUID,
    correlation_id: UUID,
    action: ActionId,
    permission: PermissionId,
    resource_type: str,
    record_id: UUID | str,
    selector: str,
    projects: tuple[UUID, ...],
) -> None:
    assert row.event_type == "SensitiveAuthorizationAllowed"
    assert row.actor_id == str(actor.id) and row.matched_grant_id == grant_id
    assert (row.action_id, row.permission_id) == (action.value, permission.value)
    assert (row.request_id, row.correlation_id) == (str(request_id), str(correlation_id))
    assert row.denial_code is None
    assert row.after_facts == {
        "allowed": True,
        "resource_context_digest": authorization_resource_digest(
            ArtifactOperatorReadResourceContext(
                resource_type=resource_type,
                resource_id=record_id,
                selector=selector,
                project_ids=projects,
                action_id=action,
                identity_link_id=link_id,
            )
        ),
    }


async def _operator_link_id(operator: SignedActor) -> UUID:
    async with db_session.get_session_factory()() as session:
        link = await session.scalar(select(ActorIdentityLink).where(
            ActorIdentityLink.actor_profile_id == str(operator.id)
        ))
        assert link is not None
        return UUID(link.id)


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
    request_id, correlation_id = uuid4(), uuid4()
    allowed = await signed_access.client.get(
        path,
        headers=operator.headers | {
            "X-Request-Id": str(request_id), "X-Correlation-Id": str(correlation_id)
        },
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["active"] is False
    events = await _events("operations.artifact_storage_admission.read", operator.id)
    assert len(events) == 2
    assert events[-1].denial_code is None
    assert events[-1].matched_grant_id == grant_id
    _assert_exact_read_event(
        events[-1], actor=operator, grant_id=grant_id,
        link_id=await _operator_link_id(operator),
        request_id=request_id, correlation_id=correlation_id,
        action=ActionId.OPERATIONS_ARTIFACT_STORAGE_ADMISSION_READ,
        permission=PermissionId.OPERATIONS_STATUS_READ,
        resource_type="artifact_admission_scope",
        record_id="workstream:artifact_storage_readiness",
        selector="artifact-storage-readiness", projects=(),
    )

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
    request_id, correlation_id = uuid4(), uuid4()
    headers = operator.headers | {
        "X-Request-Id": str(request_id), "X-Correlation-Id": str(correlation_id)
    }
    job = await signed_access.client.get(
        f"{base}/verification-jobs/{source_id}", headers=headers
    )
    assert job.status_code == 200, job.text
    assert job.json()["status"] == "provider_unavailable"
    job_events = await _events("artifact.verification_job.read", operator.id)
    assert len(job_events) == 1
    assert job_events[0].matched_grant_id == grant_id
    assert job_events[0].after_facts["resource_context_digest"].startswith("sha256:")

    replicas = await signed_access.client.get(
        f"{base}/contents/{content_id}/replicas", headers=headers
    )
    assert replicas.status_code == 200, replicas.text
    assert replicas.json()["items"][0]["id"] == replica_id
    assert len(await _events("artifact.replica.read", operator.id)) == 1
    bindings = await signed_access.client.get(
        f"{base}/bindings",
        headers=headers,
        params={"resource_type": "task", "resource_id": task_id},
    )
    assert bindings.status_code == 200, bindings.text
    assert len(await _events("artifact.binding.read", operator.id)) == 1
    receipts = await signed_access.client.get(
        f"{base}/replicas/{replica_id}/receipts", headers=headers
    )
    assert receipts.status_code == 200, receipts.text
    assert len(await _events("artifact.receipt.read", operator.id)) == 1
    audit = await signed_access.client.get(
        f"{base}/audit-events",
        headers=headers,
        params={"resource_type": "artifact_verification_job", "resource_id": source_id},
    )
    assert audit.status_code == 200, audit.text
    assert len(await _events("artifact.audit.read", operator.id)) == 1
    usage = await signed_access.client.get(
        f"{base}/admission-usage",
        headers=headers,
        params={"project_id": project_id},
    )
    assert usage.status_code == 200, usage.text
    assert usage.json()["items"]
    assert all(item["configured_limit_bytes"] is None for item in usage.json()["items"])
    assert len(await _events("operations.artifact_storage_admission.read", operator.id)) == 1
    link_id = await _operator_link_id(operator)
    project = (UUID(project_id),)
    cases = (
        (ActionId.ARTIFACT_VERIFICATION_JOB_READ, PermissionId.ARTIFACT_VERIFICATION_JOB_READ,
         "artifact_verification_job", UUID(source_id), source_id),
        (ActionId.ARTIFACT_REPLICA_READ, PermissionId.ARTIFACT_REPLICA_READ,
         "artifact_content", UUID(content_id), content_id),
        (ActionId.ARTIFACT_BINDING_READ, PermissionId.ARTIFACT_BINDING_READ,
         "artifact_binding_scope", UUID(task_id), f"task:{task_id}"),
        (ActionId.ARTIFACT_RECEIPT_READ, PermissionId.ARTIFACT_RECEIPT_READ,
         "artifact_replica", UUID(replica_id), replica_id),
        (ActionId.ARTIFACT_AUDIT_READ, PermissionId.ARTIFACT_AUDIT_READ,
         "artifact_audit_resource", UUID(source_id), f"artifact_verification_job:{source_id}"),
        (ActionId.OPERATIONS_ARTIFACT_STORAGE_ADMISSION_READ, PermissionId.OPERATIONS_STATUS_READ,
         "artifact_admission_scope", UUID(project_id), f"project:{project_id}:task:*"),
    )
    for action, permission, resource_type, record_id, selector in cases:
        rows = await _events(action.value, operator.id)
        assert len(rows) == 1
        _assert_exact_read_event(
            rows[0], actor=operator, grant_id=grant_id, link_id=link_id,
            request_id=request_id, correlation_id=correlation_id, action=action,
            permission=permission, resource_type=resource_type, record_id=record_id,
            selector=selector, projects=project,
        )


def _assert_retry_decisions(
    decisions: list[AuditEvent], *, actor: SignedActor, grant_id: str,
    link_id: UUID, request_id: UUID, correlation_id: UUID, payload: dict,
    source_id: str,
) -> None:
    assert len(decisions) == 3
    digest = authorization_resource_digest(ArtifactOperatorRetryResourceContext(
        resource_id=UUID(source_id), project_id=UUID(payload["project_id"]),
        task_id=UUID(payload["task_id"]),
        submission_id=UUID(payload["submission_id"]) if payload["submission_id"] else None,
        expected_source_job_cas_version=payload["expected_source_job_cas_version"],
        identity_link_id=link_id,
    ))
    for row in decisions:
        assert (row.actor_id, row.matched_grant_id, row.denial_code) == (
            str(actor.id), grant_id, None
        )
        assert (row.action_id, row.permission_id) == (
            ActionId.ARTIFACT_VERIFICATION_JOB_RETRY.value,
            PermissionId.ARTIFACT_VERIFICATION_JOB_RETRY.value,
        )
        assert row.after_facts == {"allowed": True, "resource_context_digest": digest}
    assert all((row.request_id, row.correlation_id) == (
        str(request_id), str(correlation_id)
    ) for row in decisions[:2])


async def _assert_retry_chain_effects(
    created: dict, source_id: str, decisions: list[AuditEvent]
) -> None:
    async with db_session.get_session_factory()() as observer:
        attempt = await observer.get(ArtifactRecoveryAttempt, created["recovery_attempt_id"])
        assert attempt is not None and attempt.source_verification_job_id == source_id
        assert await observer.scalar(select(func.count(ArtifactRecoveryAttempt.id)).where(
            ArtifactRecoveryAttempt.source_verification_job_id == source_id
        )) == 1
        retry_job = await observer.get(
            ArtifactVerificationJob, created["retry_verification_job_id"]
        )
        assert retry_job is not None and retry_job.parent_verification_job_id == source_id
        initiation = await observer.get(AuditEvent, attempt.initiation_audit_event_id)
        assert initiation is not None
        terminal_id = initiation.event_payload["authorization_decision_id"]
        assert terminal_id in {row.id for row in decisions}
        assert terminal_id != decisions[0].id


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
        retry_request_id, retry_correlation_id = uuid4(), uuid4()
        created = await signed_access.client.post(
            retry_path,
            headers=operator.headers | {
                "X-Request-Id": str(retry_request_id),
                "X-Correlation-Id": str(retry_correlation_id),
            },
            json=payload,
        )
        assert created.status_code == 202, created.text
        assert created.json()["replayed"] is False
        recovery_request_id, recovery_correlation_id = uuid4(), uuid4()
        recovery = await signed_access.client.get(
            "/api/v1/operator/artifacts/recovery-attempts/" + created.json()["recovery_attempt_id"],
            headers=operator.headers | {
                "X-Request-Id": str(recovery_request_id),
                "X-Correlation-Id": str(recovery_correlation_id),
            },
        )
        assert recovery.status_code == 200, recovery.text
        assert recovery.json()["source_verification_job_id"] == source_id
        assert len(await _events("artifact.recovery_attempt.read", operator.id)) == 1
        link_id = await _operator_link_id(operator)
        _assert_exact_read_event(
            (await _events("artifact.recovery_attempt.read", operator.id))[0],
            actor=operator, grant_id=grant_id, link_id=link_id,
            request_id=recovery_request_id, correlation_id=recovery_correlation_id,
            action=ActionId.ARTIFACT_RECOVERY_ATTEMPT_READ,
            permission=PermissionId.ARTIFACT_RECOVERY_ATTEMPT_READ,
            resource_type="artifact_recovery_attempt",
            record_id=UUID(created.json()["recovery_attempt_id"]),
            selector=created.json()["recovery_attempt_id"], projects=(UUID(project_id),),
        )
        replay = await signed_access.client.post(retry_path, headers=operator.headers, json=payload)
        assert replay.status_code == 202, replay.text
        assert replay.json()["replayed"] is True
        assert {k: v for k, v in created.json().items() if k != "replayed"} == {
            k: v for k, v in replay.json().items() if k != "replayed"
        }
        decisions = await _events("artifact.verification_job.retry", operator.id)
        _assert_retry_decisions(
            decisions, actor=operator, grant_id=grant_id, link_id=link_id,
            request_id=retry_request_id, correlation_id=retry_correlation_id,
            payload=payload, source_id=source_id,
        )
        await _assert_retry_chain_effects(created.json(), source_id, decisions)

        revoked = await signed_access.revoke(admin, grant_id)
        assert revoked.status_code == 200, revoked.text
        denied_replay = await signed_access.client.post(
            retry_path, headers=operator.headers, json=payload
        )
        assert denied_replay.status_code == 404, denied_replay.text
        assert len(await _events("artifact.verification_job.retry", operator.id)) == 4
    finally:
        bootstrap.close()


async def test_signed_retry_late_persistence_failure_rolls_back_authority_and_effects(
    signed_access: SignedAccess,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = await signed_access.actor("artifact-late-retry-admin")
    operator = await signed_access.actor("artifact-late-retry-operator")
    code, bootstrap_result = await run_bootstrap(admin.id, execute=True)
    assert code == 0, bootstrap_result
    await signed_access.grant(admin, operator)
    async with db_session.get_session_factory()() as session:
        project_id, task_id, submission_id, source, _, bootstrap = await _exhausted_job(
            session, _settings(tmp_path), tmp_path, _context()
        )
        source_id, source_cas = source.id, source.cas_version
        await session.rollback()

    original = ArtifactRepository.add_recovery_attempt
    staged: list[tuple[int, int, int, int]] = []

    async def fail_after_staging(repository, attempt):
        await original(repository, attempt)
        session = repository._session
        counts = (
            await session.scalar(select(func.count(AuditEvent.id)).where(
                AuditEvent.action_id == "artifact.verification_job.retry",
                AuditEvent.actor_id == str(operator.id),
            )),
            await session.scalar(select(func.count(ArtifactRecoveryAttempt.id)).where(
                ArtifactRecoveryAttempt.source_verification_job_id == source_id
            )),
            await session.scalar(select(func.count(ArtifactVerificationJob.id)).where(
                ArtifactVerificationJob.parent_verification_job_id == source_id
            )),
            await session.scalar(select(func.count(AuditEvent.id)).where(
                AuditEvent.event_type == "ArtifactRecoveryInitiated",
                AuditEvent.entity_id == attempt.id,
            )),
        )
        staged.append(counts)
        raise SQLAlchemyError("injected after complete retry staging")

    try:
        with monkeypatch.context() as patch:
            patch.setattr(ArtifactRepository, "add_recovery_attempt", fail_after_staging)
            response = await signed_access.client.post(
                f"/api/v1/operator/artifacts/verification-jobs/{source_id}/retry",
                headers=operator.headers,
                json={
                    "project_id": project_id,
                    "task_id": task_id,
                    "submission_id": submission_id,
                    "reason": "late rollback proof",
                    "client_idempotency_key": "signed-late-retry-fault",
                    "expected_source_job_cas_version": source_cas,
                },
            )
        assert response.status_code == 503, response.text
        assert staged == [(2, 1, 1, 1)]
        assert await _events("artifact.verification_job.retry", operator.id) == []
        async with db_session.get_session_factory()() as observer:
            assert await observer.scalar(select(func.count(ArtifactRecoveryAttempt.id)).where(
                ArtifactRecoveryAttempt.source_verification_job_id == source_id
            )) == 0
            assert await observer.scalar(select(func.count(ArtifactVerificationJob.id)).where(
                ArtifactVerificationJob.parent_verification_job_id == source_id
            )) == 0
            assert await observer.scalar(select(func.count(AuditEvent.id)).where(
                AuditEvent.event_type == "ArtifactRecoveryInitiated"
            )) == 0
    finally:
        bootstrap.close()


async def test_signed_replica_read_digests_all_stored_project_lineage(
    signed_access: SignedAccess,
    tmp_path: Path,
) -> None:
    admin = await signed_access.actor("artifact-lineage-admin")
    operator = await signed_access.actor("artifact-lineage-operator")
    code, bootstrap_result = await run_bootstrap(admin.id, execute=True)
    assert code == 0, bootstrap_result
    grant_id = await signed_access.grant(admin, operator)
    async with db_session.get_session_factory()() as session:
        first_project, task_id, _, source, _, bootstrap = await _exhausted_job(
            session, _settings(tmp_path), tmp_path, _context()
        )
        put_attempt = await session.get(ArtifactPutAttempt, source.originating_put_attempt_id)
        assert put_attempt is not None
        replica = await session.get(ArtifactReplica, put_attempt.replica_id)
        assert replica is not None
        replica_id, content_id, source_id = replica.id, replica.content_id, source.id
        receipt_id = await session.scalar(select(ArtifactOperationReceipt.id).where(
            ArtifactOperationReceipt.replica_id == replica_id
        ))
        assert receipt_id is not None
        await session.rollback()
    try:
        second_project = str(await create_project("artifact-second-lineage"))
        async with db_session.get_session_factory()() as session:
            session.add(ArtifactBinding(
                id=str(new_record_id()), content_id=content_id, project_id=second_project,
                resource_type="task", resource_id=task_id, logical_role="operator-lineage",
                scope_version=1, actor_id=str(operator.id), attribution_type="human",
            ))
            await session.commit()
        request_id, correlation_id = uuid4(), uuid4()
        headers = operator.headers | {
            "X-Request-Id": str(request_id), "X-Correlation-Id": str(correlation_id),
        }
        link_id = await _operator_link_id(operator)
        projects = tuple(sorted((UUID(first_project), UUID(second_project))))
        cases = (
            (f"/contents/{content_id}/replicas", None,
             ActionId.ARTIFACT_REPLICA_READ, PermissionId.ARTIFACT_REPLICA_READ,
             "artifact_content", UUID(content_id), content_id),
            (f"/replicas/{replica_id}/receipts", None,
             ActionId.ARTIFACT_RECEIPT_READ, PermissionId.ARTIFACT_RECEIPT_READ,
             "artifact_replica", UUID(replica_id), replica_id),
            (f"/verification-jobs/{source_id}", None,
             ActionId.ARTIFACT_VERIFICATION_JOB_READ, PermissionId.ARTIFACT_VERIFICATION_JOB_READ,
             "artifact_verification_job", UUID(source_id), source_id),
            ("/audit-events", {"resource_type": "artifact_replica", "resource_id": replica_id},
             ActionId.ARTIFACT_AUDIT_READ, PermissionId.ARTIFACT_AUDIT_READ,
             "artifact_audit_resource", UUID(replica_id), f"artifact_replica:{replica_id}"),
            ("/audit-events", {"resource_type": "artifact_receipt", "resource_id": receipt_id},
             ActionId.ARTIFACT_AUDIT_READ, PermissionId.ARTIFACT_AUDIT_READ,
             "artifact_audit_resource", UUID(receipt_id), f"artifact_receipt:{receipt_id}"),
            ("/audit-events", {"resource_type": "artifact_verification_job", "resource_id": source_id},
             ActionId.ARTIFACT_AUDIT_READ, PermissionId.ARTIFACT_AUDIT_READ,
             "artifact_audit_resource", UUID(source_id), f"artifact_verification_job:{source_id}"),
        )
        audit_count = 0
        for path, params, action, permission, resource_type, record_id, selector in cases:
            response = await signed_access.client.get(
                f"/api/v1/operator/artifacts{path}", headers=headers, params=params,
            )
            assert response.status_code == 200, response.text
            if action is ActionId.ARTIFACT_REPLICA_READ:
                assert response.json()["items"][0]["id"] == replica_id
            audit_count += action is ActionId.ARTIFACT_AUDIT_READ
            events = await _events(action.value, operator.id)
            assert len(events) == (audit_count if audit_count else 1)
            _assert_exact_read_event(
                events[-1], actor=operator, grant_id=grant_id, link_id=link_id,
                request_id=request_id, correlation_id=correlation_id,
                action=action, permission=permission, resource_type=resource_type,
                record_id=record_id, selector=selector, projects=projects,
            )
            incomplete = authorization_resource_digest(ArtifactOperatorReadResourceContext(
                resource_type=resource_type, resource_id=record_id, selector=selector,
                action_id=action, identity_link_id=link_id,
                project_ids=(UUID(first_project),),
            ))
            assert events[-1].after_facts["resource_context_digest"] != incomplete
    finally:
        bootstrap.close()


@pytest.mark.parametrize("writer_kind", ("binding", "put_completion"))
async def test_signed_content_lineage_serializes_new_project_association(
    signed_access: SignedAccess,
    auth_database_env: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    writer_kind: str,
) -> None:
    admin = await signed_access.actor(f"artifact-lineage-race-admin-{writer_kind}")
    operator = await signed_access.actor(f"artifact-lineage-race-operator-{writer_kind}")
    code, bootstrap_result = await run_bootstrap(admin.id, execute=True)
    assert code == 0, bootstrap_result
    await signed_access.grant(admin, operator)
    settings = _settings(tmp_path)
    async with db_session.get_session_factory()() as session:
        first_project, task_id, _, source, _, bootstrap = await _exhausted_job(
            session, settings, tmp_path, _context()
        )
        attempt = await session.get(ArtifactPutAttempt, source.originating_put_attempt_id)
        assert attempt is not None
        replica = await session.get(ArtifactReplica, attempt.replica_id)
        assert replica is not None
        content_id, replica_id = replica.content_id, replica.id
        await session.rollback()
    identity = f"art-lineage-{writer_kind[:3]}-{uuid4().hex}"
    collected, writer_ready, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    reader_pid = writer_pid = None
    original_projects = ArtifactOperatorService._content_projects
    original_lock = ArtifactRepository.lock_content
    path = f"/api/v1/operator/artifacts/contents/{content_id}/replicas"
    async def paused_projects(service, candidate):
        nonlocal reader_pid
        projects = await original_projects(service, candidate)
        if candidate == content_id and not collected.is_set():
            reader_pid = await service._session.scalar(text("select pg_backend_pid()"))
            collected.set()
            await release.wait()
        return projects
    async def captured_lock(repository, candidate):
        nonlocal writer_pid
        if candidate == content_id and asyncio.current_task().get_name() == identity + "-writer":
            await repository._session.execute(
                text("select set_config('application_name', :name, true)"), {"name": identity}
            )
            writer_pid = await repository._session.scalar(text("select pg_backend_pid()"))
            writer_ready.set()
        return await original_lock(repository, candidate)
    async def writer():
        nonlocal writer_pid
        await collected.wait()
        if writer_kind == "put_completion":
            async with db_session.get_session_factory()() as session:
                project, _, _, later_source, _, later_bootstrap = await _exhausted_job(
                    session, settings, tmp_path, _context()
                )
                try:
                    later_attempt = await session.get(
                        ArtifactPutAttempt, later_source.originating_put_attempt_id
                    )
                    assert later_attempt is not None and later_attempt.replica_id == replica_id
                finally:
                    later_bootstrap.close()
            return project
        project = str(await create_project("artifact-binding-race-project"))
        async with db_session.get_session_factory()() as session:
            await session.execute(
                text("select set_config('application_name', :name, true)"), {"name": identity}
            )
            writer_pid = await session.scalar(text("select pg_backend_pid()"))
            writer_ready.set()
            assert await ArtifactRepository(session).lock_content(content_id) is not None
            session.add(ArtifactBinding(
                id=str(new_record_id()), content_id=content_id, project_id=project,
                resource_type="task", resource_id=task_id, logical_role="lineage-race",
                scope_version=1, actor_id=str(operator.id), attribution_type="human",
            ))
            await session.commit()
        return project

    async def observe_waiter():
        await writer_ready.wait()
        assert reader_pid is not None and writer_pid is not None and reader_pid != writer_pid
        await wait_for_named_database_lock(
            auth_database_env, identity,
            expected_waiter_pid=writer_pid, expected_blocker_pid=reader_pid,
        )
        release.set()

    try:
        with monkeypatch.context() as patch:
            patch.setattr(ArtifactOperatorService, "_content_projects", paused_projects)
            patch.setattr(ArtifactRepository, "lock_content", captured_lock)
            first, second_project, _ = await asyncio.wait_for(asyncio.gather(
                asyncio.create_task(signed_access.client.get(path, headers=operator.headers), name=identity + "-reader"),
                asyncio.create_task(writer(), name=identity + "-writer"),
                asyncio.create_task(observe_waiter(), name=identity + "-observer"),
            ), timeout=120)
        assert first.status_code == 200, first.text
        assert first.json()["items"][0]["id"] == replica_id
        first_events = await _events("artifact.replica.read", operator.id)
        assert len(first_events) == 1
        link_id = await _operator_link_id(operator)
        first_digest = authorization_resource_digest(ArtifactOperatorReadResourceContext(
            resource_type="artifact_content", resource_id=UUID(content_id), selector=content_id,
            project_ids=(UUID(first_project),), action_id=ActionId.ARTIFACT_REPLICA_READ,
            identity_link_id=link_id,
        ))
        assert first_events[0].after_facts["resource_context_digest"] == first_digest
        second = await signed_access.client.get(path, headers=operator.headers)
        assert second.status_code == 200, second.text
        events = await _events("artifact.replica.read", operator.id)
        assert len(events) == 2
        full_digest = authorization_resource_digest(ArtifactOperatorReadResourceContext(
            resource_type="artifact_content", resource_id=UUID(content_id), selector=content_id,
            project_ids=tuple(sorted((UUID(first_project), UUID(second_project)))),
            action_id=ActionId.ARTIFACT_REPLICA_READ, identity_link_id=link_id,
        ))
        assert events[-1].after_facts["resource_context_digest"] == full_digest
    finally:
        release.set()
        bootstrap.close()


@pytest.mark.parametrize(
    ("action", "permission"),
    [
        (ActionId.ARTIFACT_BINDING_READ, PermissionId.ARTIFACT_BINDING_READ),
        (ActionId.ARTIFACT_REPLICA_READ, PermissionId.ARTIFACT_REPLICA_READ),
        (ActionId.ARTIFACT_RECEIPT_READ, PermissionId.ARTIFACT_RECEIPT_READ),
        (ActionId.ARTIFACT_VERIFICATION_JOB_READ, PermissionId.ARTIFACT_VERIFICATION_JOB_READ),
        (ActionId.ARTIFACT_RECOVERY_ATTEMPT_READ, PermissionId.ARTIFACT_RECOVERY_ATTEMPT_READ),
        (ActionId.ARTIFACT_AUDIT_READ, PermissionId.ARTIFACT_AUDIT_READ),
        (ActionId.OPERATIONS_ARTIFACT_STORAGE_ADMISSION_READ, PermissionId.OPERATIONS_STATUS_READ),
        (ActionId.ARTIFACT_VERIFICATION_JOB_RETRY, PermissionId.ARTIFACT_VERIFICATION_JOB_RETRY),
    ],
)
async def test_migrated_audit_constraint_rejects_swapped_art_permission(
    signed_access: SignedAccess,
    action: ActionId,
    permission: PermissionId,
) -> None:
    operator = await signed_access.actor(f"artifact-constraint-{action.name.lower()}")
    await signed_access.client.get(
        "/api/v1/operator/artifacts/readiness", headers=operator.headers
    )
    decision = (await _events("operations.artifact_storage_admission.read", operator.id))[0]
    assert decision.denial_code == "permission_not_granted"
    with pytest.raises(DBAPIError, match="ck_audit_events_authorization_action_evidence"):
        await clone_decision(decision, {
            "action_id": action.value,
            "permission_id": PermissionId.OPERATIONS_STATUS_READ.value
            if permission is not PermissionId.OPERATIONS_STATUS_READ
            else PermissionId.ARTIFACT_BINDING_READ.value,
        })


@pytest.mark.parametrize("transition", ("actor_suspend", "link_revoke", "grant_revoke"))
@pytest.mark.parametrize("transition_first", (True, False))
async def test_signed_retry_serializes_against_operator_authority_transition(
    signed_access: SignedAccess,
    auth_database_env: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    transition: str,
    transition_first: bool,
) -> None:
    admin = await signed_access.actor(f"artifact-race-admin-{transition}")
    operator = await signed_access.actor(f"artifact-race-operator-{transition}")
    code, bootstrap_result = await run_bootstrap(admin.id, execute=True)
    assert code == 0, bootstrap_result
    grant_id = await signed_access.grant(admin, operator)
    async with db_session.get_session_factory()() as session:
        project_id, task_id, submission_id, source, _, bootstrap = await _exhausted_job(
            session, _settings(tmp_path), tmp_path, _context()
        )
        source_id, source_cas = source.id, source.cas_version
        link = await session.scalar(select(ActorIdentityLink).where(
            ActorIdentityLink.actor_profile_id == str(operator.id)
        ))
        assert link is not None
        link_id = link.id
        await session.rollback()
    payload = {
        "project_id": project_id,
        "task_id": task_id,
        "submission_id": submission_id,
        "reason": "serialized retry proof",
        "client_idempotency_key": "signed-artifact-race",
        "expected_source_job_cas_version": source_cas,
    }
    retry_path = f"/api/v1/operator/artifacts/verification-jobs/{source_id}/retry"

    async def retry():
        return await signed_access.client.post(retry_path, headers=operator.headers, json=payload)

    async def disable():
        if transition == "grant_revoke":
            return await signed_access.revoke(admin, grant_id)
        path = (
            f"/api/v1/actors/{operator.id}/suspend" if transition == "actor_suspend"
            else f"/api/v1/actor-identity-links/{link_id}/revoke"
        )
        return await signed_access.client.post(
            path,
            headers=admin.headers | {"Idempotency-Key": str(uuid4())},
            json={"reason": "End Operator authority during retry"},
        )

    try:
        first, second, custody = await ordered_owner_calls(
            disable if transition_first else retry,
            retry if transition_first else disable,
            boundary="control",
            database_url=auth_database_env,
            monkeypatch=monkeypatch,
        )
        assert custody.observed
        assert (first if transition_first else second).status_code == 200
        retry_response = second if transition_first else first
        assert retry_response.status_code == (404 if transition_first else 202), retry_response.text
        decisions = await _events("artifact.verification_job.retry", operator.id)
        assert sum(row.denial_code is None for row in decisions) == (0 if transition_first else 2)
        async with db_session.get_session_factory()() as observer:
            attempts = await observer.scalar(select(func.count(ArtifactRecoveryAttempt.id)).where(
                ArtifactRecoveryAttempt.source_verification_job_id == source_id
            ))
            jobs = await observer.scalar(select(func.count(ArtifactVerificationJob.id)).where(
                ArtifactVerificationJob.parent_verification_job_id == source_id
            ))
        assert (attempts, jobs) == ((0, 0) if transition_first else (1, 1))
        if not transition_first:
            denied_replay = await retry()
            assert denied_replay.status_code == 404, denied_replay.text
    finally:
        bootstrap.close()


async def test_signed_existing_artifact_read_conceals_non_operator_and_revoked_identity(
    signed_access: SignedAccess,
    tmp_path: Path,
) -> None:
    admin = await signed_access.actor("artifact-negative-admin")
    granted = await signed_access.actor("artifact-negative-granted")
    token_role = await signed_access.actor("artifact-negative-token-role", roles=("operator",))
    wrong_role = await signed_access.actor("artifact-negative-wrong-role")
    suspended = await signed_access.actor("artifact-negative-suspended")
    unlinked = await signed_access.actor("artifact-negative-unlinked")
    code, bootstrap_result = await run_bootstrap(admin.id, execute=True)
    assert code == 0, bootstrap_result
    await signed_access.grant(admin, granted)
    async with db_session.get_session_factory()() as session:
        project_id, _, _, source, _, bootstrap = await _exhausted_job(
            session, _settings(tmp_path), tmp_path, _context()
        )
        source_id = source.id
        await session.rollback()
    try:
        await signed_access.grant(
            admin, wrong_role, role="project_manager", project_id=UUID(project_id)
        )
        await signed_access.grant(admin, suspended)
        await signed_access.grant(admin, unlinked)
        link_id = await _operator_link_id(unlinked)
        suspend = await signed_access.client.post(
            f"/api/v1/actors/{suspended.id}/suspend",
            headers=admin.headers | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Negative ART identity proof"},
        )
        assert suspend.status_code == 200, suspend.text
        revoke_link = await signed_access.client.post(
            f"/api/v1/actor-identity-links/{link_id}/revoke",
            headers=admin.headers | {"Idempotency-Key": str(uuid4())},
            json={"reason": "Negative ART identity proof"},
        )
        assert revoke_link.status_code == 200, revoke_link.text
        path = f"/api/v1/operator/artifacts/verification-jobs/{source_id}"
        missing = await signed_access.client.get(
            f"/api/v1/operator/artifacts/verification-jobs/{uuid4()}",
            headers=granted.headers,
        )
        assert missing.status_code == 404, missing.text
        concealed = missing.json()
        concealed["error"].pop("correlation_id")
        service_token = issue_asymmetric_token(
            signed_access.private_key, scope="workstream:service",
            claims={
                "sub": f"artifact-unprovisioned-service-{uuid4()}",
                "subject_kind": "service", "roles": ["operator"],
            },
        )
        for actor, headers, expected_denial in (
            (token_role, token_role.headers, "permission_not_granted"),
            (wrong_role, wrong_role.headers, "permission_not_granted"),
            (None, {"Authorization": f"Bearer {service_token}"}, None),
            (suspended, suspended.headers, "actor_suspended"),
            (unlinked, unlinked.headers, "identity_link_revoked"),
        ):
            response = await signed_access.client.get(path, headers=headers)
            assert response.status_code == 404, response.text
            body = response.json()
            body["error"].pop("correlation_id")
            assert body == concealed
            if actor is not None:
                decisions = await _events("artifact.verification_job.read", actor.id)
                assert len(decisions) == 1
                assert decisions[0].denial_code == expected_denial
                assert decisions[0].matched_grant_id is None
    finally:
        bootstrap.close()


async def test_signed_concurrent_exact_retry_has_one_chain_and_fresh_decisions(
    signed_access: SignedAccess,
    tmp_path: Path,
) -> None:
    admin = await signed_access.actor("artifact-same-key-admin")
    operator = await signed_access.actor("artifact-same-key-operator")
    code, bootstrap_result = await run_bootstrap(admin.id, execute=True)
    assert code == 0, bootstrap_result
    grant_id = await signed_access.grant(admin, operator)
    async with db_session.get_session_factory()() as session:
        project_id, task_id, submission_id, source, _, bootstrap = await _exhausted_job(
            session, _settings(tmp_path), tmp_path, _context()
        )
        source_id, source_cas = source.id, source.cas_version
        await session.rollback()
    payload = {
        "project_id": project_id,
        "task_id": task_id,
        "submission_id": submission_id,
        "reason": "concurrent exact retry proof",
        "client_idempotency_key": "signed-concurrent-artifact-retry",
        "expected_source_job_cas_version": source_cas,
    }
    path = f"/api/v1/operator/artifacts/verification-jobs/{source_id}/retry"
    try:
        first, second = await asyncio.wait_for(asyncio.gather(*(
            signed_access.client.post(path, headers=operator.headers, json=payload)
            for _ in range(2)
        )), timeout=60)
        assert first.status_code == second.status_code == 202, (first.text, second.text)
        assert {first.json()["replayed"], second.json()["replayed"]} == {False, True}
        assert {k: v for k, v in first.json().items() if k != "replayed"} == {
            k: v for k, v in second.json().items() if k != "replayed"
        }
        events = await _events("artifact.verification_job.retry", operator.id)
        assert len(events) == 3
        assert all(row.matched_grant_id == grant_id and row.denial_code is None for row in events)
        async with db_session.get_session_factory()() as observer:
            assert await observer.scalar(select(func.count(ArtifactRecoveryAttempt.id)).where(
                ArtifactRecoveryAttempt.source_verification_job_id == source_id
            )) == 1
            assert await observer.scalar(select(func.count(ArtifactVerificationJob.id)).where(
                ArtifactVerificationJob.parent_verification_job_id == source_id
            )) == 1
            assert await observer.scalar(select(func.count(AuditEvent.id)).where(
                AuditEvent.event_type == "ArtifactRecoveryInitiated"
            )) == 1
    finally:
        bootstrap.close()
