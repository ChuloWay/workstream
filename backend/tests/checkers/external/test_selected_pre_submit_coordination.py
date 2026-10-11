"""Selected PRE durable ownership stays exact before native migration proof."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.core.identifiers import new_record_id
from app.modules.checkers.api.default_checker import WORKSTREAM_DEFAULT_BEHAVIOR_SHA256
from app.modules.checkers.api.selected_pre_submit import (
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
