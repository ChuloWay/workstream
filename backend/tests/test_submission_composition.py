"""Focused behavior proof for hidden admission-backed Submission composition."""

from app.core.config import get_settings

from app.adapters.tasks import task_service

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID
from app.core.identifiers import new_record_id

from submission_context_fixtures import submission_context_facts

import pytest

from app.modules.tasks.api import (
    SubmissionCreationRequest,
    SubmissionCreationUnavailable,
    TaskLockedProjectContextReferences,
)
from app.modules.tasks.submission_composition import TaskSubmissionCreationService
from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.adapters.tasks import TransactionalSubmissionCreationCommand
from app.modules.artifacts.submission_bindings import SubmissionAdmissionConsumptionService
from app.modules.artifacts.authorization import PreparedSubmissionBindingAuthorization
from app.modules.authorization.prepared import (
    PreparedSubmissionCreationAuthorization,
)
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)


class _Session:
    def in_transaction(self):
        return True

    def in_nested_transaction(self):
        return False

    async def connection(self):
        return self

    async def execute(self, statement):
        return None

    async def scalar(self, statement):
        return None

    async def flush(self):
        return None


def _request():
    return SubmissionCreationRequest(
        admission_id=new_record_id(), task_id=new_record_id(), assignment_id=new_record_id(),
        contributor_id=new_record_id(), predecessor_submission_id=None,
        summary="summary", contributor_attestation="attestation",
    )


def _context(request):
    return submission_context_facts(submitter_contribution_policy_version_id=UUID(int=100),
        task_id=request.task_id, assignment_id=request.assignment_id,
        contributor_id=request.contributor_id, status="in_progress", kind="initial",
        predecessor=None,
        locked_project_context=TaskLockedProjectContextReferences(locked_contribution_policy_version_id=UUID(int=100),
            project_id=new_record_id(), guide_version="1", source_snapshot_id=new_record_id(),
            source_snapshot_hash="sha256:" + "1" * 64, effective_policy_id=new_record_id(),
            effective_policy_hash="sha256:" + "2" * 64,
            pre_submit_policy_id=new_record_id(),
            pre_submit_policy_bundle_hash="sha256:" + "3" * 64,
        ),
    )


def _task():
    values = {
        "id": str(new_record_id()), "project_id": str(new_record_id()),
        "locked_guide_version": "1", "locked_post_submit_checker_policy_id": str(new_record_id()),
        "locked_post_submit_checker_policy_version": "1",
        "locked_post_submit_checker_policy_hash": "sha256:" + "4" * 64,
        "locked_post_submit_checker_policy_body": {}, "locked_review_policy_id": str(new_record_id()),
        "locked_review_policy_generation": 1,
        "locked_review_policy_hash": "sha256:" + "5" * 64,
        "locked_revision_policy_id": str(new_record_id()), "locked_revision_policy_generation": 1,
        "locked_revision_policy_hash": "sha256:" + "6" * 64,
        "locked_guide_source_snapshot_id": str(new_record_id()),
        "locked_guide_source_snapshot_hash": "sha256:" + "7" * 64,
        "locked_effective_project_submission_artifact_policy_id": str(new_record_id()),
        "locked_effective_project_submission_artifact_policy_hash": "sha256:" + "8" * 64,
        "locked_pre_submit_checker_policy_id": str(new_record_id()),
        "locked_pre_submit_checker_bundle_hash": "sha256:" + "9" * 64,
    }
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("actor_status", "link_status"),
    [
        (ActorStatus.SUSPENDED, IdentityLinkStatus.ACTIVE),
        (ActorStatus.ACTIVE, IdentityLinkStatus.REVOKED),
    ],
)
@pytest.mark.asyncio
async def test_human_lifecycle_denial_precedes_task_state(
    actor_status, link_status,
):
    request = _request()
    context = HumanAuthorizationContext(
        actor_profile_id=request.contributor_id,
        actor_kind=ActorKind.HUMAN,
        actor_status=actor_status,
        identity_link_id=new_record_id(),
        identity_link_status=link_status,
        request_id=new_record_id(),
        correlation_id=new_record_id(),
    )
    authority = PreparedSubmissionCreationAuthorization(object(), context)
    service = TaskSubmissionCreationService(
        _Session(),
        authorization=authority,
        evaluations=None, events=None,
        admissions=None,
        contexts=task_service(_Session(), settings=get_settings()),
    )
    service._repository = SimpleNamespace(
        lock_submission_context=lambda value: pytest.fail("TASK state was revealed")
    )
    with pytest.raises(SubmissionCreationUnavailable):
        await service.create(request)


@pytest.mark.asyncio
async def test_foreign_contributor_denial_precedes_task_lookup():
    request = _request()
    context = HumanAuthorizationContext(
        actor_profile_id=new_record_id(), actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE, identity_link_id=new_record_id(),
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=new_record_id(), correlation_id=new_record_id(),
    )
    service = TaskSubmissionCreationService(
        _Session(),
        authorization=PreparedSubmissionCreationAuthorization(object(), context),
        evaluations=None, events=None,
        admissions=None,
        contexts=task_service(_Session(), settings=get_settings()),
    )
    service._repository = SimpleNamespace(
        lock_submission_context=lambda value: pytest.fail("foreign task was inspected"),
    )
    with pytest.raises(SubmissionCreationUnavailable):
        await service.create(request)


@pytest.mark.asyncio
async def test_denial_precedes_task_lock_and_all_mutation():
    class Authority:
        async def authorize(self, facts): raise SubmissionCreationUnavailable
        async def prepare(self, facts): raise AssertionError("unreachable")
        async def consume(self, handle, facts): raise AssertionError("unreachable")
        def close(self, handle): raise AssertionError("unreachable")

    service = TaskSubmissionCreationService(
        _Session(),
        authorization=Authority(),
        evaluations=None, events=None,
        admissions=None,
        contexts=task_service(_Session(), settings=get_settings()),
    )
    service._repository = SimpleNamespace(
        lock_submission_context=lambda value: pytest.fail("TASK state was revealed")
    )
    with pytest.raises(SubmissionCreationUnavailable):
        await service.create(_request())


@pytest.mark.parametrize("revocation", ["identity_link_revoked", "submitter_grant_missing"])
@pytest.mark.asyncio
async def test_fresh_authority_denial_precedes_art_and_mutation(revocation):
    request = _request()
    events = []

    class Authority:
        async def authorize(self, facts): pass
        async def prepare(self, facts):
            events.append(revocation)
            raise SubmissionCreationUnavailable("submission creation is unavailable")
        async def consume(self, handle, facts): raise AssertionError("unreachable")
        def close(self, handle): raise AssertionError("unreachable")

    class Admissions:
        async def consume(self, value):
            raise AssertionError("ART admission state was inspected")

    service = TaskSubmissionCreationService(
        _Session(),
        authorization=Authority(),
        evaluations=None, events=None,
        admissions=Admissions(),
        contexts=task_service(_Session(), settings=get_settings()),
    )
    persisted = []

    class Repository:
        async def lock_submission_context(self, value): return _context(request)
        async def get_task(self, task_id, **kwargs): return _task()
        async def add_submission(self, submission): persisted.append(submission)

    service._repository = Repository()
    # This test isolates authority sequencing, not policy validation behavior.
    service._contexts = SimpleNamespace(_load_locked_task_context=AsyncMock())
    with pytest.raises(SubmissionCreationUnavailable):
        await service.create(request)
    assert events == [revocation]
    assert persisted == []


@pytest.mark.asyncio
async def test_invalid_admission_result_denies_before_lineage_and_final_authority():
    request = _request()
    events = []

    class Authority:
        async def authorize(self, facts): events.append("authorize")
        async def prepare(self, facts):
            events.append("prepare")
            return "prepared"
        async def consume(self, handle, facts): events.append("final")
        def close(self, handle): assert handle == "prepared"

    class Admissions:
        async def consume(self, value):
            events.append("art")
            return SimpleNamespace(binding_id=None, content_id=new_record_id())

    service = TaskSubmissionCreationService(
        _Session(),
        authorization=Authority(),
        evaluations=None, events=None,
        admissions=Admissions(),
        contexts=task_service(_Session(), settings=get_settings()),
    )
    persisted = []

    class Repository:
        async def lock_submission_context(self, value): return _context(request)
        async def get_task(self, task_id, **kwargs): return _task()
        async def add_submission(self, submission): persisted.append(submission)

    service._repository = Repository()
    # This test isolates ART result validation, not policy validation behavior.
    service._contexts = SimpleNamespace(_load_locked_task_context=AsyncMock())
    with pytest.raises(RuntimeError, match="exact binding facts"):
        await service.create(request)
    assert events == ["authorize", "prepare", "art"]
    assert len(persisted) == 1
    assert persisted[0].artifact_binding_id is None


def test_hidden_composition_uses_both_active_authority_adapters() -> None:
    session = SimpleNamespace()
    context = SimpleNamespace()
    command = compose_hidden_submission_creation_command(
        session, context, request_id=new_record_id(), correlation_id=new_record_id()
    )
    assert type(command) is TransactionalSubmissionCreationCommand
    assert type(command._authorization) is PreparedSubmissionCreationAuthorization
    assert type(command._admissions) is SubmissionAdmissionConsumptionService
    assert type(command._admissions._authorization) is PreparedSubmissionBindingAuthorization


@pytest.mark.asyncio
async def test_policy_failure_closes_prepared_authority_before_any_submission_or_art_write():
    request = _request()
    authority = SimpleNamespace(
        authorize=AsyncMock(), prepare=AsyncMock(return_value=object()),
        consume=AsyncMock(), close=lambda handle: closed.append(handle),
    )
    closed = []
    admissions = SimpleNamespace(consume=AsyncMock())
    service = TaskSubmissionCreationService(
        _Session(),
        authorization=authority,
        evaluations=None, events=None,
        admissions=admissions,
        contexts=SimpleNamespace(
            _load_locked_task_context=AsyncMock(side_effect=ValueError("custody changed"))
        ),
    )
    service._repository = SimpleNamespace(
        lock_submission_context=AsyncMock(return_value=_context(request)),
        get_task=AsyncMock(return_value=_task()), add_submission=AsyncMock(),
    )
    with pytest.raises(ValueError, match="custody changed"):
        await service.create(request)
    assert closed == [authority.prepare.return_value]
    service._repository.add_submission.assert_not_awaited()
    admissions.consume.assert_not_awaited()
    authority.consume.assert_not_awaited()


def test_task_and_assignment_policy_facts_reject_substitution():
    from dataclasses import replace

    facts = _context(_request())
    assert facts.submitter_contribution_policy_version_id == facts.locked_project_context.locked_contribution_policy_version_id
    for invalid in (None, str(facts.submitter_contribution_policy_version_id), new_record_id()):
        with pytest.raises(ValueError, match="assignment contribution policy differs from task"):
            replace(facts, submitter_contribution_policy_version_id=invalid)
    for invalid in (None, str(facts.locked_project_context.locked_contribution_policy_version_id)):
        with pytest.raises(ValueError, match="task contribution policy identity is invalid"):
            replace(facts.locked_project_context, locked_contribution_policy_version_id=invalid)
