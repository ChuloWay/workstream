"""Paused revision clocks preserve allowance and publish durable PM attention."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.identifiers import new_record_id
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.api.revision import RevisionCandidate, RevisionContextSnapshot
from app.modules.tasks.api.revision_expiry import REVISION_CONTEXT_BLOCKED_EVENT, REVISION_EXPIRY_EVENT
from app.modules.tasks.api.transition_audit import TaskPolicyLineage
from app.modules.tasks.post_submit_routing.models import TaskPostSubmitRoutingManifest
from app.modules.tasks.revision.expiry_event import revision_preparation_event
from app.modules.tasks.revision.models import TaskRevisionPreparation
from app.modules.tasks.revision.service import candidate_from_packet, project_revision
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.post_submit_routing.support import activate_successor_guide
from tests.tasks.test_public_submission_intake import _client
from tests.test_submission_predecessor_custody import _fixture_revision_context


def _paused_row():
    """Build strict public lineage for a pure paused-clock projection proof."""
    start = datetime(2026, 10, 14, tzinfo=UTC)
    lineage = TaskPolicyLineage(**{
        name: new_record_id() if name.endswith("_id") else
        1 if name.endswith("_generation") else
        "sha256:" + "a" * 64 if name.endswith(("_hash", "_bundle_hash")) else "v1"
        for name in TaskPolicyLineage.model_fields
    })
    prior = RevisionContextSnapshot(
        guide_id=new_record_id(), activation_operation_id=new_record_id(),
        activation_generation=1, activated_at=start, lineage=lineage,
    )
    candidate = RevisionCandidate(
        prior=prior, target=None, max_revision_rounds=2, revision_deadline_hours=24,
    )
    return SimpleNamespace(
        id=new_record_id(), preparation_sha256="sha256:" + "b" * 64,
        predecessor_id=None, submission_id=str(new_record_id()), routing_manifest_id=new_record_id(),
        sequence=1, next_revision_round=1, max_revision_rounds=2, requested_at=start,
        deadline_at=None, remaining_microseconds=86_400_000_000,
        outcome="blocked", blocked_reason="context_blocked",
        packet={"candidate": candidate.model_dump(mode="json")},
    )


def test_paused_projection_never_spends_allowance_as_wall_time_passes():
    row = _paused_row()
    first = project_revision(row, row.requested_at)
    later = project_revision(row, row.requested_at + timedelta(days=100))
    assert first == later
    assert later.clock_state == "paused" and later.deadline_at is None
    assert later.remaining_microseconds == 86_400_000_000
    assert later.disposition == "context_blocked"
    wire = later.model_dump(mode="json", exclude_none=True)
    assert wire["deadline_at"] is None
    assert wire["remaining_microseconds"] == row.remaining_microseconds


def test_retained_lower_target_limit_is_setup_blocked_and_respects_running_deadline():
    row = _paused_row()
    candidate = candidate_from_packet(row.packet)
    target = candidate.prior.model_copy(update={
        "activation_operation_id": new_record_id(), "activation_generation": 2,
        "lineage": candidate.prior.lineage.model_copy(update={
            "locked_revision_policy_id": new_record_id(),
            "locked_revision_policy_hash": "sha256:" + "c" * 64,
        }),
    })
    row.packet["candidate"] = candidate.model_copy(update={
        "target": target, "target_max_revision_rounds": 1, "target_post_policy_json": "{}",
    }).model_dump(mode="json")
    row.next_revision_round = 2
    row.blocked_reason = "revision_limit_reached"
    row.deadline_at = row.requested_at + timedelta(hours=24)
    row.remaining_microseconds = None
    before = project_revision(row, row.requested_at)
    assert before.disposition == "context_blocked" and before.clock_state == "running"
    assert project_revision(row, row.deadline_at).disposition == "revision_deadline_expired"
    row.next_revision_round = row.max_revision_rounds + 1
    assert project_revision(row, row.deadline_at).disposition == "revision_limit_reached"


def test_resumed_timer_keeps_root_identity_but_selects_new_effective_deadline():
    root = _paused_row()
    root.project_id, root.task_id = str(new_record_id()), str(new_record_id())
    root.assignment_id, root.contributor_id = str(new_record_id()), str(new_record_id())
    root.audit_event_id, root.authorization_decision_id = new_record_id(), new_record_id()
    manifest = SimpleNamespace(id=root.routing_manifest_id, outcome_event_id=new_record_id())
    notice = revision_preparation_event(manifest, root)
    assert notice.event_type == REVISION_CONTEXT_BLOCKED_EVENT
    assert notice.not_before_at is None
    assert notice.payload["remaining_microseconds"] == root.remaining_microseconds
    head = SimpleNamespace(**vars(root))
    head.id, head.predecessor_id, head.sequence = new_record_id(), root.id, 2
    head.deadline_at = root.requested_at + timedelta(days=100, hours=24)
    head.remaining_microseconds = None
    event = revision_preparation_event(manifest, root, head)
    assert event.event_type == REVISION_EXPIRY_EVENT
    assert event.idempotency_key == f"task.revision.expire:{manifest.id}:{head.id}"
    assert event.payload["root_preparation_id"] == str(root.id)
    assert event.payload["root_preparation_sha256"] == root.preparation_sha256
    assert event.not_before_at == head.deadline_at


async def _read_prep(h, preparation_id=None):
    async with h.factory() as session:
        return await session.get(TaskRevisionPreparation, preparation_id or h.revision_preparation_id)


async def _repair(client, h, parent, *, key=None):
    original = AuthorizedTaskCommands.repair_revision_context
    failures = []

    async def observed(command, *args, **kwargs):
        try:
            return await original(command, *args, **kwargs)
        except SQLAlchemyError as exc:
            failures.append(exc)
            raise

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(AuthorizedTaskCommands, "repair_revision_context", observed)
        response = await client.post(
            f"/api/v1/projects/{h.request.project_id}/tasks/{h.request.task_id}/revision-context/repair",
            json={"parent_preparation_id": str(parent.id),
                  "parent_preparation_sha256": parent.preparation_sha256,
                  "reason": "Adopt the complete current approved context"},
            headers={"Idempotency-Key": str(key or new_record_id())},
        )
    if failures:
        raise AssertionError("real PM repair database failure") from failures[0]
    assert response.status_code == 200, response.text
    return response.json()


async def test_blocked_initial_context_pauses_full_budget_and_is_visible_to_pm(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        await activate_successor_guide(h, max_revision_rounds=0)
        source_id = await _fixture_revision_context(h)
        root = await _read_prep(h)
        assert root.outcome == "blocked" and root.blocked_reason == "context_blocked"
        policy_budget = root.packet["candidate"]["revision_deadline_hours"] * 3_600_000_000
        assert root.deadline_at is None and root.remaining_microseconds == policy_budget
        async with h.factory() as session:
            manifest = await session.get(TaskPostSubmitRoutingManifest, source_id)
            expected = revision_preparation_event(manifest, root)
            notices = (await session.scalars(select(OutboxEvent).where(
                OutboxEvent.idempotency_key == expected.idempotency_key,
            ))).all()
            assert len(notices) == 1 and notices[0].payload == expected.payload
            assert await session.scalar(text(
                "SELECT count(*) FROM public.outbox_events WHERE event_type=:type "
                "AND correlation_id=:source"
            ), {"type": REVISION_EXPIRY_EVENT, "source": str(source_id)}) == 0
        assert await _fixture_revision_context(h) == source_id
        assert (await _read_prep(h)).preparation_sha256 == root.preparation_sha256
        async with _client(h, monkeypatch, isolated_database_env) as client:
            response = await client.get(
                f"/api/v1/projects/{h.request.project_id}/tasks/{h.request.task_id}/work-context",
            )
            assert response.status_code == 200, response.text
            view = response.json()["task"]["revision_context"]
            assert view["clock_state"] == "paused" and view["deadline_at"] is None
            assert view["remaining_microseconds"] == root.remaining_microseconds


async def test_pm_pause_and_resume_preserve_only_remaining_database_time(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        root = await _read_prep(h)
        await activate_successor_guide(h, max_revision_rounds=0)
        async with _client(h, monkeypatch, isolated_database_env) as client:
            paused_view = await _repair(client, h, root)
            paused = await _read_prep(h, UUID(paused_view["preparation_id"]))
            expected_remaining = (root.deadline_at - paused.clock_observed_at) // timedelta(microseconds=1)
            assert paused.deadline_at is None
            original_budget = (root.deadline_at - root.requested_at) // timedelta(microseconds=1)
            assert 0 < paused.remaining_microseconds == expected_remaining < original_budget
            await activate_successor_guide(h, max_revision_rounds=2, version="v3")
            key = new_record_id()
            resumed_view = await _repair(client, h, paused, key=key)
            resumed = await _read_prep(h, UUID(resumed_view["preparation_id"]))
            assert resumed.deadline_at == resumed.clock_observed_at + timedelta(
                microseconds=paused.remaining_microseconds,
            )
            assert resumed.deadline_at > root.deadline_at
            assert resumed.remaining_microseconds is None and resumed.outcome == "rebased"
            assert await _repair(client, h, paused, key=key) == resumed_view
        async with h.factory() as session:
            heads = (await session.scalars(select(TaskRevisionPreparation).where(
                TaskRevisionPreparation.routing_manifest_id == source_id,
            ).order_by(TaskRevisionPreparation.sequence))).all()
            assert [head.id for head in heads] == [root.id, paused.id, resumed.id]
            assert heads[0].deadline_at == root.deadline_at
            manifest = await session.get(TaskPostSubmitRoutingManifest, source_id)
            for head in heads:
                expected = revision_preparation_event(manifest, root, head)
                event = await session.scalar(select(OutboxEvent).where(
                    OutboxEvent.idempotency_key == expected.idempotency_key,
                ))
                assert event is not None and event.payload == expected.payload
