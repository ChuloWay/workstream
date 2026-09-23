"""Hidden effect proof: real AUTH causes/OUTBOX custody; synthetic feature authority."""

import pytest
from uuid import UUID, uuid4
from sqlalchemy import select

from app.adapters.tasks import (
    DenyAssignmentInvalidationAuthorization,
    TransactionalAssignmentInvalidationHandler,
)
from app.modules.outbox.api import HandlerOutcome
from app.modules.tasks.api.assignment_invalidation import (
    AssignmentInvalidationAuthority,
    assignment_invalidation_evidence_id,
)
from app.modules.tasks.models import TaskAssignment, WorkstreamTask, Submission
from app.modules.tasks.service import TaskService
from tests.submission_fixtures import seed_finalized_submission_for_checker_test
from tests.test_tasks import (
    auth_headers,
    complete_submission_payload,
    set_dev_actor,
    admit_and_grant_project_submitter,
)
from tests.test_tasks import task_client as task_client, task_database_env as task_database_env
from tests.tasks.invalidation_support import (
    SyntheticFeatureAuthority,
    setup_assignment,
    revoke,
    invoked,
    snapshot,
)


@pytest.mark.parametrize("started", [False, True])
@pytest.mark.parametrize("kind", ["grant", "suspend", "deactivate", "link"])
async def test_exact_real_cause_releases_only_pre_submit_assignment(
    task_client, monkeypatch, started, kind
):
    s = await setup_assignment(task_client, monkeypatch, started=started)
    await revoke(s, kind)
    target, envelope = await invoked(s)
    before = await snapshot(s)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    task, assignments, events = await snapshot(s)
    assert task["status"] == "ready" and task["assigned_to"] is None
    assert (
        assignments[0]["status"] == "authority_revoked"
        and assignments[0]["released_at"] is not None
    )
    assert {k: v for k, v in task.items() if k.startswith("locked_")} == {
        k: v for k, v in before[0].items() if k.startswith("locked_")
    }
    assert {k: v for k, v in assignments[0].items() if k not in {"status", "released_at"}} == {
        k: v for k, v in before[1][0].items() if k not in {"status", "released_at"}
    }
    added = [event for event in events if event["id"] not in {old["id"] for old in before[2]}]
    assert len(added) == 1 and added[0]["id"] == str(assignment_invalidation_evidence_id(target))
    assert added[0]["event_type"] == "TaskAssignmentAuthorityRevoked"
    assert all(event in events for event in before[2])
    assert [stage for stage, _ in s.trace] == ["prepare", "consume", "close"]
    after = await snapshot(s)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    assert await snapshot(s) == after
    assert len(s.trace) == 3


async def test_valid_delivery_cannot_substitute_target_or_cause(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    target, envelope = await invoked(s)
    before = await snapshot(s)
    for field in ("task_id", "assignment_id", "contributor_id", "authority_invalidation_event_id"):
        _, crossed = await invoked(s, target=target.model_copy(update={field: uuid4()}))
        assert await s.handler(crossed) is HandlerOutcome.REJECT
        assert await snapshot(s) == before
    response = await s.client.post(
        "/api/v1/projects",
        headers=auth_headers(),
        json={
            "name": "Other invalidation project",
            "slug": "other-invalidation-project",
            "description": "Isolation proof",
        },
    )
    assert response.status_code == 201, response.text
    other_project = response.json()
    _, crossed_project = await invoked(
        s, target=target.model_copy(update={"project_id": UUID(other_project["id"])})
    )
    assert await s.handler(crossed_project) is HandlerOutcome.REJECT
    assert await snapshot(s) == before
    for bad in (
        object(),
        envelope.model_copy(update={"payload_json": "{}"}),
        envelope.model_copy(update={"event_version": 2}),
        envelope.model_copy(update={"correlation_id": "forged"}),
    ):
        assert await s.handler(bad) is HandlerOutcome.REJECT
        assert await snapshot(s) == before
    assert s.trace == []
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE


async def test_hidden_authority_is_required_and_invalid_results_rollback(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    _, envelope = await invoked(s)
    before = await snapshot(s)
    denied = TransactionalAssignmentInvalidationHandler(
        s.sessions,
        observer=s.h.delivery,
        authorization_factory=lambda session: DenyAssignmentInvalidationAuthorization(),
    )
    assert await denied(envelope) is HandlerOutcome.REJECT
    for result in (
        None,
        AssignmentInvalidationAuthority("not-a-uuid", uuid4()),
        AssignmentInvalidationAuthority(uuid4(), "not-a-uuid"),
    ):

        class InvalidAuthority(SyntheticFeatureAuthority):
            async def consume(self, handle, facts):
                return result

        bad = TransactionalAssignmentInvalidationHandler(
            s.sessions,
            observer=s.h.delivery,
            authorization_factory=lambda session: InvalidAuthority([]),
        )
        assert await bad(envelope) is HandlerOutcome.REJECT
        assert await snapshot(s) == before


async def test_audit_failure_rolls_back_every_effect(task_client, monkeypatch):
    from app.adapters.audit import _AssignmentInvalidationAudit

    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    _, envelope = await invoked(s)
    before = await snapshot(s)
    original = _AssignmentInvalidationAudit.record_release

    async def fail_after_evidence(owner, evidence):
        await original(owner, evidence)
        raise RuntimeError("test failure after effect and evidence flush")

    with monkeypatch.context() as patch:
        patch.setattr(_AssignmentInvalidationAudit, "record_release", fail_after_evidence)
        with pytest.raises(RuntimeError, match="after effect"):
            await s.handler(envelope)
    assert await snapshot(s) == before
    assert s.trace[-1][0] == "close"
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE


async def test_old_delivery_cannot_release_real_replacement_claim(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s, "suspend")
    target, envelope = await invoked(s)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    before_restore = await snapshot(s)
    response = await s.client.post(
        f"/api/v1/actors/{s.grant['actor_profile_id']}/reactivate",
        headers=auth_headers(),
        json={"reason": "Restore actor, not prior work"},
    )
    assert response.status_code == 200, response.text
    assert await snapshot(s) == before_restore
    set_dev_actor(monkeypatch, roles="viewer", subject="invalidation-submitter")
    claimed = await s.client.post(f"/api/v1/tasks/{s.task['id']}/claim", headers=auth_headers())
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["assignment"]["id"] != s.assignment["id"]
    after = await snapshot(s)
    # A fresh transport event for the same immutable cause still addresses only the old assignment.
    _, duplicate = await invoked(s, target=target)
    assert await s.handler(duplicate) is HandlerOutcome.ACKNOWLEDGE
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    assert await snapshot(s) == after


async def test_released_work_can_be_claimed_by_another_eligible_contributor(
    task_client, monkeypatch
):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    _, envelope = await invoked(s)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    other = await admit_and_grant_project_submitter(
        s.client, monkeypatch, s.project["id"], "next-contributor"
    )
    claim = await s.client.post(f"/api/v1/tasks/{s.task['id']}/claim", headers=auth_headers())
    assert claim.status_code == 200, claim.text
    task, assignments, _ = await snapshot(s)
    assert task["assigned_to"] == other["actor_profile_id"] and task["status"] == "claimed"
    assert {row["status"] for row in assignments} == {"active", "authority_revoked"}


async def test_existing_submission_and_revision_history_are_never_released(
    task_client, monkeypatch
):
    s = await setup_assignment(task_client, monkeypatch, started=True)

    async def hold_dispatch(*args, **kwargs):
        pass

    # Reuse the admitted downstream packet fixture; this is not new ART intake proof.
    monkeypatch.setattr(TaskService, "_enqueue_pre_review_gate_after_commit", hold_dispatch)
    submission_id = await seed_finalized_submission_for_checker_test(
        s.task["id"], complete_submission_payload()
    )
    await revoke(s)
    _, envelope = await invoked(s)
    for state in (
        "submitted",
        "evaluation_pending",
        "review_pending",
        "needs_revision",
        "in_progress",
    ):
        async with s.sessions() as session, session.begin():
            task = await session.get(WorkstreamTask, s.task["id"])
            task.status = state  # Last case isolates the independent existing-Submission guard.
        before = await snapshot(s)
        async with s.sessions() as session:
            submission_before = dict(
                (
                    await session.execute(
                        select(Submission.__table__).where(Submission.id == submission_id)
                    )
                )
                .mappings()
                .one()
            )
        assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
        assert await snapshot(s) == before
        async with s.sessions() as session:
            assert (
                dict(
                    (
                        await session.execute(
                            select(Submission.__table__).where(Submission.id == submission_id)
                        )
                    )
                    .mappings()
                    .one()
                )
                == submission_before
            )
    assert s.trace == []


async def test_inconsistent_assignment_cannot_be_released(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    _, envelope = await invoked(s)
    for kind in ("status", "owner", "released"):
        async with s.sessions() as session, session.begin():
            task = await session.get(WorkstreamTask, s.task["id"])
            assignment = await session.get(TaskAssignment, s.assignment["id"])
            task.assigned_to = None if kind == "owner" else s.grant["actor_profile_id"]
            assignment.status = "authority_revoked" if kind == "status" else "active"
            assignment.released_at = envelope.claim.claimed_at if kind == "released" else None
        before = await snapshot(s)
        assert await s.handler(envelope) is HandlerOutcome.REJECT
        assert await snapshot(s) == before
    assert s.trace == []


async def test_release_requires_root_transaction_and_exact_prior_receipt(task_client, monkeypatch):
    from types import SimpleNamespace
    from app.adapters.audit import assignment_invalidation_audit, committed_authority_invalidation
    from app.adapters.outbox import outbox_invocation_fence
    from app.modules.audit.repository import AuditRepository
    from app.modules.tasks.assignment_invalidation import AssignmentInvalidationOperation
    from app.modules.tasks.api.assignment_invalidation import AssignmentInvalidationUnavailable
    from app.modules.tasks.models import AuditEvent

    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s)
    target, envelope = await invoked(s)
    async with s.sessions() as session:
        operation = AssignmentInvalidationOperation(
            session,
            observer=s.h.delivery,
            fence=outbox_invocation_fence(session),
            causes=committed_authority_invalidation(s.sessions),
            authorization=SyntheticFeatureAuthority([]),
            audit=assignment_invalidation_audit(session),
        )
        with pytest.raises(AssignmentInvalidationUnavailable, match="root transaction"):
            await operation.reconcile(envelope)
        async with session.begin(), session.begin_nested():
            with pytest.raises(AssignmentInvalidationUnavailable, match="root transaction"):
                await operation.reconcile(envelope)
    assert await s.handler(envelope) is HandlerOutcome.ACKNOWLEDGE
    before = await snapshot(s)
    async with s.sessions() as session:
        row = await session.get(AuditEvent, str(assignment_invalidation_evidence_id(target)))
        original = {column.key: getattr(row, column.key) for column in AuditEvent.__table__.columns}
    for altered in (
        {**original, "event_payload": {"references": {}}},
        {**original, "entity_id": str(uuid4())},
    ):

        async def bad_receipt(owner, event_id):
            assert event_id == assignment_invalidation_evidence_id(target)
            return SimpleNamespace(**altered)

        with monkeypatch.context() as patch:
            patch.setattr(AuditRepository, "lifecycle_event", bad_receipt)
            assert await s.handler(envelope) is HandlerOutcome.REJECT
        assert await snapshot(s) == before
    async with s.sessions() as session, session.begin():
        assignment = await session.get(TaskAssignment, s.assignment["id"])
        assignment.released_at = None
    inconsistent = await snapshot(s)
    assert await s.handler(envelope) is HandlerOutcome.REJECT
    assert await snapshot(s) == inconsistent
