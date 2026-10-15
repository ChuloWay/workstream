"""Stored per-finding evidence, the coverage hold and its Operator recovery."""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.adapters.checkers import checker_history_repository, checker_retry_service
from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import COMPLETION_EVENT, CheckerRetryCommand
from app.modules.checkers.models import CheckerResultFinding, CheckerRun
from app.modules.outbox.models import OutboxEvent
from app.modules.tasks.models import Submission, WorkstreamTask
from tests.checkers.execution.support import ControlledSelectedExecution, live_executor, reserve
from tests.checkers.external.support import post_registry_spec
from tests.post_submit_materialization_helpers import material_fixture
from tests.project_create_fixtures import grant_fixture_admin_role
from tests.test_artifact_admission import _context, _seed_human_actor

COVERAGE = {
    "check_id": "coverage.files", "code": "coverage.unreadable",
    "level": "coverage_incomplete", "message": "One file was not evaluated.",
    "path": "src/vendor.bin", "line": None,
}
WARNING = {
    "check_id": "style.lines", "code": "style.long_line", "level": "warning",
    "message": "Line is long.", "path": "src/main.py", "line": 12,
}
ERROR = {
    "check_id": "tests.pass", "code": "tests.failed", "level": "error",
    "message": "A test failed.", "path": "tests/test_main.py", "line": 3,
}


async def _evaluate(h, *, verdict, findings):
    await reserve(h)
    result = await live_executor(
        h, selected_execution=ControlledSelectedExecution(verdict=verdict, findings=findings),
    ).evaluate_post_submission(h.request)
    async with h.factory() as session:
        run = await session.get(CheckerRun, str(result.attempt_id))
    return result, run


async def test_coverage_gap_holds_without_routing_and_stays_private(tmp_path, isolated_database_env):
    async with material_fixture(
        tmp_path, isolated_database_env, post_submit_registry_spec=post_registry_spec(),
    ) as h:
        result, run = await _evaluate(h, verdict="passed", findings=(COVERAGE, WARNING))
        assert result.outcome == "completed"
        assert (run.status, run.routing_recommendation, run.completion_event_id) == (
            "completed", "task_setup_blocked", None,
        )
        async with h.factory() as session:
            assert await session.scalar(select(func.count()).select_from(OutboxEvent).where(
                OutboxEvent.event_type == COMPLETION_EVENT,
            )) == 0
            stored = list(await session.scalars(select(CheckerResultFinding).where(
                CheckerResultFinding.checker_run_id == run.id,
            ).order_by(CheckerResultFinding.finding_order)))
            assert [
                (row.check_id, row.code, row.level, row.path, row.line) for row in stored
            ] == [
                (item["check_id"], item["code"], item["level"], item["path"], item["line"])
                for item in (COVERAGE, WARNING)
            ]
            task = await session.get(WorkstreamTask, str(h.request.task_id))
            submission = await session.get(Submission, str(h.request.submission_id))
            assert task.status == "evaluation_pending"
            assert (submission.attempt_status, submission.decided_at) == ("evaluation_pending", None)

            reads = checker_history_repository(session)
            managed, _ = await reads.read(
                submission_id=h.request.submission_id, task_id=h.request.task_id, manager=True,
            )
            assert [
                (item.check_id, item.path, item.line, item.status, item.blocks_review)
                for item in managed[0].results
            ] == [
                ("coverage.files", "src/vendor.bin", None, "coverage_incomplete", False),
                ("style.lines", "src/main.py", 12, "warning", False),
            ]
            assert managed[0].routing_recommendation == "task_setup_blocked"
            contributed, _ = await reads.read(
                submission_id=h.request.submission_id, task_id=h.request.task_id, manager=False,
            )
            assert contributed[0].results == []
            submission_id = h.request.submission_id
            manager_counts = await reads.read_finding_counts((submission_id,), manager=True)
            contributor_counts = await reads.read_finding_counts((submission_id,), manager=False)
            assert manager_counts[submission_id] == (0, 1, 1)
            assert contributor_counts[submission_id] == (0, 0, 0)


async def test_failures_still_route_to_revision_alongside_coverage(tmp_path, isolated_database_env):
    async with material_fixture(
        tmp_path, isolated_database_env, post_submit_registry_spec=post_registry_spec(),
    ) as h:
        _, run = await _evaluate(h, verdict="failed", findings=(ERROR, COVERAGE))
        assert run.routing_recommendation == "needs_revision"
        assert run.completion_event_id is not None
        async with h.factory() as session:
            reads = checker_history_repository(session)
            contributed, _ = await reads.read(
                submission_id=h.request.submission_id, task_id=h.request.task_id, manager=False,
            )
            assert [(item.check_id, item.line, item.status) for item in contributed[0].results] == [
                ("tests.pass", 3, "failed"), ("coverage.files", None, "coverage_incomplete"),
            ]
            counts = await reads.read_finding_counts((h.request.submission_id,), manager=False)
            assert counts[h.request.submission_id] == (1, 0, 1)


async def test_findings_are_immutable_and_bound_to_the_stored_result(
    tmp_path, isolated_database_env,
):
    async with material_fixture(
        tmp_path, isolated_database_env, post_submit_registry_spec=post_registry_spec(),
    ) as h:
        _, run = await _evaluate(h, verdict="passed", findings=(WARNING,))
        assert run.routing_recommendation == "allow_review"
        async with h.factory() as session:
            finding = await session.scalar(select(CheckerResultFinding).where(
                CheckerResultFinding.checker_run_id == run.id,
            ))
        for statement in (
            "update public.checker_result_findings set line=99 where id=:id",
            "delete from public.checker_result_findings where id=:id",
        ):
            with pytest.raises(DBAPIError, match="finding custody is immutable"):
                async with h.factory.begin() as session:
                    await session.execute(text(statement), {"id": finding.id})
        # A finished run cannot gain a finding the stored result does not contain.
        with pytest.raises(DBAPIError, match="cannot receive findings"):
            async with h.factory.begin() as session:
                session.add(CheckerResultFinding(
                    id=str(new_record_id()), checker_result_id=finding.checker_result_id,
                    checker_run_id=run.id, task_id=run.task_id, submission_id=run.submission_id,
                    member_order=finding.member_order, finding_order=1,
                    check_id="extra.check", code="extra", level="error",
                ))
                await session.flush()


async def test_operator_retry_recovers_a_coverage_hold(tmp_path, isolated_database_env):
    async with material_fixture(
        tmp_path, isolated_database_env, post_submit_registry_spec=post_registry_spec(),
    ) as h:
        _, run = await _evaluate(h, verdict="passed", findings=(COVERAGE,))
        operator = _context()
        async with h.factory.begin() as session:
            await _seed_human_actor(session, operator)
            await grant_fixture_admin_role(
                session, operator.actor_profile_id, role="operator", scope="system",
            )
        key = new_record_id()
        operator = operator.model_copy(update={"request_id": key, "correlation_id": key})
        command = CheckerRetryCommand(
            source_run_id=run.id, request_key=key, reason="Checker image coverage restored",
        )
        async with h.factory.begin() as session:
            created = await checker_retry_service(session, operator).retry(command)
        assert created.successor.generation == 2
        async with h.factory() as session:
            assert await session.scalar(
                text("select failure_code from public.checker_retry_receipts where id=:id"),
                {"id": created.receipt_id},
            ) == "coverage_incomplete"
            assert await session.scalar(
                text("select public.checker_retry_receipt_valid(:id)"), {"id": created.receipt_id},
            ) is True
        async with h.factory.begin() as session:
            assert await checker_retry_service(session, operator).retry(command) == created


async def test_completed_routed_runs_cannot_be_retried(tmp_path, isolated_database_env):
    async with material_fixture(
        tmp_path, isolated_database_env, post_submit_registry_spec=post_registry_spec(),
    ) as h:
        _, run = await _evaluate(h, verdict="passed", findings=(WARNING,))
        operator = _context()
        async with h.factory.begin() as session:
            await _seed_human_actor(session, operator)
            await grant_fixture_admin_role(
                session, operator.actor_profile_id, role="operator", scope="system",
            )
        key = new_record_id()
        operator = operator.model_copy(update={"request_id": key, "correlation_id": key})
        with pytest.raises(Exception, match="checker_retry_source_unavailable"):
            async with h.factory.begin() as session:
                await checker_retry_service(session, operator).retry(CheckerRetryCommand(
                    source_run_id=run.id, request_key=key, reason="Not a recoverable hold",
                ))
