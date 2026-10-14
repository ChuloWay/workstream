"""Locked revision caps across real checker completion, intake, creation and SQL."""

import json

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

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
    _create, _creation_request, _creation_snapshot, _ready_replacement,
)
from tests.tasks.test_public_submission_intake import _client, _payload
from tests.test_submission_predecessor_custody import _fixture_revision_context


async def _fail_current_submission(h):
    """Complete the actual reserved successor using controlled external work failure."""
    async with h.factory() as session:
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

    async with remediation_source(tmp_path, isolated_database_env) as h:
        await _fixture_revision_context(h)
        async with h.factory() as session:
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

            # Arrange a real ready admission retained from preparation without
            # the new cap. All authority, checker, storage and lineage guards run.
            with monkeypatch.context() as patch:
                patch.setattr(
                    "app.modules.artifacts.submission_admission.require_revision_capacity",
                    lambda *_: None,
                )
                spare, spare_admission = await _ready_replacement(h, revision_archive(h.data))
            spare_payload = _payload(spare, spare_admission)
            before = await _creation_snapshot(h)
            # Empty/malformed ZIP would fail archive checks if capacity were checked too late.
            denied = await client.post(
                f"/api/v1/tasks/{h.request.task_id}/submission-bundle-preparations",
                headers={
                    "Content-Type": "application/zip",
                    "X-Task-Assignment-Id": str(h.request.assignment_id),
                    "X-Predecessor-Submission-Id": str(h.created.submission_id),
                    "Idempotency-Key": str(new_record_id()),
                }, content=b"not a zip",
            )
            assert denied.status_code == 409, denied.text
            assert denied.json()["error"]["code"] == "revision_limit_reached"
            over_cap = spare_payload
            denied = await client.post(route, json=over_cap)
            assert denied.status_code == 409, denied.text
            assert denied.json()["error"]["code"] == "revision_limit_reached"
            assert await _creation_snapshot(h) == before
            replay = await client.post(route, json=saved_payload)
            assert replay.status_code == 201, replay.text
            assert replay.json() == saved_response

        # Removing only the application cap still cannot create round3: the
        # otherwise-valid canonical writer must meet PostgreSQL's INSERT guard.
        with monkeypatch.context() as patch:
            patch.setattr(
                "app.modules.tasks.submission_composition.require_revision_capacity",
                lambda *_: None,
            )
            with pytest.raises(IntegrityError, match="revision_limit_reached"):
                await _create(h, _creation_request(h, spare, spare_admission))
        assert await _creation_snapshot(h) == before
        async with h.factory() as session:
            original = await session.scalar(text(
                "SELECT to_jsonb(s) FROM public.submissions s WHERE id=:id"
            ), {"id": h.created.submission_id})
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
