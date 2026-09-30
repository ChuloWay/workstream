"""Fixed SQL projections and live grant privacy over retained checker results."""

from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.engine import Engine

from app.db import session as db_session
from app.modules.tasks.models import AuditEvent, Submission
from app.modules.tasks.submission_history import SubmissionHistoryRepository
from app.modules.checkers.history import CheckerHistoryRepository
from tests.submission_fixtures import seed_retained_submission, seed_retained_checker_run
from tests.test_tasks import (create_active_project, create_started_task, complete_submission_payload,
                             set_dev_actor, auth_headers, actor_id)
from .test_reads import history_paths, history_case
from .test_absence import (SUBMISSION_FIELDS, MANAGER_SUBMISSION_FIELDS, RUN_FIELDS, MANAGER_RUN_FIELDS,
                           RESULT_FIELDS, MANAGER_RESULT_FIELDS, EVIDENCE_FIELDS)


@pytest.mark.parametrize("state,failures", [("completed", ()), ("completed", ("check_policy_context_present",)), ("infrastructure_failed", ())])
async def test_fixed_projection_and_selected_columns(task_client, monkeypatch, state, failures):
    project = await create_active_project(task_client)
    task = await create_started_task(task_client, project["id"], monkeypatch)
    submission = await seed_retained_submission(task["id"], complete_submission_payload())
    run = await seed_retained_checker_run(submission, state=state, failures=failures)
    captured = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        compiled = getattr(context, "compiled", None)
        selected = getattr(getattr(compiled, "statement", None), "selected_columns", ())
        if selected is not None:
            captured.extend(selected)
    event.listen(Engine, "before_cursor_execute", capture)
    try:
        for manager in (False, True):
            set_dev_actor(monkeypatch, roles="", subject="project-manager-subject" if manager else "worker-one")
            for action, path in history_paths(project["id"], task["id"], submission, run, manager=manager).items():
                captured.clear()
                response = await task_client.get(path, headers=auth_headers())
                assert response.status_code == 200, response.text
                assert "PRIVATE_CHECKER_PACKET_SENTINEL" not in response.text
                value = response.json()
                item = value["items"][0] if action.endswith("list") else value
                checker = "checker" in action
                expected = (MANAGER_RUN_FIELDS if manager else RUN_FIELDS) if checker else (MANAGER_SUBMISSION_FIELDS if manager else SUBMISSION_FIELDS)
                assert set(item) == expected
                nested_key = "results" if checker else "evidence_items"
                nested_fields = (MANAGER_RESULT_FIELDS if manager else RESULT_FIELDS) if checker else EVIDENCE_FIELDS
                assert all(set(nested) == nested_fields for nested in item[nested_key])
                if checker:
                    assert bool(item["results"]) == (state == "completed" and (manager or not failures))
                # Actual selected columns, rather than searching predicates that
                # legitimately compute a boolean inside PostgreSQL. No raw body,
                # URI/hash, aggregate count, or receipt is loaded into Python.
                protected = {"submissions", "checker_runs", "checker_results", "evidence_items"}
                private = {"package_uri", "package_hash", "artifact_hash_manifest", "worker_attestation",
                           "locked_payment_policy_version", "locked_post_submit_checker_policy_body",
                           "request_json", "request_digest", "result_json", "result_digest", "material_custody",
                           "execute_evidence_id", "finalize_evidence_id", "completion_event_id", "counters",
                           "passed_count", "warning_count", "failed_count", "blocking_count", "uri", "hash"}
                owned = [column for column in captured if getattr(getattr(column, "table", None), "name", None) in protected]
                assert owned
                assert not {column.name for column in owned} & private
    finally:
        event.remove(Engine, "before_cursor_execute", capture)


async def test_denied_read_never_loads_private_rows(task_client, monkeypatch):
    from app.modules.authorization.models import ProjectRoleGrant
    case = await history_case(task_client, monkeypatch)
    who = await actor_id("worker-one")
    async with db_session.get_session_factory()() as session:
        grant = await session.scalar(select(ProjectRoleGrant).where(ProjectRoleGrant.actor_profile_id == who))
        grant_id = str(grant.id)
    set_dev_actor(monkeypatch, roles="", subject="project-manager-subject")
    revoke = await task_client.post(f"/api/v1/projects/{case[0]}/role-grants/{grant_id}/revoke",
                                   headers=auth_headers() | {"Idempotency-Key": str(uuid4())}, json={"reason": "Withdraw history access"})
    assert revoke.status_code == 200, revoke.text
    set_dev_actor(monkeypatch, roles="admin,project_manager,worker", subject="worker-one")
    async def forbidden(*args, **kwargs):
        pytest.fail("private projection entered without live grant")
    monkeypatch.setattr(SubmissionHistoryRepository, "read", forbidden)
    monkeypatch.setattr(CheckerHistoryRepository, "read", forbidden)
    for path in history_paths(*case).values():
        response = await task_client.get(path, headers=auth_headers())
        assert response.status_code == 404, response.text
    async with db_session.get_session_factory()() as session:
        events = list(await session.scalars(select(AuditEvent).where(AuditEvent.actor_id == who,
                                AuditEvent.action_id.in_(tuple(history_paths(*case))))))
        assert len(events) == 4
        assert all(event.after_facts["allowed"] is False for event in events)
        assert await session.get(Submission, case[2]) is not None


@pytest.mark.parametrize("manager", [False, True])
async def test_nested_values_match_exact_stored_parents(task_client, monkeypatch, manager):
    from app.modules.tasks.models import EvidenceItem
    from app.modules.checkers.models import CheckerResult
    from app.modules.checkers.execution_results import RESULT_MESSAGES
    project = await create_active_project(task_client)
    task = await create_started_task(task_client, project["id"], monkeypatch)
    submission = await seed_retained_submission(task["id"], complete_submission_payload())
    run = await seed_retained_checker_run(submission)
    sibling = await seed_retained_checker_run(submission, generation=2, failures=("check_submission_packet",))
    foreign_task = await create_started_task(task_client, project["id"], monkeypatch, subject="foreign-nested-owner")
    payload = complete_submission_payload()
    for item in payload["evidence_items"]:
        item["label"] = "Foreign " + item["label"]
    foreign_submission = await seed_retained_submission(foreign_task["id"], payload)
    foreign_run = await seed_retained_checker_run(foreign_submission, failures=("check_evidence_present",))
    async with db_session.get_session_factory()() as session:
        evidence = list(await session.scalars(select(EvidenceItem).order_by(EvidenceItem.id)))
        rows = list(await session.scalars(select(CheckerResult).order_by(CheckerResult.member_order)))
        assert {str(row.checker_run_id) for row in rows} == {run, sibling, foreign_run}
        expected_evidence = [{field: str(getattr(row, field)) if field == "id" else getattr(row, field)
                              for field in EVIDENCE_FIELDS} for row in evidence if row.submission_id == submission]
        expected_results = {}
        for run_id in (run, sibling):
            expected_results[run_id] = []
            for row in rows:
                if row.checker_run_id != run_id:
                    continue
                assert row.task_id == task["id"] and row.submission_id == submission
                message, fix = RESULT_MESSAGES[row.code]
                entry = {field:getattr(row,field) for field in ("id","checker_name","status","severity")}
                entry.update(worker_message=message, worker_suggested_fix=fix)
                if manager:
                    entry.update(message=message, blocks_review=row.status=="failed" and row.severity in {"high","critical"})
                expected_results[run_id].append(entry)
        assert expected_results[run] != expected_results[sibling] and expected_evidence
    set_dev_actor(monkeypatch, roles="", subject="project-manager-subject" if manager else "worker-one")
    for action, path in history_paths(project["id"],task["id"],submission,run,manager=manager).items():
        response = await task_client.get(path, headers=auth_headers())
        assert response.status_code == 200, response.text
        items = response.json()["items"] if action.endswith("list") else [response.json()]
        checker = "checker" in action
        assert {item["id"] for item in items} == ({run,sibling} if action=="submission.checker_run.list" else {run} if checker else {submission})
        for item in items:
            if checker:
                assert item["results"] == expected_results[item["id"]]
                assert item["is_current_for_submission"] == (item["id"]==sibling)
                assert item["submission_id"] == submission and item["task_id"] == task["id"]
            else:
                assert item["evidence_items"] == expected_evidence
