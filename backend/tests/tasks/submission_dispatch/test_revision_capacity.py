"""Locked revision caps across real checker completion, intake, creation and SQL."""

import json
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.adapters.checkers import evaluation_coordinator
from app.core.identifiers import new_record_id
from app.modules.checkers.models import CheckerRun
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.models import Submission
from tests.checkers.execution.support import ControlledSelectedExecution, live_executor
from tests.tasks.post_submit_routing.outcome_support import invoked_completion
from tests.tasks.post_submit_routing.remediation_support import remediation_source
from tests.tasks.post_submit_routing.support import revision_archive
from tests.tasks.submission_dispatch.test_replacement_creation import (
    _creation_snapshot, _ready_replacement,
)
from tests.tasks.test_public_submission_intake import _client, _payload
from tests.test_submission_predecessor_custody import _fixture_revision_context


async def _fail_current_submission(h):
    """Complete the actual reserved successor using controlled external work failure."""
    async with h.factory() as session, session.begin():
        reserved = await evaluation_coordinator(session).read_reserved_evaluation(
            project_id=h.request.project_id, task_id=h.request.task_id,
            submission_id=h.created.submission_id,
            request_id=h.created.evaluation_request_id,
        )
    h.request = reserved.request
    h.result = await live_executor(
        h, selected_execution=ControlledSelectedExecution(verdict="failed"),
    ).evaluate_post_submission(h.request)
    async with h.factory() as session:
        run = await session.get(CheckerRun, str(h.result.attempt_id))
        assert run.routing_recommendation == "needs_revision"
        event = await session.scalar(select(OutboxEvent).where(
            OutboxEvent.event_id == run.completion_event_id,
        ))
        h.source = {"completion_event_id": event.event_id}
    h.envelope = await invoked_completion(h)
    await _fixture_revision_context(h)


async def test_two_revisions_then_public_and_sql_refusal(
    tmp_path, isolated_database_env, monkeypatch,
):
    """Initial0 and revisions1/2 commit; preparation/POST/SQL cannot create round3."""
    from app.modules.tasks.schemas import AdmissionBackedSubmissionResponse
    from app.modules.tasks.revision.models import TaskRevisionPreparation

    async with remediation_source(tmp_path, isolated_database_env) as h:
        await _fixture_revision_context(h)
        async with h.factory() as session:
            first_window = await session.get(TaskRevisionPreparation, h.revision_preparation_id)
            previous_start = first_window.requested_at
            window_length = first_window.deadline_at - previous_start
            assert await session.scalar(text(
                "SELECT p.max_revision_rounds FROM public.revision_policies p "
                "JOIN public.workstream_tasks t ON t.locked_revision_policy_id=p.id "
                "WHERE t.id=:id"
            ), {"id": h.request.task_id}) == 2
        initial_id = h.created.submission_id
        saved_payload = None
        async with _client(h, monkeypatch, isolated_database_env) as client:
            route = f"/api/v1/tasks/{h.request.task_id}/submissions"
            for round_number in (1, 2):
                h.data = revision_archive(h.data)
                prepared, admission = await _ready_replacement(h, h.data)
                payload = _payload(prepared, admission)
                response = await client.post(route, json=payload)
                assert response.status_code == 201, response.text
                assert response.json()["submission_version"] == round_number + 1
                h.created = AdmissionBackedSubmissionResponse.model_validate(response.json())
                saved_payload = payload
                saved_response = response.json()
                await _fail_current_submission(h)
                async with h.factory() as session:
                    window = await session.get(TaskRevisionPreparation, h.revision_preparation_id)
                    assert window.requested_at > previous_start
                    assert window.deadline_at - window.requested_at == window_length
                    assert window.next_revision_round == round_number + 1
                    previous_start = window.requested_at

            before = await _creation_snapshot(h)
            # Empty/malformed ZIP would fail archive checks if capacity were checked too late.
            denied = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/submission-bundle-preparations",
                headers={
                    "Content-Type": "application/zip",
                    "X-Task-Assignment-Id": str(h.request.assignment_id),
                    "X-Predecessor-Submission-Id": str(h.created.submission_id),
                    "Idempotency-Key": str(new_record_id()),
                    "X-Revision-Preparation-Id": str(h.revision_preparation_id),
                    "X-Revision-Preparation-Sha256": h.revision_preparation_sha256,
                }, content=b"not a zip",
            )
            assert denied.status_code == 409, denied.text
            assert denied.json()["error"]["code"] == "revision_limit_reached"
            assert await _creation_snapshot(h) == before
            replay = await client.post(route, json=saved_payload)
            assert replay.status_code == 201, replay.text
            assert replay.json() == saved_response

        async with h.factory() as session:
            original = await session.scalar(text(
                "SELECT to_jsonb(s) FROM public.submissions s WHERE id=:id"
            ), {"id": h.created.submission_id})
        # Intake now rejects excess rounds at the database boundary too. A raw
        # INSERT cannot bypass the cap even before an admission is selected.
        forbidden = dict(original, id=str(new_record_id()), version=4,
                         supersedes_submission_id=str(h.created.submission_id))
        with pytest.raises(IntegrityError, match="revision_limit_reached"):
            async with h.factory() as session, session.begin():
                await session.execute(text(
                    "INSERT INTO public.submissions SELECT * FROM "
                    "jsonb_populate_record(NULL::public.submissions, CAST(:row AS jsonb))"
                ), {"row": json.dumps(forbidden)})
        assert await _creation_snapshot(h) == before
        for version in (0, -1):
            forged = dict(original, id=str(new_record_id()), version=version,
                          supersedes_submission_id=str(h.created.submission_id),
                          submission_bundle_admission_id=None, artifact_binding_id=None,
                          artifact_content_id=None)
            with pytest.raises(IntegrityError, match="submission_revision_lineage_invalid"):
                async with h.factory() as session, session.begin():
                    await session.execute(text(
                        "INSERT INTO public.submissions SELECT * FROM "
                        "jsonb_populate_record(NULL::public.submissions, CAST(:row AS jsonb))"
                    ), {"row": json.dumps(forged)})
        async with h.factory() as session:
            rows = (await session.scalars(select(Submission).order_by(Submission.version))).all()
            assert [row.version for row in rows] == [1, 2, 3]
            assert rows[0].id == str(initial_id)
            assert rows[1].supersedes_submission_id == rows[0].id
            assert rows[2].supersedes_submission_id == rows[1].id


def test_revision_projection_preserves_deadline_and_distinguishes_policy_changes():
    """JSON recovery preserves exact UUIDs, deadlines and bounded contributor changes."""
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace
    from app.modules.tasks.api.revision import RevisionCandidate, RevisionContextSnapshot
    from app.modules.tasks.api.transition_audit import TaskPolicyLineage
    from app.modules.tasks.revision.service import project_revision

    start = datetime(2026, 10, 14, tzinfo=UTC)
    fields = {
        name: new_record_id() if name.endswith("_id") else
        1 if name.endswith("_generation") else
        "sha256:" + "a" * 64 if name.endswith(("_hash", "_bundle_hash")) else "v1"
        for name in TaskPolicyLineage.model_fields
    }
    prior = RevisionContextSnapshot(
        guide_id=new_record_id(), activation_operation_id=new_record_id(),
        activation_generation=1, activated_at=start - timedelta(days=1),
        lineage=TaskPolicyLineage(**fields),
    )
    candidate = RevisionCandidate(
        prior=prior, target=prior, target_post_policy_json="{}",
        max_revision_rounds=2, target_max_revision_rounds=2, revision_deadline_hours=24,
    )
    row = SimpleNamespace(
        id=new_record_id(), preparation_sha256="sha256:" + "b" * 64,
        predecessor_id=None, submission_id=str(new_record_id()), routing_manifest_id=new_record_id(),
        sequence=1, next_revision_round=1, max_revision_rounds=2, requested_at=start,
        deadline_at=start + timedelta(hours=24), outcome="kept", blocked_reason=None,
        packet={"candidate": candidate.model_dump(mode="json")},
    )
    first = project_revision(row, row.deadline_at - timedelta(microseconds=1))
    assert first.disposition == "ready" and first.changes == ()
    assert first.direction == "kept"
    boundary = project_revision(row, row.deadline_at)
    assert boundary.disposition == "revision_deadline_expired"
    assert boundary.requested_at == first.requested_at and boundary.deadline_at == first.deadline_at
    assert "target_post_policy_json" not in boundary.model_dump_json()

    target = prior.model_copy(update={
        "activation_operation_id": new_record_id(), "activation_generation": 2,
        "activated_at": start,
        "lineage": prior.lineage.model_copy(update={"locked_contribution_policy_version_id": new_record_id()}),
    })
    row.packet = {"candidate": candidate.model_copy(update={"target": target}).model_dump(mode="json")}
    row.outcome = "rebased"
    row.predecessor_id, row.id = row.id, new_record_id()
    row.sequence = 2
    repaired = project_revision(row, start + timedelta(hours=23))
    assert repaired.deadline_at == first.deadline_at
    assert repaired.direction == "forward"
    assert [change.component for change in repaired.changes] == ["guide", "contribution"]
    assert repaired.prior == prior and repaired.target == target
    row.blocked_reason = "revision_limit_reached"
    row.outcome = "blocked"
    assert project_revision(row, row.deadline_at).disposition == "revision_limit_reached"


async def test_rebase_keeps_history_and_requires_exact_acknowledgement(
    tmp_path, isolated_database_env, monkeypatch,
):
    """A real v2 activation rebases only the next attempt and preserves v1 evidence."""
    from app.modules.tasks.models import WorkstreamTask, TaskAssignment
    from app.modules.tasks.revision.models import TaskRevisionPreparation
    from tests.tasks.post_submit_routing.support import activate_successor_guide

    async with remediation_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            original = await session.scalar(text(
                "SELECT to_jsonb(s) FROM public.submissions s WHERE id=:id"
            ), {"id": h.created.submission_id})
            retained_run = await session.scalar(text(
                "SELECT to_jsonb(r) FROM public.checker_runs r WHERE id=:id"
            ), {"id": h.result.attempt_id})
        await activate_successor_guide(h)
        source_id = await _fixture_revision_context(h)
        async with h.factory() as session:
            preparation = await session.get(TaskRevisionPreparation, h.revision_preparation_id)
            assert preparation.outcome == "rebased"
            assert preparation.next_revision_round == 1
            task = await session.get(WorkstreamTask, str(h.request.task_id))
            assignment = await session.get(TaskAssignment, str(h.request.assignment_id))
            assert task.locked_guide_version == "v2"
            assert str(task.locked_contribution_policy_version_id) == str(assignment.submitter_contribution_policy_version_id)
            packet = preparation.packet
            assert packet["candidate"]["prior"]["lineage"]["locked_guide_version"] != "v2"
            assert packet["candidate"]["target"]["lineage"]["locked_guide_version"] == "v2"
            frozen = (preparation.id, preparation.preparation_sha256, preparation.requested_at, preparation.deadline_at)
        # Exact worker redelivery never selects a fresh preparation or window.
        assert await _fixture_revision_context(h) == source_id
        async with h.factory() as session:
            rows = (await session.scalars(select(TaskRevisionPreparation))).all()
            assert len(rows) == 1
            assert (rows[0].id, rows[0].preparation_sha256, rows[0].requested_at, rows[0].deadline_at) == frozen
        async with _client(h, monkeypatch, isolated_database_env) as client:
            context = await client.get(f"/api/v1/tasks/{h.request.task_id}/work-context")
            assert context.status_code == 200, context.text
            view = context.json()["revision_context"]
            assert view["preparation_id"] == str(h.revision_preparation_id)
            assert view["outcome"] == "rebased" and view["disposition"] == "ready"
            assert "contribution" in {change["component"] for change in view["changes"]}
            replayed_initial = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/submissions",
                json=_payload(h.creation_request, h.creation_request.admission_id),
            )
            assert replayed_initial.status_code == 201, replayed_initial.text
            assert replayed_initial.json()["submission_id"] == str(h.created.submission_id)
            assert replayed_initial.json()["submission_version"] == 1
            before = await _creation_snapshot(h)
            refused = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/submission-bundle-preparations",
                headers={
                    "Content-Type": "application/zip",
                    "X-Task-Assignment-Id": str(h.request.assignment_id),
                    "X-Predecessor-Submission-Id": str(h.created.submission_id),
                    "X-Revision-Preparation-Id": str(new_record_id()),
                    "X-Revision-Preparation-Sha256": h.revision_preparation_sha256,
                    "Idempotency-Key": str(new_record_id()),
                }, content=b"not a zip",
            )
            assert refused.status_code == 409, refused.text
            assert refused.json()["error"]["code"] == "revision_context_changed"
            assert await _creation_snapshot(h) == before
            prepared, admission = await _ready_replacement(h, revision_archive(h.data))
            created = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/submissions", json=_payload(prepared, admission),
            )
            assert created.status_code == 201, created.text
            assert created.json()["submission_version"] == 2
        async with h.factory() as session:
            assert await session.scalar(text(
                "SELECT to_jsonb(s) FROM public.submissions s WHERE id=:id"
            ), {"id": h.created.submission_id}) == original
            assert await session.scalar(text(
                "SELECT to_jsonb(r) FROM public.checker_runs r WHERE id=:id"
            ), {"id": h.result.attempt_id}) == retained_run
            assert await session.scalar(text(
                "SELECT bool_and(public.submission_dispatch_valid(d)) FROM public.submission_dispatches d"
            )) is True
        for mutation in (
            "UPDATE public.task_revision_preparations SET deadline_at=deadline_at+interval '1 hour' WHERE id=:id",
            "DELETE FROM public.task_revision_preparations WHERE id=:id",
        ):
            with pytest.raises(DBAPIError, match="immutable"):
                async with h.factory() as session, session.begin():
                    await session.execute(text(mutation), {"id": h.revision_preparation_id})


async def test_pm_recovers_retained_source_and_repairs_without_resetting_window(
    tmp_path, isolated_database_env, monkeypatch,
):
    """Explicit PM recovery and later rebase keep the original failure's window."""
    from app.modules.tasks.revision.models import TaskRevisionPreparation
    from tests.tasks.post_submit_routing.support import activate_successor_guide

    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        async with h.factory() as session:
            original = await session.get(TaskRevisionPreparation, h.revision_preparation_id)
            anchor, deadline, limit = original.requested_at, original.deadline_at, original.max_revision_rounds
        # Arrange only the retained pre-preparation schema state in this owned
        # test database. The real source, authority, Task and evidence stay intact.
        # The protection itself is tested above; recovery runs with it enabled.
        async with h.factory() as session, session.begin():
            await session.execute(text("ALTER TABLE public.task_revision_preparations DISABLE TRIGGER revision_preparation_immutable"))
            await session.execute(text("DELETE FROM public.task_revision_preparations WHERE id=:id"), {"id": h.revision_preparation_id})
            await session.execute(text("ALTER TABLE public.task_revision_preparations ENABLE TRIGGER revision_preparation_immutable"))
        async with _client(h, monkeypatch, isolated_database_env) as client:
            route = f"/api/v1/projects/{h.request.project_id}/tasks/{h.request.task_id}/revision-context/repair"
            root_payload = {"routing_manifest_id": str(source_id), "reason": "Recover the retained revision source"}
            root_key = str(new_record_id())
            response = await client.post(route, json=root_payload, headers={"Idempotency-Key": root_key})
            assert response.status_code == 200, response.text
            root = response.json()
            assert root["sequence"] == 1 and root["outcome"] == "kept"
            assert root["source_routing_manifest_id"] == str(source_id)
            async with h.factory() as session:
                restored = await session.get(TaskRevisionPreparation, UUID(root["preparation_id"]))
                assert (restored.requested_at, restored.deadline_at, restored.max_revision_rounds) == (anchor, deadline, limit)
                assert restored.repair_actor_id == h.actor_context.actor_profile_id
            replay = await client.post(route, json=root_payload, headers={"Idempotency-Key": root_key})
            assert replay.status_code == 200, replay.text
            assert replay.json() == root
            await activate_successor_guide(h)
            child_payload = {
                "parent_preparation_id": root["preparation_id"],
                "parent_preparation_sha256": root["preparation_sha256"],
                "reason": "Adopt the complete corrected active guide",
            }
            child_key = str(new_record_id())
            repaired = await client.post(route, json=child_payload, headers={"Idempotency-Key": child_key})
            assert repaired.status_code == 200, repaired.text
            child = repaired.json()
            assert child["sequence"] == 2 and child["outcome"] == "rebased"
            assert child["requested_at"] == root["requested_at"]
            assert child["deadline_at"] == root["deadline_at"]
            assert child["max_revision_rounds"] == root["max_revision_rounds"]
            stale = await client.post(route, json=child_payload, headers={"Idempotency-Key": str(new_record_id())})
            assert stale.status_code == 409, stale.text
            h.revision_preparation_id = UUID(child["preparation_id"])
            h.revision_preparation_sha256 = child["preparation_sha256"]
            prepared, admission = await _ready_replacement(h, revision_archive(h.data))
            created = await client.post(f"/api/v1/tasks/{h.request.task_id}/submissions", json=_payload(prepared, admission))
            assert created.status_code == 201, created.text
            replay = await client.post(route, json=child_payload, headers={"Idempotency-Key": child_key})
            assert replay.status_code == 200, replay.text
            assert replay.json()["preparation_id"] == child["preparation_id"]
            assert replay.json()["deadline_at"] == root["deadline_at"]
            assert replay.json()["disposition"] == "context_blocked"
        async with h.factory() as session:
            rows = (await session.scalars(select(TaskRevisionPreparation).order_by(TaskRevisionPreparation.sequence))).all()
            assert len(rows) == 2
            assert rows[1].predecessor_id == rows[0].id
            assert rows[0].packet["candidate"]["target"]["lineage"]["locked_guide_version"] != "v2"


async def test_pm_repair_refuses_superseded_checker_source(
    tmp_path, isolated_database_env, monkeypatch,
):
    """Both repair forms conceal stale eligibility behind fresh PM authority."""
    from tests.tasks.post_submit_routing.support import next_request

    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        successor = await next_request(h)
        async with h.factory() as session, session.begin():
            await evaluation_coordinator(session).reserve_current_evaluation(successor)
        async with _client(h, monkeypatch, isolated_database_env) as client:
            route = f"/api/v1/projects/{h.request.project_id}/tasks/{h.request.task_id}/revision-context/repair"
            payloads = (
                {"parent_preparation_id": str(h.revision_preparation_id),
                 "parent_preparation_sha256": h.revision_preparation_sha256,
                 "reason": "Try to repair a superseded result"},
                {"routing_manifest_id": str(source_id),
                 "reason": "Try to recover a superseded result"},
            )
            for index, payload in enumerate(payloads):
                if index:
                    # Represent a retained source without a preparation. Only
                    # fixture setup bypasses immutability; the request does not.
                    async with h.factory() as session, session.begin():
                        await session.execute(text("ALTER TABLE public.task_revision_preparations DISABLE TRIGGER revision_preparation_immutable"))
                        await session.execute(text("DELETE FROM public.task_revision_preparations WHERE id=:id"), {"id": h.revision_preparation_id})
                        await session.execute(text("ALTER TABLE public.task_revision_preparations ENABLE TRIGGER revision_preparation_immutable"))
                async with h.factory() as session:
                    before = (await session.execute(text(
                        "SELECT (SELECT count(*) FROM public.task_revision_preparations), "
                        "(SELECT count(*) FROM public.audit_events)"
                    ))).one()
                response = await client.post(route, json=payload, headers={"Idempotency-Key": str(new_record_id())})
                assert response.status_code == 409, response.text
                assert response.json()["error"]["code"] == "revision_context_changed"
                async with h.factory() as session:
                    assert (await session.execute(text(
                        "SELECT (SELECT count(*) FROM public.task_revision_preparations), "
                        "(SELECT count(*) FROM public.audit_events)"
                    ))).one() == before


async def test_expired_retained_failure_recovers_without_a_new_window(
    tmp_path, isolated_database_env, monkeypatch,
):
    """Real database time blocks an old failure without cancelling the task."""
    from app.modules.tasks.revision.models import TaskRevisionPreparation

    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        # Model a retained source from before preparations existed, already past
        # its policy deadline. Restore every guard before exercising public APIs.
        async with h.factory() as session, session.begin():
            await session.execute(text("ALTER TABLE public.task_revision_preparations DISABLE TRIGGER revision_preparation_immutable"))
            await session.execute(text("DELETE FROM public.task_revision_preparations WHERE id=:id"), {"id": h.revision_preparation_id})
            await session.execute(text("ALTER TABLE public.task_revision_preparations ENABLE TRIGGER revision_preparation_immutable"))
            await session.execute(text("ALTER TABLE public.task_post_submit_routing_manifests DISABLE TRIGGER task_routing_manifest_immutable"))
            anchor, deadline = (await session.execute(text("""
                UPDATE public.task_post_submit_routing_manifests m
                SET created_at=clock_timestamp()-make_interval(hours => p.revision_deadline_hours+1)
                FROM public.submissions s JOIN public.revision_policies p ON p.id=s.locked_revision_policy_id
                WHERE m.id=:id AND s.id=m.submission_id
                RETURNING m.created_at, m.created_at+make_interval(hours => p.revision_deadline_hours)
            """), {"id": source_id})).one()
            await session.execute(text("ALTER TABLE public.task_post_submit_routing_manifests ENABLE TRIGGER task_routing_manifest_immutable"))
            assert await session.scalar(text(
                "SELECT public.task_routing_outcome_complete(m) FROM public.task_post_submit_routing_manifests m WHERE id=:id"
            ), {"id": source_id}) is True
        async with _client(h, monkeypatch, isolated_database_env) as client:
            route = f"/api/v1/projects/{h.request.project_id}/tasks/{h.request.task_id}/revision-context/repair"
            payload = {"routing_manifest_id": str(source_id), "reason": "Recover an expired retained failure"}
            headers = {"Idempotency-Key": str(new_record_id())}
            response = await client.post(route, json=payload, headers=headers)
            assert response.status_code == 200, response.text
            receipt = response.json()
            assert receipt["outcome"] == "blocked"
            assert receipt["disposition"] == "revision_deadline_expired"
            async with h.factory() as session:
                row = await session.get(TaskRevisionPreparation, UUID(receipt["preparation_id"]))
                assert (row.requested_at, row.deadline_at) == (anchor, deadline)
            replay = await client.post(route, json=payload, headers=headers)
            assert replay.status_code == 200 and replay.json() == receipt
            before = await _creation_snapshot(h)
            denied = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/submission-bundle-preparations",
                headers={
                    "Content-Type": "application/zip",
                    "X-Task-Assignment-Id": str(h.request.assignment_id),
                    "X-Predecessor-Submission-Id": str(h.created.submission_id),
                    "Idempotency-Key": str(new_record_id()),
                    "X-Revision-Preparation-Id": receipt["preparation_id"],
                    "X-Revision-Preparation-Sha256": receipt["preparation_sha256"],
                }, content=b"not a zip",
            )
            assert denied.status_code == 409, denied.text
            assert denied.json()["error"]["code"] == "revision_deadline_expired"
            assert await _creation_snapshot(h) == before
            async with h.factory() as session:
                assert await session.scalar(text("SELECT status FROM public.workstream_tasks WHERE id=:id"), {"id": h.request.task_id}) == "needs_revision"
