"""Stored per-finding evidence and policy-governed routing of checker coverage gaps."""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.adapters.checkers import checker_history_repository
from app.adapters.tasks import task_post_submit_outcome
from app.core.identifiers import new_record_id
from app.modules.checkers.api.execution import COMPLETION_EVENT
from app.modules.checkers.models import CheckerResultFinding, CheckerRun
from app.modules.outbox.models import OutboxEvent
from tests.checkers.execution.support import ControlledSelectedExecution, live_executor, reserve
from tests.checkers.external.support import post_registry_spec
from tests.post_submit_materialization_helpers import material_fixture
from tests.tasks.post_submit_routing.backfill_support import (
    assert_backfill_matches_live, assert_upgrade_refuses_stale_findings,
)
from tests.tasks.post_submit_routing.remediation_support import remediation_source

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


async def test_coverage_gap_goes_to_review_when_human_review_is_required(
    tmp_path, isolated_database_env,
):
    async with material_fixture(
        tmp_path, isolated_database_env, post_submit_registry_spec=post_registry_spec(),
        human_review_required=True,
    ) as h:
        _, run = await _evaluate(h, verdict="passed", findings=(COVERAGE, WARNING))
        # A reviewer judges what the checker could not; nothing is auto-accepted.
        assert (run.status, run.routing_recommendation) == ("completed", "allow_review")
        assert run.completion_event_id is not None
        async with h.factory() as session:
            stored = list(await session.scalars(select(CheckerResultFinding).where(
                CheckerResultFinding.checker_run_id == run.id,
            ).order_by(CheckerResultFinding.finding_order)))
            assert [
                (row.check_id, row.code, row.level, row.path, row.line) for row in stored
            ] == [
                (item["check_id"], item["code"], item["level"], item["path"], item["line"])
                for item in (COVERAGE, WARNING)
            ]
            reads = checker_history_repository(session)
            for manager in (False, True):
                runs, _ = await reads.read(
                    submission_id=h.request.submission_id, task_id=h.request.task_id,
                    manager=manager,
                )
                assert [
                    (item.check_id, item.path, item.line, item.status)
                    for item in runs[0].results
                ] == [
                    ("coverage.files", "src/vendor.bin", None, "coverage_incomplete"),
                    ("style.lines", "src/main.py", 12, "warning"),
                ]
                counts = await reads.read_finding_counts((h.request.submission_id,), manager=manager)
                assert counts[h.request.submission_id] == (0, 1, 1)
        await assert_upgrade_refuses_stale_findings(h.factory, store="checker_runs", row_id=run.id)


async def test_coverage_gap_returns_to_contributor_without_human_review(
    tmp_path, isolated_database_env,
):
    async with material_fixture(
        tmp_path, isolated_database_env, post_submit_registry_spec=post_registry_spec(),
        human_review_required=False,
    ) as h:
        _, run = await _evaluate(h, verdict="passed", findings=(COVERAGE,))
        # Under a false ReviewPolicy a passing verdict with a coverage gap never accepts.
        assert (run.status, run.routing_recommendation) == ("completed", "needs_revision")
        assert (run.passed_count, run.failed_count) == (1, 0)
        assert run.completion_event_id is not None


async def test_failures_still_route_to_revision_alongside_coverage(tmp_path, isolated_database_env):
    async with material_fixture(
        tmp_path, isolated_database_env, post_submit_registry_spec=post_registry_spec(),
        human_review_required=True,
    ) as h:
        _, run = await _evaluate(h, verdict="failed", findings=(ERROR, COVERAGE))
        assert run.routing_recommendation == "needs_revision"
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
            assert await session.scalar(select(func.count()).select_from(OutboxEvent).where(
                OutboxEvent.event_type == COMPLETION_EVENT,
            )) == 1


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


async def test_coverage_return_spends_no_revision_round(tmp_path, isolated_database_env):
    async with remediation_source(
        tmp_path, isolated_database_env, human_review_required=False, findings=(COVERAGE,),
    ) as h:
        async with h.factory() as session, session.begin():
            routed = await task_post_submit_outcome(session, h.factory).apply(
                h.envelope, current_generation=None,
            )
        assert routed.routing_recommendation == "needs_revision"
        assert routed.final_acceptance_id is None
        async with h.factory() as session:
            outcome = (await session.execute(text("""
                SELECT s.attempt_status, s.status_reason, s.decided_at=m.created_at,
                  p.next_revision_round, t.status
                FROM public.submissions s
                JOIN public.task_post_submit_routing_manifests m ON m.submission_id=s.id
                JOIN public.task_revision_preparations p ON p.routing_manifest_id=m.id
                JOIN public.workstream_tasks t ON t.id=s.task_id
                WHERE s.id=:id
            """), {"id": h.request.submission_id})).one()
        # The contributor gets the work back; the next attempt is still round zero.
        assert outcome == (
            "needs_revision", "checker_coverage_incomplete", True, 0, "needs_revision",
        )
        await assert_backfill_matches_live(h.factory)


async def test_genuine_failure_with_coverage_gap_spends_the_normal_round_and_window(
    tmp_path, isolated_database_env,
):
    """An error beside a coverage gap is an ordinary contributor failure, not a gap return."""
    async with remediation_source(
        tmp_path, isolated_database_env, human_review_required=False,
        findings=(ERROR, COVERAGE),
    ) as h:
        assert (h.run.routing_recommendation, h.run.failed_count) == ("needs_revision", 1)
        async with h.factory() as session, session.begin():
            routed = await task_post_submit_outcome(session, h.factory).apply(
                h.envelope, current_generation=None,
            )
        assert routed.routing_recommendation == "needs_revision"
        async with h.factory() as session:
            outcome = (await session.execute(text("""
                SELECT s.attempt_status, s.status_reason, s.decided_at=m.created_at,
                  p.next_revision_round, p.requested_at=m.created_at,
                  p.deadline_at=m.created_at+make_interval(hours=>policy.revision_deadline_hours)
                FROM public.submissions s
                JOIN public.task_post_submit_routing_manifests m ON m.submission_id=s.id
                JOIN public.task_revision_preparations p ON p.routing_manifest_id=m.id
                JOIN public.revision_policies policy ON policy.id=s.locked_revision_policy_id
                WHERE s.id=:id
            """), {"id": h.request.submission_id})).one()
        # No coverage exemption: no reason, round one is spent, the policy window applies.
        assert outcome == ("needs_revision", None, True, 1, True, True)
        await assert_backfill_matches_live(h.factory)


async def test_coverage_gap_routes_to_review_pending_when_review_is_required(
    tmp_path, isolated_database_env,
):
    async with remediation_source(
        tmp_path, isolated_database_env, recommendation="allow_review",
        human_review_required=True, findings=(COVERAGE,),
    ) as h:
        async with h.factory() as session, session.begin():
            routed = await task_post_submit_outcome(session, h.factory).apply(
                h.envelope, current_generation=None,
            )
        assert routed.routing_recommendation == "allow_review"
        assert routed.final_acceptance_id is None
        async with h.factory() as session:
            outcome = (await session.execute(text("""
                SELECT s.attempt_status, s.status_reason, s.decided_at,
                  (SELECT count(*) FROM public.final_acceptances), t.status
                FROM public.submissions s JOIN public.workstream_tasks t ON t.id=s.task_id
                WHERE s.id=:id
            """), {"id": h.request.submission_id})).one()
        # Awaiting a reviewer is not a decision: no time, no reason, no acceptance.
        assert outcome == ("review_pending", None, None, 0, "review_pending")
        await assert_backfill_matches_live(h.factory)


@pytest.mark.parametrize("change", [
    {}, {"check_id": None}, {"check_id": "Upper.case"}, {"path": None, "line": None},
    {"path": "../outside"}, {"path": "/absolute"}, {"path": "dir\\file"},
    {"path": "src/\u200bhidden"}, {"path": "C:/drive"}, {"path": "src/trailing."},
    {"path": None, "line": 3},
])
def test_upgrade_precondition_matches_the_finding_contract(change):
    """0049's frozen retained-finding rules accept exactly what the contract accepts."""
    from app.modules.checkers.api import ExternalCheckerFinding
    from tests.tasks.post_submit_routing.backfill_support import _MIGRATION

    finding = {key: value for key, value in (ERROR | change).items() if value is not None}
    try:
        ExternalCheckerFinding.model_validate(finding)
        accepted = True
    except Exception:
        accepted = False
    assert _MIGRATION._finding_current(finding) is accepted
