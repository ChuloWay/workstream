"""Current contributor failures route atomically without human review or acceptance."""

import asyncio

import pytest
from sqlalchemy import text

from app.adapters.tasks import evaluation_completion_handler, task_post_submit_outcome
from app.modules.outbox.api import HandlerOutcome
from tests.tasks.post_submit_routing.backfill_support import assert_backfill_matches_live
from tests.tasks.post_submit_routing.outcome_support import outcome_snapshot
from .remediation_support import remediation_source, no_economic_effects


@pytest.mark.parametrize("human_review_required", [True, False])
async def test_remediation_outcome_and_replay(tmp_path, isolated_database_env, human_review_required):
    async with remediation_source(
        tmp_path, isolated_database_env, human_review_required=human_review_required,
    ) as h:
        class ForbiddenAcceptance:
            async def observe_generation(self):
                pytest.fail("remediation observed REV")

            def prepare(self, generation):
                pytest.fail("remediation acquired REV")

        async with h.factory() as session, session.begin():
            operation = task_post_submit_outcome(session, h.factory)
            operation._acceptance = ForbiddenAcceptance()
            assert await operation.observe_delivery_generation(h.envelope) is None
            result = await operation.apply(h.envelope, current_generation=None)
            assert result.routing_recommendation == "needs_revision"
            assert result.final_acceptance_id is None and result.economic is None
        async with h.factory() as session:
            row = (await session.execute(text("""
                SELECT m.routing_recommendation,m.checker_run_id,m.result_digest,
                  m.assignment_id,m.submission_id,m.authorization_decision_id,
                  m.authority_context->'consequence' AS consequence,
                  t.status,a.status AS assignment_status,
                  public.task_routing_context_valid(m) AS context_valid,
                  public.task_routing_outcome_complete(m) AS complete
                FROM public.task_post_submit_routing_manifests m
                JOIN public.workstream_tasks t ON t.id=m.task_id
                JOIN public.task_assignments a ON a.id=m.assignment_id
                WHERE m.id=:id
            """), {"id": result.routing_manifest_id})).mappings().one()
            assert row["routing_recommendation"] == row["status"] == "needs_revision"
            assert row["checker_run_id"] == h.completion.reference.attempt_id
            assert row["result_digest"] == h.completion.reference.result_digest
            assert row["submission_id"] == h.request.submission_id
            assert row["assignment_id"] == h.request.assignment_id
            assert row["authorization_decision_id"] == result.authorization_decision_id
            assert row["assignment_status"] == "active"
            assert row["context_valid"] is True and row["complete"] is True
            # The routing manifest, not the caller, supplies the decision time.
            assert (await session.execute(text(
                "SELECT s.attempt_status,s.decided_at=m.created_at,s.status_reason "
                "FROM public.submissions s JOIN public.task_post_submit_routing_manifests m "
                "ON m.submission_id=s.id WHERE m.id=:id"
            ), {"id": result.routing_manifest_id})).one() == ("needs_revision", True, None)
            assert row["consequence"] == {
                "kind": "checker_remediation", "expected_task_status": "evaluation_pending",
                "target_task_status": "needs_revision",
            }
            await no_economic_effects(session)
            before = await outcome_snapshot(session)
        # A lost response is recovered through the actual completion handler.
        assert await evaluation_completion_handler(sessions=h.factory)(h.envelope) is HandlerOutcome.ACKNOWLEDGE
        async with h.factory() as session:
            assert await outcome_snapshot(session) == before
            await no_economic_effects(session)
        await assert_backfill_matches_live(h.factory)


async def test_false_remediation_does_not_wait_for_rev(tmp_path, isolated_database_env):
    async with remediation_source(tmp_path, isolated_database_env, human_review_required=False) as h:
        async with h.factory() as holder, holder.begin():
            assert await holder.scalar(text(
                "SELECT singleton FROM public.joint_lifecycle_release_control WHERE singleton FOR UPDATE"
            )) is True
            async def deliver():
                return await evaluation_completion_handler(sessions=h.factory)(h.envelope)
            # A regression acquiring REV waits on the holder until this deadline.
            result = await asyncio.wait_for(deliver(), timeout=10)
            assert result is HandlerOutcome.ACKNOWLEDGE
        async with h.factory() as session:
            assert await session.scalar(text("SELECT phase FROM public.joint_lifecycle_release_control")) == "disabled"
            await no_economic_effects(session)


async def test_remediation_does_not_freeze_successor(tmp_path, isolated_database_env):
    async with remediation_source(tmp_path, isolated_database_env, human_review_required=False) as h:
        assert await evaluation_completion_handler(sessions=h.factory)(h.envelope) is HandlerOutcome.ACKNOWLEDGE
        async with h.factory() as session:
            retained = await session.scalar(text(
                "SELECT to_jsonb(m) FROM public.task_post_submit_routing_manifests m"
            ))
        # Scope: the accepted-state guard must not freeze remediation. This is
        # not proof of the deferred exact-cause replacement writer or admission.
        async with h.factory() as session, session.begin():
            changed = await session.execute(text(
                "UPDATE public.workstream_tasks SET status='evaluation_pending' WHERE id=:id AND status='needs_revision'"
            ), {"id": h.request.task_id})
            assert changed.rowcount == 1
        async with h.factory() as session:
            assert await session.scalar(text(
                "SELECT to_jsonb(m) FROM public.task_post_submit_routing_manifests m"
            )) == retained
            await no_economic_effects(session)
