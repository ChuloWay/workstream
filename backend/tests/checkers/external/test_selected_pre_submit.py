"""Selected default and project PRE images share one verified ART callback."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.interfaces.external_checker_execution import (
    ExternalCheckerExecutionResponse,
    ExternalCheckerIsolationReceipt,
    ExternalCheckerMaterialGrant,
)
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
    WorkstreamDefaultCheckerInput,
    workstream_default_input_sha256,
)
from app.modules.checkers.api.external import (
    PRE_SUBMIT_INPUT_SCHEMA_ID,
    ExternalCheckerRegistryEntry,
    ExternalCheckerSchema,
    PreSubmitExternalCheckerIdentity,
    PreSubmitExternalCheckerMaterial,
    external_checker_json_hash,
    make_external_checker_execution_result,
)
from app.modules.checkers.api.external_policy import (
    LockedExternalCheckerBinding,
    LockedExternalCheckerPolicies,
    LockedExternalPostSubmitPolicy,
    LockedExternalPreSubmitPolicy,
    LockedWorkstreamDefault,
)
from app.modules.checkers.api.materialization import SubmissionMaterialEntry
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitLeaseFacts,
    SelectedPreSubmitReservationFacts,
    SelectedPreSubmitTerminalFacts,
)
from app.modules.checkers.selected_pre_submit_execution import SelectedPreSubmitProcessor
from app.adapters.checkers import SelectedPreSubmitCheckerExecutionAdapter
from app.modules.artifacts.pre_submit_attempts import PreSubmitAttemptClaim
from app.modules.artifacts.selected_pre_submit_admission import (
    bind_selected_pre_submit_admission,
    build_selected_pre_submit_reservation,
)
from app.modules.artifacts.submission_manifest import SubmissionCanonicalPredecessor
from app.modules.artifacts.submission_materialization import (
    PreparedBundleMaterializationService,
)
from app.modules.checkers.api.pre_submit import SubmissionPacketView
from tests.checkers.external.support import SHA, registry_entry
from tests.test_default_pre_submit_execution import _request


def _open_input_schema() -> ExternalCheckerSchema:
    document = {"type": "object"}
    return ExternalCheckerSchema(
        schema_id=PRE_SUBMIT_INPUT_SCHEMA_ID,
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )


def _policy() -> LockedExternalPreSubmitPolicy:
    values = registry_entry().model_dump()
    values["input_schema"] = _open_input_schema()
    # The immutable entry digest includes the input schema.
    spec = {
        key: value
        for key, value in values.items()
        if key
        not in {
            "registry_entry_id",
            "entry_digest",
            "registration_operation_id",
            "registered_by_actor_profile_id",
            "authorization_decision_event_id",
            "created_at",
        }
    }
    spec["input_schema"] = values["input_schema"].model_dump(mode="json")
    values["entry_digest"] = external_checker_json_hash(spec)
    registry = ExternalCheckerRegistryEntry.model_validate(values)
    binding = LockedExternalCheckerBinding(
        requirement_id="project.archive_rules",
        stage="pre_submit",
        registry=registry,
        configuration={},
        configuration_sha256=external_checker_json_hash({}),
    )
    default = LockedWorkstreamDefault()
    body = {
        "schema_version": "external_pre_submit_policy.v1",
        "workstream_default": default.model_dump(mode="json"),
        "entries": [binding.model_dump(mode="json")],
    }
    return LockedExternalPreSubmitPolicy(
        workstream_default=default,
        entries=(binding,),
        policy_sha256=canonical_json_hash(body),
    )


def _policies() -> LockedExternalCheckerPolicies:
    pre = _policy()
    post_body = {
        "schema_version": "external_post_submit_policy.v1",
        "entries": [],
    }
    post = LockedExternalPostSubmitPolicy(
        entries=(),
        policy_sha256=canonical_json_hash(post_body),
    )
    body = {
        "schema_version": "external_checker_policies.v1",
        "pre_submit": pre.model_dump(mode="json"),
        "post_submit": post.model_dump(mode="json"),
    }
    return LockedExternalCheckerPolicies(
        pre_submit=pre,
        post_submit=post,
        policies_sha256=canonical_json_hash(body),
    )


class _GrantIssuer:
    def __init__(self) -> None:
        self.requests = []

    @contextmanager
    def issue(self, request, _workspace):
        self.requests.append(request)
        yield ExternalCheckerMaterialGrant(
            grant_id="extract_" + "a" * 32,
            binding_digest="sha256:" + "b" * 64,
        )


class _Execution:
    def __init__(self, verdict: str) -> None:
        self.verdict = verdict
        self.requests = []

    async def execute(self, request, _grant):
        self.requests.append(request)
        findings = (
            ()
            if self.verdict == "passed"
            else (
                {
                    "code": "project_rule_failed",
                    "level": "error",
                    "message": "Project rule failed.",
                },
            )
        )
        result = make_external_checker_execution_result(
            request_digest=request.request_digest,
            registry_entry_id=request.registry.registry_entry_id,
            registry_entry_digest=request.registry.entry_digest,
            phase="pre_submit",
            outcome="completed",
            verdict=self.verdict,
            findings=findings,
            infrastructure_failure_code=None,
        )
        return ExternalCheckerExecutionResponse(
            result=result,
            isolation=ExternalCheckerIsolationReceipt(
                repository="registry.example/workstream/checker",
                platform_manifest_digest=request.registry.image_digest,
                platform_manifest_media_type=(
                    "application/vnd.oci.image.manifest.v1+json"
                ),
                platform_manifest_byte_count=1024,
                operating_system="linux",
                architecture="amd64",
                config_image_id=SHA,
                runtime="runsc",
                isolation_mode="gvisor",
                sandbox_uid=65532,
                sandbox_gid=65532,
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict,eligible", [("passed", True), ("failed", False)])
async def test_selected_pre_runs_default_then_locked_external_image(
    tmp_path, verdict: str, eligible: bool
) -> None:
    request, inspector, manager, preparation, _catalogue = await _request(tmp_path)
    policy = _policy()
    identity = PreSubmitExternalCheckerIdentity(
        project_id=request.effective_plan.lineage.project_id,
        task_id=request.task_id,
        assignment_id=request.assignment_id,
        prepared_generation_id=request.prepared_artifact.generation_id,
        attempt_id=new_record_id(),
        attempt_request_digest=SHA,
        effective_plan_sha256=policy.policy_sha256,
    )
    material = PreSubmitExternalCheckerMaterial(
        role="submission_archive",
        prepared_generation_id=identity.prepared_generation_id,
        attempt_id=identity.attempt_id,
        attempt_request_digest=identity.attempt_request_digest,
        archive_sha256=request.prepared_artifact.commitment.sha256,
        archive_byte_count=request.prepared_artifact.commitment.byte_count,
        semantic_manifest_sha256=request.manifest.sha256,
        media_type="application/zip",
    )
    entries = tuple(
        SubmissionMaterialEntry(
            item.normalized_path,
            item.entry_type.value,
            item.byte_count,
            item.sha256,
            item.executable,
        )
        for item in request.manifest.entries
    )
    default_input = WorkstreamDefaultCheckerInput(
        archive_sha256=material.archive_sha256,
        archive_byte_count=material.archive_byte_count,
        archive_media_type=material.media_type,
        semantic_manifest_sha256=material.semantic_manifest_sha256,
        entries=entries,
        predecessor=None,
        predecessor_exists=False,
        current_predecessor=None,
        current_rules_sha256=request.effective_plan.lineage.pre_submit_policy_bundle_hash,
        predecessor_rules_sha256=None,
        packet=SubmissionPacketView(summary="", contributor_attestation=""),
    )
    grants, execution = _GrantIssuer(), _Execution(verdict)
    processor = SelectedPreSubmitProcessor(
        archive_inspector=inspector,
        inspection=request.inspection,
        policy=policy,
        default_input=default_input,
        identity=identity,
        material=material,
        grants=grants,
        execution=execution,
    )
    try:
        result = await preparation._process_prepared_submission(
            request.prepared_artifact,
            processor,
            reserved_bytes=request.manifest.total_expanded_bytes,
            maximum_entries=request.manifest.entry_count,
        )
        assert result.eligible is eligible
        assert result.workstream_default.eligible
        assert [item.code for item in result.workstream_default.warnings] == [
            "submission_summary_missing",
            "submission_attestation_missing",
        ]
        assert len(result.external_members) == 1
        assert result.external_members[0].result.verdict == verdict
        assert len(grants.requests) == len(execution.requests) == 1
        assert grants.requests[0].request_digest == execution.requests[0].request_digest
        assert result.result_digest == canonical_json_hash(result.canonical_body())
        now = datetime.now(UTC)
        reservation = SelectedPreSubmitReservationFacts(
            actor_profile_id=new_record_id(),
            identity_link_id=new_record_id(),
            project_id=identity.project_id,
            task_id=identity.task_id,
            assignment_id=identity.assignment_id,
            attempt_id=identity.attempt_id,
            attempt_request_digest=identity.attempt_request_digest,
            prepared_generation_id=identity.prepared_generation_id,
            policy_sha256=policy.policy_sha256,
            default_behavior_sha256=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
            default_input_sha256=workstream_default_input_sha256(default_input),
            archive_sha256=material.archive_sha256,
            archive_byte_count=material.archive_byte_count,
            semantic_manifest_sha256=material.semantic_manifest_sha256,
            execution_budget_ms=120_000,
        )
        lease = SelectedPreSubmitLeaseFacts(
            reservation=reservation,
            lease_id=new_record_id(),
            lease_generation=1,
            lease_expires_at=now + timedelta(minutes=2),
        )
        terminal = SelectedPreSubmitTerminalFacts(
            lease=lease,
            outcome="completed",
            execution=result,
            infrastructure_failure_code=None,
            queued_at=now,
            started_at=now + timedelta(milliseconds=25),
            completed_at=now + timedelta(milliseconds=75),
        )
        assert terminal.canonical_body()["queue_latency_ms"] == 25
        assert terminal.canonical_body()["execution_latency_ms"] == 50
        assert terminal.canonical_body()["request_digest"] == reservation.request_digest
        assert terminal.terminal_digest == canonical_json_hash(terminal.canonical_body())
    finally:
        await request.prepared_artifact.close()
        manager.close()


@pytest.mark.asyncio
async def test_selected_pre_default_secret_blocker_precedes_external_image(
    tmp_path,
) -> None:
    request, inspector, manager, preparation, _catalogue = await _request(
        tmp_path,
        primary_bytes=b"-----BEGIN OPENSSH PRIVATE KEY-----\nencoded",
    )
    policy = _policy()
    identity = PreSubmitExternalCheckerIdentity(
        project_id=request.effective_plan.lineage.project_id,
        task_id=request.task_id,
        assignment_id=request.assignment_id,
        prepared_generation_id=request.prepared_artifact.generation_id,
        attempt_id=new_record_id(),
        attempt_request_digest=SHA,
        effective_plan_sha256=policy.policy_sha256,
    )
    material = PreSubmitExternalCheckerMaterial(
        role="submission_archive",
        prepared_generation_id=identity.prepared_generation_id,
        attempt_id=identity.attempt_id,
        attempt_request_digest=identity.attempt_request_digest,
        archive_sha256=request.prepared_artifact.commitment.sha256,
        archive_byte_count=request.prepared_artifact.commitment.byte_count,
        semantic_manifest_sha256=request.manifest.sha256,
        media_type="application/zip",
    )
    entries = tuple(
        SubmissionMaterialEntry(
            item.normalized_path,
            item.entry_type.value,
            item.byte_count,
            item.sha256,
            item.executable,
        )
        for item in request.manifest.entries
    )
    execution = _Execution("passed")
    grants = _GrantIssuer()
    processor = SelectedPreSubmitProcessor(
        archive_inspector=inspector,
        inspection=request.inspection,
        policy=policy,
        default_input=WorkstreamDefaultCheckerInput(
            archive_sha256=material.archive_sha256,
            archive_byte_count=material.archive_byte_count,
            archive_media_type=material.media_type,
            semantic_manifest_sha256=material.semantic_manifest_sha256,
            entries=entries,
            predecessor=None,
            predecessor_exists=False,
            current_predecessor=None,
            current_rules_sha256=request.effective_plan.lineage.pre_submit_policy_bundle_hash,
            predecessor_rules_sha256=None,
            packet=request.packet,
        ),
        identity=identity,
        material=material,
        grants=grants,
        execution=execution,
    )
    try:
        result = await preparation._process_prepared_submission(
            request.prepared_artifact,
            processor,
            reserved_bytes=request.manifest.total_expanded_bytes,
            maximum_entries=request.manifest.entry_count,
        )
        assert result.eligible is False
        assert result.workstream_default.checks[2].failure_code == (
            "high_confidence_secret_detected"
        )
        assert result.external_members == ()
        assert grants.requests == []
        assert execution.requests == []
    finally:
        await request.prepared_artifact.close()
        manager.close()


@pytest.mark.asyncio
async def test_selected_admission_binds_unchanged_work_to_current_task_rules(
    tmp_path,
) -> None:
    request, _inspector, manager, _preparation, _catalogue = await _request(tmp_path)
    policies = _policies()
    project_id = request.effective_plan.lineage.project_id
    actor_profile_id = new_record_id()
    identity_link_id = new_record_id()
    assignment_id = new_record_id()
    guide_id = new_record_id()
    source_snapshot_id = new_record_id()
    effective_policy_id = new_record_id()
    pre_submit_policy_id = new_record_id()
    predecessor = SubmissionCanonicalPredecessor(
        submission_id=new_record_id(),
        submission_version=1,
        archive_sha256=request.prepared_artifact.commitment.sha256,
        semantic_manifest_sha256=request.manifest.sha256,
    )
    task = SimpleNamespace(
        contributor_id=actor_profile_id,
        task_id=request.task_id,
        assignment_id=assignment_id,
        predecessor=SimpleNamespace(
            submission_id=predecessor.submission_id,
            version=predecessor.submission_version,
        ),
        locked_project_context=SimpleNamespace(project_id=project_id),
        locked_policy=SimpleNamespace(
            model_dump=lambda **_kwargs: {
                "locked_guide_version": "v1",
                "locked_pre_submit_checker_bundle_hash": SHA,
            }
        ),
    )
    project = SimpleNamespace(
        project_id=project_id,
        guide_id=guide_id,
        guide_version="v1",
        source_snapshot_id=source_snapshot_id,
        source_snapshot_hash=SHA,
        effective_policy_id=effective_policy_id,
        effective_policy_hash=SHA,
        pre_submit_policy_id=pre_submit_policy_id,
        pre_submit_policy_bundle_hash=SHA,
        external_checker_policies=SimpleNamespace(
            value=json.dumps(
                policies.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            )
        ),
    )
    try:
        bound = bind_selected_pre_submit_admission(
            task=task,
            project=project,
            commitment=request.prepared_artifact.commitment,
            manifest=request.manifest,
            predecessor=predecessor,
            predecessor_rules_sha256="sha256:" + "d" * 64,
            predecessor_exists=True,
            packet=request.packet,
        )
        assert bound.change_gate.outcome.value == "unchanged"
        assert bound.default_input.predecessor is not None
        assert bound.default_input.predecessor_rules_sha256 == "sha256:" + "d" * 64
        assert bound.default_input.current_rules_sha256 == bound.rules_sha256
        assert bound.policy.policy_sha256 == policies.pre_submit.policy_sha256
        reservation = build_selected_pre_submit_reservation(
            actor_profile_id=actor_profile_id,
            identity_link_id=identity_link_id,
            task=task,
            project=project,
            prepared_generation_id=request.prepared_artifact.generation_id,
            attempt_id=new_record_id(),
            attempt_request_digest=SHA,
            commitment=request.prepared_artifact.commitment,
            manifest=request.manifest,
            packet=request.packet,
            selected=bound,
            storage_scheme="s3",
            execution_budget_ms=120_000,
        )
        assert reservation.admission_lineage is not None
        assert reservation.admission_lineage.semantic_manifest_body == (
            request.manifest.as_dict()
        )
        assert reservation.admission_lineage.packet_sha256 == request.packet.sha256
        assert reservation.admission_lineage.predecessor_submission_id == (
            predecessor.submission_id
        )
    finally:
        await request.prepared_artifact.close()
        manager.close()


@pytest.mark.asyncio
async def test_selected_factory_uses_request_bound_art_grant(tmp_path) -> None:
    request, inspector, manager, preparation, _catalogue = await _request(tmp_path)
    policy = _policy()
    entries = tuple(
        SubmissionMaterialEntry(
            item.normalized_path,
            item.entry_type.value,
            item.byte_count,
            item.sha256,
            item.executable,
        )
        for item in request.manifest.entries
    )
    request = replace(
        request,
        external_policy=policy,
        default_checker_input=WorkstreamDefaultCheckerInput(
            archive_sha256=request.prepared_artifact.commitment.sha256,
            archive_byte_count=request.prepared_artifact.commitment.byte_count,
            archive_media_type="application/zip",
            semantic_manifest_sha256=request.manifest.sha256,
            entries=entries,
            predecessor=None,
            predecessor_exists=False,
            current_predecessor=None,
            current_rules_sha256=request.effective_plan.lineage.pre_submit_policy_bundle_hash,
            predecessor_rules_sha256=None,
            packet=request.packet,
        ),
    )
    transaction = True
    claim = object.__new__(PreSubmitAttemptClaim)
    claim.attempt_id, claim._nonce = new_record_id(), new_record_id()
    claim.request_digest = SHA
    claim._request = replace(request, prepared_authorization=None)
    claim._started, claim._execution = False, None
    row = SimpleNamespace(
        status="reserved",
        evidence_set_id=None,
        claim_nonce=str(claim._nonce),
        request_digest=claim.request_digest,
        prepared_generation_id=str(request.prepared_artifact.generation_id),
    )
    session = SimpleNamespace(
        in_transaction=lambda: transaction,
        in_nested_transaction=lambda: False,
        scalar=AsyncMock(return_value=row),
    )
    claim._session = session
    execution = _Execution("passed")
    authority = SimpleNamespace(
        prepare=AsyncMock(return_value=object()),
        consume=AsyncMock(),
    )
    service = PreparedBundleMaterializationService(
        session=session,
        authorization=authority,
        preparation=preparation,
        checker_execution=SelectedPreSubmitCheckerExecutionAdapter(
            archive_inspector=inspector,
            external_execution=execution,
        ),
        storage_scheme="s3",
    )
    try:
        await service.prepare_authorization(
            task_id=request.task_id,
            assignment_id=request.assignment_id,
            submission_artifact_policy_id=request.submission_artifact_policy_id,
            checker_policy_id=request.checker_policy_id,
            prepared_artifact=request.prepared_artifact,
            effective_plan=request.effective_plan,
            idempotency_key=new_record_id(),
            external_policy=policy,
        )
        assert authority.prepare.await_count == 1
        await service.authorize_prepared_bundle(request, claim=claim)
        transaction = False
        result = await service.materialize_prepared_bundle(
            replace(request, prepared_authorization=None), claim=claim
        )
        assert result.checker_facts.eligible is True
        assert len(execution.requests) == 1
        assert execution.requests[0].identity.attempt_id == claim.attempt_id
        assert execution.requests[0].materials[0].archive_sha256 == (
            request.prepared_artifact.commitment.sha256
        )
    finally:
        await request.prepared_artifact.close()
        manager.close()
