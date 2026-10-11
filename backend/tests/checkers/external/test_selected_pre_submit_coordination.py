"""Selected PRE durable ownership stays exact before native migration proof."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.core.identifiers import new_record_id
from app.core.hashing import canonical_json_hash
from app.modules.artifacts.schemas import SubmissionBundleArtifactAdmissionRequest
from app.modules.artifacts.models import (
    SubmissionBundleAdmission,
    SubmissionBundleDurableIntent,
)
from app.modules.checkers.api.default_checker import WORKSTREAM_DEFAULT_BEHAVIOR_SHA256
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitExecuteFacts,
    SelectedPreSubmitAdmissionLineage,
    SelectedPreSubmitFinalizeFacts,
    SelectedPreSubmitLeaseFacts,
    SelectedPreSubmitReservationFacts,
)
from app.modules.checkers.models import SelectedPreSubmitRun
from app.modules.checkers.selected_pre_submit_coordination import (
    SelectedPreSubmitAdmissionCapability,
    SelectedPreSubmitExecutionCapability,
    SelectedPreSubmitUnavailable,
)
from tests.checkers.external.support import SHA


def _reservation() -> SelectedPreSubmitReservationFacts:
    return SelectedPreSubmitReservationFacts(
        actor_profile_id=new_record_id(),
        identity_link_id=new_record_id(),
        project_id=new_record_id(),
        task_id=new_record_id(),
        assignment_id=new_record_id(),
        attempt_id=new_record_id(),
        attempt_request_digest=SHA,
        prepared_generation_id=new_record_id(),
        policy_sha256="sha256:" + "1" * 64,
        default_behavior_sha256=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
        default_input_sha256="sha256:" + "2" * 64,
        archive_sha256="sha256:" + "3" * 64,
        archive_byte_count=1024,
        semantic_manifest_sha256="sha256:" + "4" * 64,
        execution_budget_ms=120_000,
    )


def test_selected_pre_model_compiles_complete_owner_and_authority_custody() -> None:
    sql = str(
        CreateTable(SelectedPreSubmitRun.__table__).compile(
            dialect=postgresql.dialect()
        )
    )
    for value in (
        "fk_selected_pre_run_task_project",
        "fk_selected_pre_run_assignment",
        "execute_evidence_id",
        "finalize_evidence_id",
        "execution_budget_ms",
    ):
        assert value in sql
    assert "pre_submit_execution_attempts" not in sql

    intent_sql = str(
        CreateTable(SubmissionBundleDurableIntent.__table__).compile(
            dialect=postgresql.dialect()
        )
    )
    admission_sql = str(
        CreateTable(SubmissionBundleAdmission.__table__).compile(
            dialect=postgresql.dialect()
        )
    )
    for compiled in (intent_sql, admission_sql):
        assert "selected_pre_submit_run_id" in compiled
        assert "pre_submit_lineage" in compiled
    for value in (
        "semantic_manifest_body",
        "packet_sha256",
        "effective_plan_sha256",
        "pre_submit_policy_sha256",
    ):
        assert value in admission_sql


def test_selected_pre_admission_capability_is_exact_and_single_use() -> None:
    reservation = _reservation()
    owner = SimpleNamespace(_capability=None)
    run_id = new_record_id()
    terminal = SimpleNamespace(
        lease=SimpleNamespace(reservation=reservation),
        terminal_digest="sha256:" + "5" * 64,
    )
    capability = SelectedPreSubmitAdmissionCapability._issued(
        owner=owner,
        run_id=run_id,
        terminal=terminal,
    )
    owner._capability = capability
    values = {
        "run_id": run_id,
        "terminal_digest": terminal.terminal_digest,
        "attempt_id": reservation.attempt_id,
        "prepared_generation_id": reservation.prepared_generation_id,
        "archive_sha256": reservation.archive_sha256,
        "semantic_manifest_sha256": reservation.semantic_manifest_sha256,
    }
    with pytest.raises(
        SelectedPreSubmitUnavailable, match="selected_pre_submit_admission_unavailable"
    ):
        capability.consume(
            **(values | {"semantic_manifest_sha256": "sha256:" + "6" * 64})
        )
    assert capability.consume(**values) == run_id
    with pytest.raises(SelectedPreSubmitUnavailable):
        capability.consume(**values)


def test_selected_pre_execution_capability_is_exact_and_single_use() -> None:
    from datetime import UTC, datetime

    reservation = _reservation()
    lease = SelectedPreSubmitLeaseFacts(
        reservation=reservation,
        lease_id=new_record_id(),
        lease_generation=1,
        lease_expires_at=datetime.now(UTC),
    )
    owner = SimpleNamespace(_execution_capability=None)
    capability = SelectedPreSubmitExecutionCapability._issued(
        owner=owner,
        run_id=reservation.attempt_id,
        lease=lease,
    )
    owner._execution_capability = capability
    with pytest.raises(
        SelectedPreSubmitUnavailable, match="selected_pre_submit_execution_unavailable"
    ):
        capability.consume(run_id=new_record_id(), lease=lease)
    assert capability.consume(
        run_id=reservation.attempt_id,
        lease=lease,
    ) == lease
    with pytest.raises(SelectedPreSubmitUnavailable):
        capability.consume(run_id=reservation.attempt_id, lease=lease)


def test_selected_pre_authority_digests_bind_lease_and_infrastructure_outcome() -> None:
    from datetime import UTC, datetime, timedelta

    reservation = _reservation()
    lease = SelectedPreSubmitLeaseFacts(
        reservation=reservation,
        lease_id=new_record_id(),
        lease_generation=1,
        lease_expires_at=datetime.now(UTC),
    )
    execution = SelectedPreSubmitExecuteFacts(lease)
    changed = SelectedPreSubmitExecuteFacts(
        SelectedPreSubmitLeaseFacts(
            reservation=reservation,
            lease_id=lease.lease_id,
            lease_generation=2,
            lease_expires_at=lease.lease_expires_at + timedelta(seconds=1),
        )
    )
    terminal = SelectedPreSubmitFinalizeFacts(
        lease=lease,
        execution=None,
        infrastructure_failure_code="deadline_exceeded",
    )

    assert execution.facts_digest != changed.facts_digest
    assert terminal.facts_digest != SelectedPreSubmitFinalizeFacts(
        lease=lease,
        execution=None,
        infrastructure_failure_code="material_unavailable",
    ).facts_digest
    with pytest.raises(ValueError, match="outcome"):
        SelectedPreSubmitFinalizeFacts(
            lease=lease,
            execution=None,
            infrastructure_failure_code=None,
        )


def test_selected_pre_request_binds_complete_later_admission_lineage() -> None:
    manifest = {"schema_version": "submission_manifest.v1", "entries": []}
    digest = canonical_json_hash(manifest)
    lineage = SelectedPreSubmitAdmissionLineage(
        predecessor_submission_id=None,
        predecessor_submission_version=None,
        guide_id=new_record_id(),
        guide_version="locked-v1",
        source_snapshot_id=new_record_id(),
        source_snapshot_sha256=SHA,
        locked_guide_sha256=SHA,
        effective_policy_id=new_record_id(),
        effective_policy_sha256=SHA,
        pre_submit_policy_id=new_record_id(),
        pre_submit_policy_sha256=SHA,
        effective_plan_sha256="sha256:" + "1" * 64,
        locked_policy_context_hash=SHA,
        semantic_manifest_id=new_record_id(),
        semantic_manifest_body=manifest,
        packet_sha256=SHA,
        storage_scheme="s3",
    )
    reservation = replace(
        _reservation(),
        policy_sha256=lineage.effective_plan_sha256,
        semantic_manifest_sha256=digest,
        admission_lineage=lineage,
    )

    assert reservation.canonical_body()["admission_lineage"] == lineage.canonical_body()
    assert reservation.request_digest != replace(
        reservation,
        admission_lineage=replace(lineage, packet_sha256="sha256:" + "9" * 64),
    ).request_digest
    with pytest.raises(ValueError, match="reservation"):
        replace(reservation, semantic_manifest_sha256=SHA)


def test_submission_artifact_request_selects_exactly_one_pre_lineage() -> None:
    selected_id = new_record_id()
    request = SubmissionBundleArtifactAdmissionRequest(
        pre_submit_evidence_set_id=None,
        custody=object(),
        replay_durable_intent_id=None,
        selected_pre_submit_run_id=selected_id,
        selected_terminal_digest=SHA,
    )
    assert request.selected_pre_submit_run_id == selected_id
    with pytest.raises(ValueError, match="lineage"):
        SubmissionBundleArtifactAdmissionRequest(
            pre_submit_evidence_set_id=new_record_id(),
            custody=object(),
            replay_durable_intent_id=None,
            selected_pre_submit_run_id=selected_id,
            selected_terminal_digest=SHA,
        )
    with pytest.raises(ValueError, match="lineage"):
        replace(request, selected_terminal_digest=None)
