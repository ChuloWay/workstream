"""Lost publication and response recovery through production worker and public owners."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.api.post_policy import PostPolicyDelivery, post_policy_task_id
from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor, revoke_review_grant
from tests.projects.guide_compilation.proposals.public_support import proposal_client, proposal_path
from .public_support import public_approved_case, deliver


async def test_committed_approval_recovers_after_broker_failure(
    isolated_database_env, monkeypatch, post_policy_worker,
):
    from app.modules.projects.post_policy import queue

    async with public_approved_case(isolated_database_env, monkeypatch, broker_failure=True) as (
        factory, command, actor, _, approval_id, published,
    ):
        async with proposal_client(factory, actor) as client:
            package = await client.get(proposal_path(command) + "/proposal")
            assert package.json()["current_approval_operation_id"] == str(approval_id)
            assert package.json()["post_submit_policy_id"] is None
        monkeypatch.setattr(queue, "enqueue_derivation", published.append)
        scanned = post_policy_worker.scan_post_policy_approvals.apply(throw=True).get()
        assert scanned == {"selected": 1, "published": 1, "next_after": None}
        assert published == [approval_id, approval_id]
        # Exercise real SQL keyset membership independently of transport mocks.
        from app.adapters.projects import pending_post_policy_approvals
        assert await pending_post_policy_approvals(factory, after=UUID(int=0), limit=1) == [approval_id]
        assert await pending_post_policy_approvals(factory, after=approval_id, limit=1) == []
        first = deliver(post_policy_worker, published[-1])
        assert first["status"] == "policy_draft_ready", first
        assert deliver(post_policy_worker, approval_id) == first
        assert post_policy_worker.scan_post_policy_approvals.apply(throw=True).get()["selected"] == 0
        async with factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM project_post_policy_operations")) == 1
            assert await session.scalar(text("SELECT count(*) FROM checker_policies")) == 1


async def test_lost_post_policy_correction_discovered_and_dispatched_by_new_manager(
    isolated_database_env, monkeypatch, post_policy_worker,
):
    from app.core import project_agents
    from app.modules.projects import setup_queue
    from tests.projects.guide_compilation.helpers import runtime_configuration

    monkeypatch.setattr(project_agents, "project_guide_runtime_configuration", lambda settings: runtime_configuration())
    dispatched = []
    def enqueue(**values):
        dispatched.append(values)
        return values["task_id"]
    monkeypatch.setattr(setup_queue, "enqueue_project_guide_compilation", enqueue)
    async with public_approved_case(isolated_database_env, monkeypatch) as (
        factory, command, creator, grant, approval_id, _,
    ):
        assert deliver(post_policy_worker, approval_id)["status"] == "policy_draft_ready"
        path = proposal_path(command)
        async with proposal_client(factory, creator) as client:
            proposal = await client.get(path + "/proposal")
            policy_path = path + "/post-submission-policies/" + proposal.json()["post_submit_policy_id"]
            policy = await client.get(policy_path)
            key = {"Idempotency-Key": str(uuid4())}
            payload = {"target": policy.json()["target"], "reason": "Reconsider the evaluation evidence requirement."}
            response = await client.post(policy_path + "/corrections", headers=key, json=payload)
            assert response.status_code == 201, response.text
            assert (await client.post(policy_path + "/corrections", headers=key, json=payload)).json() == response.json()
            assert dispatched == []
        # No original receipt, policy ID, predecessor ID, or idempotency key is
        # carried into the new manager's discovery flow.
        del response, policy, policy_path, proposal, payload, key
        manager, _ = await seed_review_actor(factory, command.project_id)
        await revoke_review_grant(factory, creator, grant)
        latest_path = f"/api/v1/projects/{command.project_id}/guides/{command.guide_id}/setup-runs/latest"
        async with proposal_client(factory, manager) as client:
            latest = await client.get(latest_path)
            assert latest.status_code == 200, latest.text
            pending = latest.json()
            assert pending["status"] == "correction_requested"
            predecessor_path = (
                f"/api/v1/projects/{pending['project_id']}/guides/{pending['guide_id']}"
                f"/compilations/{pending['predecessor_compilation_id']}"
            )
            proposal = await client.get(predecessor_path + "/proposal")
            assert proposal.status_code == 200, proposal.text
            retained = await client.get(predecessor_path + "/post-submission-policies/" + proposal.json()["post_submit_policy_id"])
            assert retained.status_code == 200, retained.text
            assert retained.json()["lifecycle_status"] == "superseded"
            assert retained.json()["current"] is False
            correction = retained.json()["correction"]
            assert correction["operation_id"] == pending["correction_operation_id"]
            endpoint = predecessor_path + f"/corrections/{correction['operation_id']}/dispatch"
            async with proposal_client(factory, creator) as denied:
                assert (await denied.get(latest_path)).status_code == 404
                assert (await denied.post(endpoint)).status_code == 404
            result = await client.post(endpoint)
            assert result.status_code == 202, result.text
            assert len(dispatched) == 1
            assert (await client.post(endpoint)).status_code == 202
            assert len(dispatched) == 1
            async with factory() as session:
                assert await session.scalar(text("SELECT count(*) FROM project_guide_proposal_corrections")) == 1
                assert await session.scalar(text("SELECT actor_profile_id FROM project_guide_compilation_request_operations WHERE expected_predecessor_compilation_id=:id"), {"id":UUID(pending["predecessor_compilation_id"])}) == manager.actor_profile_id


async def test_stale_delivery_does_not_create_policy_and_scan_excludes_successor(
    isolated_database_env, monkeypatch, post_policy_worker,
):
    async with public_approved_case(isolated_database_env, monkeypatch) as (
        factory, command, actor, _, approval_id, _,
    ):
        async with proposal_client(factory, actor) as client:
            path = proposal_path(command)
            package = await client.get(path + "/proposal")
            corrected = await client.post(path + "/corrections", headers={"Idempotency-Key":str(uuid4())},
                json={"target": package.json()["target"], "reason":"Reconsider the task example."})
            assert corrected.status_code == 201, corrected.text
        assert deliver(post_policy_worker, approval_id) == {"status":"delivery_rejected"}
        assert post_policy_worker.scan_post_policy_approvals.apply(throw=True).get()["selected"] == 0
        async with factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM project_post_policy_operations")) == 0
            assert await session.scalar(text("SELECT count(*) FROM audit_events WHERE action_id='project.post_submit_checker_policy.derive'")) == 0


async def test_delivery_unknown_approval_has_no_product_writes(
    isolated_database_env, post_policy_worker,
):
    unknown = uuid4()
    assert await post_policy_worker._derive(PostPolicyDelivery(
        approval_operation_id=unknown, task_id=post_policy_task_id(unknown),
    )) == {"status":"delivery_rejected"}


@pytest.mark.parametrize("failure", ["revoked_service", "persistence"])
async def test_worker_failure_rolls_back_and_preserves_pending_approval(
    isolated_database_env, monkeypatch, post_policy_worker, failure,
):
    from sqlalchemy.exc import SQLAlchemyError
    from app.modules.projects.post_policy.service import PostPolicyService
    from app.adapters.projects import pending_post_policy_approvals

    async with public_approved_case(isolated_database_env, monkeypatch) as (
        factory, _, actor, _, approval_id, _,
    ):
        with monkeypatch.context() as patch:
            if failure == "revoked_service":
                async with factory() as session, session.begin():
                    await session.execute(text(
                        "UPDATE actor_identity_links SET status='revoked',revoked_at=now(),revoked_by=:by,"
                        "revoked_reason='Service access revoked' WHERE actor_profile_id IN "
                        "(SELECT id FROM actor_profiles WHERE service_identity='workstream.project.setup')"
                    ), {"by":str(actor.actor_profile_id)})
            else:
                persist = PostPolicyService._persist
                async def fail_after_flush(service, *args):
                    await persist(service, *args)
                    raise SQLAlchemyError("isolated post-write storage failure")
                patch.setattr(PostPolicyService, "_persist", fail_after_flush)
            outcome = await post_policy_worker._derive(PostPolicyDelivery(
                approval_operation_id=approval_id, task_id=post_policy_task_id(approval_id),
            ))
            assert outcome == {"status":"delivery_rejected" if failure == "revoked_service" else "derivation_unavailable"}
        async with factory() as session:
            for table in ("checker_policies", "project_post_policy_operations"):
                assert await session.scalar(text(f"SELECT count(*) FROM {table}")) == 0
            assert await session.scalar(text("SELECT count(*) FROM audit_events WHERE action_id='project.post_submit_checker_policy.derive'")) == 0
        assert await pending_post_policy_approvals(factory, after=None, limit=100) == [approval_id]
        if failure == "persistence":
            assert deliver(post_policy_worker, approval_id)["status"] == "policy_draft_ready"


async def test_scan_reaches_real_approval_after_rejected_delivery(
    isolated_database_env, monkeypatch, post_policy_worker,
):
    """Inject one unavailable metadata candidate; retain actual SQL selection and delivery."""
    async with public_approved_case(isolated_database_env, monkeypatch) as (
        factory, _, _, _, approval_id, _,
    ):
        real_pending = post_policy_worker.pending_post_policy_approvals
        unavailable = UUID(int=1)
        outcomes, next_pages = [], []
        async def candidates(sessions, *, after, limit):
            if after is None:
                return [unavailable]
            return await real_pending(sessions, after=after, limit=limit)
        async def publish(operation):
            result = await post_policy_worker._derive(PostPolicyDelivery(
                approval_operation_id=operation, task_id=post_policy_task_id(operation),
            ))
            outcomes.append((operation, result["status"]))
            return True
        monkeypatch.setattr(post_policy_worker, "POST_POLICY_SCAN_PAGE_SIZE", 1)
        monkeypatch.setattr(post_policy_worker, "pending_post_policy_approvals", candidates)
        monkeypatch.setattr(post_policy_worker, "dispatch_post_policy_derivation_after_commit", publish)
        monkeypatch.setattr(post_policy_worker.scan_post_policy_approvals, "apply_async", lambda **kw: next_pages.append(kw["args"][0]))
        post_policy_worker.scan_post_policy_approvals.apply(throw=True).get()
        assert next_pages == [str(unavailable)]
        post_policy_worker.scan_post_policy_approvals.apply(args=(next_pages.pop(0),), throw=True).get()
        assert outcomes == [(unavailable, "delivery_rejected"), (approval_id, "policy_draft_ready")]
        async with factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM project_post_policy_operations")) == 1


async def test_concurrent_worker_deliveries_commit_one_policy(
    isolated_database_env, monkeypatch, post_policy_worker,
):
    import asyncio

    async with public_approved_case(isolated_database_env, monkeypatch) as (
        factory, _, _, _, approval_id, _,
    ):
        delivery = PostPolicyDelivery(approval_operation_id=approval_id, task_id=post_policy_task_id(approval_id))
        first, second = await asyncio.gather(
            post_policy_worker._derive(delivery), post_policy_worker._derive(delivery),
        )
        assert first == second and first["status"] == "policy_draft_ready"
        async with factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM checker_policies")) == 1
            assert await session.scalar(text("SELECT count(*) FROM project_post_policy_operations")) == 1
            assert await session.scalar(text("SELECT count(*) FROM audit_events WHERE action_id='project.post_submit_checker_policy.derive'")) == 1
