"""Hidden completion delivery through actual AUTH, outcome and shared finalization."""

import asyncio

import pytest
from sqlalchemy import text

from app.adapters.auth import outbox_dispatch_authorization
from app.adapters.outbox import outbox_delivery, production_outbox_delivery
from app.adapters.tasks import evaluation_completion_handler
from app.modules.checkers.api.execution import COMPLETION_EVENT, REQUEST_EVENT
from app.modules.outbox.api import HandlerOutcome, FinalizationCause, DeliveryOptions
from app.modules.outbox.registry import HandlerRegistry
from app.modules.tasks.post_submit_routing.outcome import TaskPostSubmitOutcome
from tests.authorization.post_submit_routing.support import provision_router
from tests.tasks.post_submit_routing.test_source_preparation import routing_source
from tests.tasks.post_submit_routing.outcome_support import (
    authorized_routing_source,
    outcome_snapshot,
)
from tests.post_submit_materialization_helpers import material_fixture
from .support import delivery_fixture, outcome, state


async def completion_delivery(h, handler=None):
    """Use real dispatcher authority and only a test-owned explicit registration."""
    await provision_router(h.factory)
    await delivery_fixture(h)
    return outbox_delivery(
        h.factory,
        authorization_factory=outbox_dispatch_authorization,
        options=DeliveryOptions(),
        registry=HandlerRegistry(
            [(COMPLETION_EVENT, 1, handler or evaluation_completion_handler(sessions=h.factory))]
        ),
    )


async def assert_committed(h, *, human, award_count):
    async with h.factory() as session:
        assert await session.scalar(
            text("SELECT status FROM public.workstream_tasks WHERE id=:id"),
            {"id": str(h.request.task_id)},
        ) == ("review_pending" if human else "accepted")
        for table, count in (
            ("task_post_submit_routing_manifests", 1),
            ("final_acceptances", int(not human)),
            ("contribution_records", int(not human)),
            ("compensation_awards", award_count),
            ("reviews", 0),
        ):
            assert await session.scalar(text(f"SELECT count(*) FROM public.{table}")) == count
        assert (
            await session.scalar(
                text(
                    "SELECT public.task_routing_outcome_complete(m) FROM public.task_post_submit_routing_manifests m"
                )
            )
            is True
        )


async def commit_before_ack(h, monkeypatch, *, human, award_count):
    """Pause after real staging; independent reads distinguish staging from commit."""
    staged, release = asyncio.Event(), asyncio.Event()
    original = TaskPostSubmitOutcome.apply

    async def pause(owner, *args, **kwargs):
        result = await original(owner, *args, **kwargs)
        staged.set()
        await release.wait()
        return result

    monkeypatch.setattr(TaskPostSubmitOutcome, "apply", pause)
    handler = evaluation_completion_handler(sessions=h.factory)

    async def acknowledge(envelope):
        result = await handler(envelope)
        assert result is HandlerOutcome.ACKNOWLEDGE
        await assert_committed(h, human=human, award_count=award_count)
        return result

    delivery = await completion_delivery(h, acknowledge)
    running = asyncio.create_task(
        delivery.deliver(h.source["completion_event_id"], h.request.project_id, "completion")
    )
    try:
        await asyncio.wait_for(staged.wait(), 10)
        assert not running.done()
        async with h.factory() as session:
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM public.task_post_submit_routing_manifests")
                )
                == 0
            )
            assert await session.scalar(text("SELECT count(*) FROM public.final_acceptances")) == 0
        release.set()
        receipt = await asyncio.wait_for(running, 10)
        assert outcome(receipt)["delivery_state"] == "acknowledged"
        await assert_committed(h, human=human, award_count=award_count)
    finally:
        release.set()
        if not running.done():
            running.cancel()
        await asyncio.gather(running, return_exceptions=True)


async def test_completion_handler_true_commits_before_ack_without_rev(
    tmp_path, isolated_database_env, monkeypatch
):
    from app.adapters.tasks.routing_acceptance import RoutingAcceptanceAdapter

    async def forbidden(*args, **kwargs):
        pytest.fail("true completion touched REV")

    monkeypatch.setattr(RoutingAcceptanceAdapter, "observe_generation", forbidden)
    monkeypatch.setattr(RoutingAcceptanceAdapter, "prepare", forbidden)
    async with routing_source(tmp_path, isolated_database_env) as h:
        await commit_before_ack(h, monkeypatch, human=True, award_count=0)


@pytest.mark.parametrize("awards", [(), ("money", "project_points")])
async def test_completion_handler_false_commits_acceptance_before_ack(
    tmp_path,
    isolated_database_env,
    live_acceptance_lifecycle,
    monkeypatch,
    awards,
):
    async with routing_source(
        tmp_path, isolated_database_env, human_review_required=False, contribution_awards=awards
    ) as h:
        await commit_before_ack(h, monkeypatch, human=False, award_count=len(awards))


@pytest.mark.parametrize("human", [True, False])
async def test_completion_handler_committed_replay_is_exact(
    tmp_path, isolated_database_env, live_acceptance_lifecycle, human
):
    async with authorized_routing_source(
        tmp_path, isolated_database_env, human_review_required=human
    ) as h:
        handler = evaluation_completion_handler(sessions=h.factory)
        assert await handler(h.envelope) is HandlerOutcome.ACKNOWLEDGE
        if not human:
            from tests.reviews.lifecycle.transition_support import command_for, transition

            stopped = await transition(
                await command_for(live_acceptance_lifecycle.target.id, "draining")
            )
            assert stopped.generation == 3
        async with h.factory() as session:
            saved = await outcome_snapshot(session)
        assert await handler(h.envelope) is HandlerOutcome.ACKNOWLEDGE
        async with h.factory() as session:
            assert await outcome_snapshot(session) == saved
        await h.completion_delivery.finalize(h.envelope.claim, FinalizationCause.ACKNOWLEDGE)
        assert await handler(h.envelope) is HandlerOutcome.REJECT


def test_completion_handler_is_registered_in_production_registry():
    assert (COMPLETION_EVENT, 1) in production_outbox_delivery(None)._registry.keys


@pytest.mark.parametrize("human", [True, False])
async def test_production_registry_delivers_request_then_completion_exactly_once(
    tmp_path,
    isolated_database_env,
    live_acceptance_lifecycle,
    monkeypatch,
    human,
):
    """Production registration must consume its own emitted completion event."""
    from app.adapters import artifacts as artifact_adapters

    awards = () if human else ("money", "project_points")
    async with material_fixture(
        tmp_path,
        isolated_database_env,
        human_review_required=human,
        contribution_awards=awards,
    ) as h:
        await provision_router(h.factory)
        await delivery_fixture(h)
        monkeypatch.setattr(
            artifact_adapters,
            "worker_post_submission_materialization",
            lambda *, sessions: h.service,
        )
        delivery = production_outbox_delivery(h.factory)
        assert delivery._registry.keys[-2:] == (
            (REQUEST_EVENT, 1),
            (COMPLETION_EVENT, 1),
        )

        request_receipt = await delivery.deliver(
            h.created.evaluation_event_id,
            h.request.project_id,
            "production-request",
        )
        assert outcome(request_receipt)["delivery_state"] == "acknowledged"
        completed = await state(h)
        assert completed["run"]["status"] == "completed"
        completion_event_id = completed["run"]["completion_event_id"]
        assert completion_event_id is not None

        completion_receipt = await delivery.deliver(
            completion_event_id,
            h.request.project_id,
            "production-completion",
        )
        assert outcome(completion_receipt)["delivery_state"] == "acknowledged"
        await assert_committed(h, human=human, award_count=len(awards))
        async with h.factory() as session:
            snapshot = await outcome_snapshot(session)
        assert (
            await delivery.deliver(
                completion_event_id,
                h.request.project_id,
                "production-completion-replay",
            )
            is None
        )
        async with h.factory() as session:
            assert await outcome_snapshot(session) == snapshot
