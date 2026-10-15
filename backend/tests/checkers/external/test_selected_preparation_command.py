"""The hidden contributor command selects the durable PRE owner exclusively."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import app.modules.artifacts.submission_admission as owner
from app.core.identifiers import new_record_id
from app.modules.artifacts.api import (
    SubmissionBundlePreparationRequest,
    SubmissionBundlePreparationStatus,
)
from app.modules.artifacts.submission_admission import (
    PreparedSubmissionBundlePreparationCommand,
    SubmissionBundleDurablePutResult,
    SubmissionBundlePreparationRuntime,
)
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitCompletion


@asynccontextmanager
async def _root():
    yield


def _request_case():
    actor = ActorIdentityFacts(
        actor_profile_id=new_record_id(),
        identity_link_id=new_record_id(),
        actor_kind=ActorKind.HUMAN,
    )
    task_id, assignment_id, attempt_id = (new_record_id() for _ in range(3))
    request = SubmissionBundlePreparationRequest(
        actor=actor,
        request_id=new_record_id(),
        correlation_id=new_record_id(),
        task_id=task_id,
        assignment_id=assignment_id,
        predecessor_submission_id=None,
        idempotency_key=new_record_id(),
        summary="",
        contributor_attestation="",
        media_type="application/zip",
        byte_source=SimpleNamespace(),
    )
    prepared = SimpleNamespace(
        generation_id=new_record_id(),
        commitment=SimpleNamespace(sha256="sha256:" + "1" * 64, byte_count=100),
        inspect=AsyncMock(return_value=object()),
        close=AsyncMock(),
    )
    return actor, request, prepared, attempt_id


def _runtime_case(prepared, attempt_id):
    policy = object()
    selected = SimpleNamespace(policy=policy, default_input=object(), change_gate=object())
    reservation = SimpleNamespace(attempt_id=attempt_id)
    completion = SelectedPreSubmitCompletion(
        terminal=SimpleNamespace(
            outcome="completed",
            execution=SimpleNamespace(eligible=True),
            infrastructure_failure_code=None,
        ),
        capability=object(),
    )
    materialization = SimpleNamespace(
        prepare_selected_authorization=AsyncMock(return_value=object()),
        authorize_inspected=AsyncMock(),
    )
    coordinator = SimpleNamespace(
        read_current=AsyncMock(return_value=None),
        reserve=AsyncMock(return_value=attempt_id),
    )
    selected_execution = SimpleNamespace(execute=AsyncMock(return_value=completion))
    durable = SimpleNamespace(
        admit_in_transaction=AsyncMock(return_value=(prepared, attempt_id, SimpleNamespace())),
        publish_after_commit=AsyncMock(
            return_value=SubmissionBundleDurablePutResult(
                put_attempt_id=new_record_id(),
                operation_identity="sha256:" + "2" * 64,
                status="prepared",
                replayed=False,
                admission_id=None,
                selected_pre_submit_run_id=attempt_id,
            )
        ),
    )
    runtime = SubmissionBundlePreparationRuntime(
        preparation=SimpleNamespace(prepare=AsyncMock(return_value=prepared)),
        inspector=object(),
        materialization=materialization,
        durable_put=durable,
        selected_coordinator=coordinator,
        selected_execution=selected_execution,
        storage_scheme="s3",
        artifact_deadline_ms=120_000,
    )
    return SimpleNamespace(
        runtime=runtime,
        policy=policy,
        selected=selected,
        reservation=reservation,
        completion=completion,
        materialization=materialization,
        coordinator=coordinator,
        selected_execution=selected_execution,
        durable=durable,
    )


def _command(runtime, actor):
    @asynccontextmanager
    async def runtime_factory():
        yield runtime

    authority = SimpleNamespace(preflight=AsyncMock(), transaction=_root, close=Mock())
    command = PreparedSubmissionBundlePreparationCommand(
        session=SimpleNamespace(begin=_root),
        authority=authority,
        task_contexts=SimpleNamespace(),
        project_contexts=SimpleNamespace(),
        runtime_factory=runtime_factory,
    )
    project = SimpleNamespace(
        effective_policy_id=new_record_id(),
        pre_submit_policy_id=new_record_id(),
        external_checker_policies=SimpleNamespace(value="{}"),
    )
    command._lock_authorized_context = AsyncMock(
        return_value=(SimpleNamespace(predecessor=None, checker_remediation_manifest_id=None, revision_context=None), project)
    )
    command._load_predecessor = AsyncMock(return_value=None)
    command._load_predecessor_rules = AsyncMock(return_value=None)
    return command


def _patch_selected_owners(monkeypatch, case):
    monkeypatch.setattr(
        owner,
        "LockedExternalCheckerPolicies",
        SimpleNamespace(
            model_validate_json=Mock(return_value=SimpleNamespace(pre_submit=case.policy))
        ),
    )
    monkeypatch.setattr(owner, "build_submission_manifest", Mock(return_value=object()))
    monkeypatch.setattr(
        owner, "bind_selected_pre_submit_admission", Mock(return_value=case.selected)
    )
    monkeypatch.setattr(
        owner,
        "build_selected_pre_submit_reservation",
        Mock(return_value=case.reservation),
    )
    monkeypatch.setattr(
        owner,
        "selected_pre_submit_attempt_request_digest",
        Mock(return_value="sha256:" + "3" * 64),
    )
    monkeypatch.setattr(owner, "selected_pre_submit_execution_budget_ms", Mock(return_value=60_000))


@pytest.mark.asyncio
async def test_hidden_preparation_uses_selected_pre_before_durable_admission(
    monkeypatch,
) -> None:
    actor, request, prepared, attempt_id = _request_case()
    case = _runtime_case(prepared, attempt_id)
    command = _command(case.runtime, actor)
    _patch_selected_owners(monkeypatch, case)

    result = await command.prepare(request)

    assert result.submission_bundle_preparation_status is (
        SubmissionBundlePreparationStatus.PREPARED
    )
    case.materialization.prepare_selected_authorization.assert_awaited_once()
    case.materialization.authorize_inspected.assert_awaited_once()
    case.coordinator.read_current.assert_awaited_once_with(case.reservation)
    case.coordinator.reserve.assert_awaited_once_with(case.reservation)
    case.selected_execution.execute.assert_awaited_once()
    admitted = case.durable.admit_in_transaction.await_args.args[0]
    assert admitted.selected_completion is case.completion
    case.durable.publish_after_commit.assert_awaited_once_with(
        prepared,
        attempt_id,
        case.durable.admit_in_transaction.return_value[2],
    )
