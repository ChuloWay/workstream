"""Recovery observes real original commits or rollbacks without overlapping effects."""

import asyncio

import pytest
from sqlalchemy import text

from app.core.identifiers import new_record_id
from app.modules.checkers.delivery_reconciliation import PostSubmitDeliveryService
from app.modules.outbox.api import FinalizationCause
from app.modules.outbox.delivery_repository import DeliveryRepository
from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequestUnavailable
from app.modules.tasks.post_submit_routing.source import TaskRoutingSourcePreparer
from tests.auth_concurrency_support import wait_for_named_database_lock
from tests.authentication.fixtures import (
    auth_database_env as auth_database_env,
    clear_settings_cache as clear_settings_cache,
    rsa_signing_material as rsa_signing_material,
)
from tests.authorization.admin_access.fixtures import (
    admin_access as admin_access,
    signed_access as signed_access,
)
from tests.reviews.lifecycle.fixtures import (
    live_acceptance_lifecycle as live_acceptance_lifecycle,
)
from tests.tasks.evaluation_delivery.support import outcome
from tests.tasks.post_submit_routing.outcome_support import (
    apply_outcome,
    authorized_routing_source,
    outcome_snapshot,
)


async def _request_reconciliation(access, h, key):
    return await access.signed.client.post(
        f"/api/v1/operations/projects/{h.request.project_id}"
        f"/post-submit-deliveries/{h.envelope.claim.event_id}/reconcile",
        headers=access.target.headers | {"Idempotency-Key": str(key)},
        json={"reason": "Reconcile after exact original transaction visibility"},
    )


async def _business_facts(factory):
    async with factory() as session:
        rows = await outcome_snapshot(session)
        return (*rows[:4], *rows[6:])


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_original", [True, False], ids=["commit", "rollback"])
async def test_unknown_and_recovery_wait_for_original_transaction_visibility(
    tmp_path, auth_database_env, live_acceptance_lifecycle, monkeypatch,
    commit_original,
):
    """An in-flight fenced outcome is not yet an eligible UNKNOWN source."""
    async with authorized_routing_source(
        tmp_path, auth_database_env, contribution_awards=("project_points",),
    ) as h:
        waiter_name = "recovery-finalize-" + new_record_id().hex
        original_event = DeliveryRepository.event

        async def named_event(owner, *args, **kwargs):
            if asyncio.current_task().get_name() == waiter_name:
                await owner.session.execute(
                    text("SELECT set_config('application_name',:name,true)"),
                    {"name": waiter_name},
                )
            return await original_event(owner, *args, **kwargs)

        monkeypatch.setattr(DeliveryRepository, "event", named_event)
        pending = None
        key = new_record_id()
        try:
            async with h.factory() as writer:
                await writer.begin()
                blocker = await writer.scalar(text("SELECT pg_backend_pid()"))
                staged = await apply_outcome(writer, h, 2)
                assert staged.final_acceptance_id is not None
                pending = asyncio.create_task(
                    h.completion_delivery.finalize(
                        h.envelope.claim, FinalizationCause.UNKNOWN,
                    ),
                    name=waiter_name,
                )
                await asyncio.wait_for(wait_for_named_database_lock(
                    auth_database_env, waiter_name, expected_blocker_pid=blocker,
                ), timeout=10)
                premature = await asyncio.wait_for(_request_reconciliation(
                    live_acceptance_lifecycle, h, key,
                ), timeout=10)
                assert premature.status_code == 404, premature.text
                assert not pending.done()
                if commit_original:
                    await writer.commit()
                else:
                    await writer.rollback()
            finalized = await asyncio.wait_for(pending, timeout=10)
            assert outcome(finalized)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
            before = await _business_facts(h.factory)
            response = await _request_reconciliation(live_acceptance_lifecycle, h, key)
            assert response.status_code == 201, response.text
            assert response.json()["successor"]["classification"] == (
                "committed" if commit_original else "retry_safe"
            )
            assert await _business_facts(h.factory) == before
            assert bool(before[1]) is commit_original
        finally:
            if pending is not None:
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.asyncio
async def test_delayed_original_loses_custody_before_recovery_classifies(
    tmp_path, auth_database_env, live_acceptance_lifecycle, monkeypatch,
):
    """Recovery waits for the original REV holder to fail its actual OUTBOX fence."""
    async with authorized_routing_source(tmp_path, auth_database_env) as h:
        entered, release = asyncio.Event(), asyncio.Event()
        original_name = "delayed-original-" + new_record_id().hex
        recovery_name = "recovery-command-" + new_record_id().hex
        original_prepare = TaskRoutingSourcePreparer.prepare
        original_classify = PostSubmitDeliveryService._classify
        blocker_pids = []

        async def paused_prepare(owner, *args, **kwargs):
            if asyncio.current_task().get_name() == original_name:
                entered.set()
                await asyncio.wait_for(release.wait(), timeout=20)
            return await original_prepare(owner, *args, **kwargs)

        async def named_classify(owner, *args, **kwargs):
            await owner._session.execute(
                text("SELECT set_config('application_name',:name,true)"),
                {"name": recovery_name},
            )
            return await original_classify(owner, *args, **kwargs)

        async def original_effect():
            async with h.factory() as writer, writer.begin():
                blocker_pids.append(await writer.scalar(text("SELECT pg_backend_pid()")))
                return await apply_outcome(writer, h, 2)

        monkeypatch.setattr(TaskRoutingSourcePreparer, "prepare", paused_prepare)
        monkeypatch.setattr(PostSubmitDeliveryService, "_classify", named_classify)
        original = asyncio.create_task(original_effect(), name=original_name)
        recovery = None
        try:
            await asyncio.wait_for(entered.wait(), timeout=10)
            finalized = await h.completion_delivery.finalize(
                h.envelope.claim, FinalizationCause.UNKNOWN,
            )
            assert outcome(finalized)["error_code"] == "INVOKE_OUTCOME_UNKNOWN"
            before = await _business_facts(h.factory)
            recovery = asyncio.create_task(_request_reconciliation(
                live_acceptance_lifecycle, h, new_record_id(),
            ))
            await asyncio.wait_for(wait_for_named_database_lock(
                auth_database_env, recovery_name, expected_blocker_pid=blocker_pids[0],
            ), timeout=10)
            assert not recovery.done()
            release.set()
            with pytest.raises(TaskRoutingRequestUnavailable, match="routing invocation changed"):
                await asyncio.wait_for(original, timeout=10)
            response = await asyncio.wait_for(recovery, timeout=10)
            assert response.status_code == 201, response.text
            assert response.json()["successor"]["classification"] == "retry_safe"
            assert await _business_facts(h.factory) == before
            assert before[1] is None
        finally:
            release.set()
            pending = [task for task in (original, recovery) if task is not None]
            for task in pending:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
