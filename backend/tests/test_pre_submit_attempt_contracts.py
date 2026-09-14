"""Negative boundaries for ART attempt identity, replay and invocation claims."""

from dataclasses import replace
import pickle
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.pre_submit_attempts import (
    PreSubmitAttemptClaim,
    PreSubmitAttemptStore,
    logical_request,
)
from app.modules.artifacts.pre_submit_evidence import PreSubmitEvidenceConflict
from app.modules.artifacts.submission_materialization import PreparedBundleMaterializationService
from app.modules.checkers.catalogue import build_pre_submission_checker_catalogue
from tests.test_default_pre_submit_execution import _plan, _request
from tests.test_effective_pre_submit_execution import _context


def test_attempt_claim_cannot_be_constructed_or_serialized() -> None:
    with pytest.raises(TypeError, match="issued by ART"):
        PreSubmitAttemptClaim()
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(object.__new__(PreSubmitAttemptClaim))


def test_logical_attempt_identity_binds_packet_policy_and_archive_but_not_retry_generation() -> None:
    context = _context()
    plan = _plan(build_pre_submission_checker_catalogue())
    packet = SimpleNamespace(summary="Original work", contributor_attestation="rights_confirmed")

    def digest(current_context=context, current_packet=packet):
        # logical_request consumes a dataclass packet; use the real typed view.
        from app.modules.checkers.api import SubmissionPacketView

        view = SubmissionPacketView(
            summary=current_packet.summary,
            contributor_attestation=current_packet.contributor_attestation,
        )
        return canonical_json_hash(logical_request(current_context, plan, view))

    original = digest()
    assert digest(replace(context, prepared_generation_id=uuid4())) == original
    assert digest(current_packet=SimpleNamespace(
        summary="Changed work", contributor_attestation=packet.contributor_attestation,
    )) != original
    assert digest(replace(context, locked_checker_policy_sha256="sha256:" + "e" * 64)) != original
    assert digest(replace(context, archive_sha256="sha256:" + "f" * 64)) != original


def _claim(request, session, *, spent=False, foreign=False):
    claim = object.__new__(PreSubmitAttemptClaim)
    claim.attempt_id, claim._nonce = uuid4(), uuid4()
    claim.request_digest = "sha256:" + "1" * 64
    claim._request = replace(request, prepared_authorization=None)
    claim._started, claim._execution = spent, None
    claim._session = object() if foreign else session
    return claim


@pytest.mark.parametrize("claim_kind", ("absent", "foreign", "spent", "missing_reservation"))
async def test_invalid_attempt_claim_never_builds_processor_or_opens_workspace(
    tmp_path, claim_kind: str,
) -> None:
    request, _inspector, manager, _preparation, catalogue = await _request(tmp_path)
    session = SimpleNamespace(
        in_transaction=lambda: True,
        in_nested_transaction=lambda: False,
        scalar=AsyncMock(return_value=None),
    )
    authorization = SimpleNamespace(consume=AsyncMock())
    processor_build = Mock(side_effect=AssertionError("invalid claim built CHECKER processor"))
    preparation = SimpleNamespace(_process_prepared_submission=AsyncMock(
        side_effect=AssertionError("invalid claim opened scratch"),
    ))
    service = PreparedBundleMaterializationService(
        session=session,
        authorization=authorization,
        preparation=preparation,
        checker_execution=SimpleNamespace(
            catalogue_manifest_sha256=catalogue.manifest_sha256,
            build=processor_build,
        ),
        storage_scheme="s3",
    )
    claim = {
        "absent": None,
        "foreign": _claim(request, session, foreign=True),
        "spent": _claim(request, session, spent=True),
        "missing_reservation": _claim(request, session),
    }[claim_kind]
    try:
        with pytest.raises(PreSubmitEvidenceConflict, match="pre_submit_attempt_claim_invalid"):
            await service.materialize_prepared_bundle(request, claim=claim)
        processor_build.assert_not_called()
        preparation._process_prepared_submission.assert_not_awaited()
        assert list((tmp_path / "scratch" / "workspaces").iterdir()) == []
    finally:
        await request.prepared_artifact.close()
        manager.close()


@pytest.mark.parametrize("missing_field", ("metadata_json", "checker_order"))
async def test_completed_replay_rejects_missing_result_metadata_before_capability(
    missing_field: str,
) -> None:
    plan = _plan(build_pre_submission_checker_catalogue())
    attempt_id, evidence_id = str(uuid4()), str(uuid4())
    request_digest = "sha256:" + "a" * 64
    evidence = SimpleNamespace(
        id=evidence_id, attempt_id=attempt_id, attempt_request_digest=request_digest,
        packet_sha256="sha256:" + "b" * 64,
    )
    row = SimpleNamespace(
        id=attempt_id, status="completed", evidence_set_id=evidence_id,
        request_json={"packet_sha256": "sha256:" + "b" * 64},
        request_digest=request_digest,
    )
    members = [SimpleNamespace(metadata_json=[], checker_order=entry.order)
               for entry in plan.entries]
    setattr(members[0], missing_field, None)
    session = SimpleNamespace(
        get=AsyncMock(return_value=evidence),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: members)),
    )
    with pytest.raises(PreSubmitEvidenceConflict, match="pre_submit_attempt_result_unavailable"):
        await PreSubmitAttemptStore(session).read_completed(row=row, context=_context(), plan=plan)


@pytest.mark.parametrize("corruption", ("definition_order", "metadata"))
async def test_completed_replay_rejects_nonnull_corrupt_result_before_capability(
    corruption: str,
) -> None:
    plan = _plan(build_pre_submission_checker_catalogue())
    context = _context()
    attempt_id, evidence_id = str(uuid4()), str(uuid4())
    request_digest = "sha256:" + "a" * 64
    evidence = SimpleNamespace(
        id=evidence_id, attempt_id=attempt_id, attempt_request_digest=request_digest,
        packet_sha256="sha256:" + "b" * 64,
        archive_sha256=context.archive_sha256, archive_byte_count=context.archive_byte_count,
        semantic_manifest_sha256=context.semantic_manifest_sha256,
        storage_scheme=context.storage_scheme, effective_plan_sha256=plan.plan_sha256,
        eligible=True,
    )
    row = SimpleNamespace(
        id=attempt_id, status="completed", evidence_set_id=evidence_id,
        request_json={"packet_sha256": "sha256:" + "b" * 64},
        request_digest=request_digest, prepared_generation_id=str(context.prepared_generation_id),
    )
    members = [SimpleNamespace(
        dispatch_authority="workstream.pre_submission_checker_catalogue",
        definition_id=entry.definition_id, definition_version=entry.definition_version,
        public_name=entry.public_name, source=entry.policy_trace_source,
        effective_plan_sha256=plan.plan_sha256, rule_instance_id=entry.rule_instance_id,
        locked_policy_sha256=plan.lineage.effective_policy_hash,
        phase=entry.phase, checker_order=entry.order,
        classification=entry.classification,
        severity="warning" if entry.classification == "advisory" else "blocking",
        status="passed", failure_code=None, message_code="passed", metadata_json=[],
    ) for entry in plan.entries]
    if corruption == "definition_order":
        members[0].checker_order += 1
    else:
        members[0].metadata_json = [["unregistered_count", 1]]
    session = SimpleNamespace(
        get=AsyncMock(return_value=evidence),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: members)),
    )
    with pytest.raises(PreSubmitEvidenceConflict, match="pre_submission_result_context_invalid"):
        await PreSubmitAttemptStore(session).read_completed(row=row, context=context, plan=plan)
