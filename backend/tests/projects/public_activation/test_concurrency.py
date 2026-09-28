"""Public context and Finance retirement serialize at the same PROJECT root."""

import asyncio
from uuid import uuid4

from sqlalchemy import text

from app.adapters.projects.contribution_validation import GuideContributionPolicyDiscovery
from app.modules.projects.contribution_policy import ProjectContributionPolicyEligibility
from tests.auth_concurrency_support import wait_for_named_database_lock
from .support import activation_case, activation_state


async def test_context_holds_project_until_finance_retirement_can_commit(isolated_database_env, monkeypatch, post_policy_worker):
    async with activation_case(isolated_database_env, monkeypatch, post_policy_worker) as (
        _, _, _, _, manager, finance, policy_path, _, body, _, version_path,
    ):
        held, release, started = asyncio.Event(), asyncio.Event(), asyncio.Event()
        pids = {}
        waiter = 'activation-context-' + uuid4().hex
        read_selection = GuideContributionPolicyDiscovery.published_selection
        lock_project = ProjectContributionPolicyEligibility.lock_contribution_policy_project

        async def hold_selection(adapter, project_id):
            selection = await read_selection(adapter, project_id)
            held.set()
            await release.wait()
            return selection

        async def name_retirement(owner, project_id):
            pids['waiter'] = await owner._session.scalar(text('select pg_backend_pid()'))
            await owner._session.execute(text("select set_config('application_name',:name,true)"), {'name': waiter})
            started.set()
            return await lock_project(owner, project_id)

        with monkeypatch.context() as patch:
            patch.setattr(GuideContributionPolicyDiscovery, 'published_selection', hold_selection)
            patch.setattr(ProjectContributionPolicyEligibility, 'lock_contribution_policy_project', name_retirement)
            reader = asyncio.create_task(manager.get(policy_path))
            tasks = [reader]
            try:
                await asyncio.wait_for(held.wait(), 15)
                retiring = asyncio.create_task(finance.post(version_path + '/retirement', json={}, headers={'Idempotency-Key': str(uuid4())}))
                tasks.append(retiring)
                await asyncio.wait_for(started.wait(), 15)
                await asyncio.wait_for(wait_for_named_database_lock(isolated_database_env, waiter, expected_waiter_pid=pids['waiter']), 15)
                assert not retiring.done()
                release.set()
                displayed, retired = await asyncio.wait_for(asyncio.gather(*tasks), 30)
                assert displayed.status_code == 200, displayed.text
                assert displayed.json()['activation_context']['contribution']['contribution_policy_version_id'] == body['contribution_policy_version_id']
                assert retired.status_code == 200, retired.text
            finally:
                release.set()
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
        refreshed = await manager.get(policy_path)
        assert refreshed.status_code == 200, refreshed.text
        assert refreshed.json()['activation_context']['contribution'] is None


async def test_competing_public_activations_commit_one_guide_generation(isolated_database_env, monkeypatch, post_policy_worker):
    async with activation_case(isolated_database_env, monkeypatch, post_policy_worker) as (
        factory, command, _, _, manager, _, _, path, body, _, _,
    ):
        responses = await asyncio.wait_for(asyncio.gather(*(
            manager.post(path, json=body, headers={'Idempotency-Key': str(uuid4())}) for _ in range(2)
        )), 30)
        assert sorted(r.status_code for r in responses) == [200, 404], [r.text for r in responses]
        async with factory() as session:
            assert await session.scalar(text("select count(*) from guide_mutation_idempotency_records where action_id='project.guide.activate'")) == 1
            assert await session.scalar(text('select mutation_generation from project_guides where id=:id'), {'id': str(command.guide_id)}) == body['guide_mutation_generation'] + 1


async def test_wrong_project_public_requests_do_not_wait_on_foreign_guide(isolated_database_env, monkeypatch, post_policy_worker):
    import json
    from app.core.hashing import canonical_json_hash
    from app.modules.projects.api.guide_activation import GuideActivationInput
    from app.core.identifiers import new_record_id
    from tests.project_create_fixtures import seed_authorized_project
    from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor

    async with activation_case(isolated_database_env, monkeypatch, post_policy_worker) as (
        factory, command, actor, _, manager, _, policy_path, path, body, _, _,
    ):
        other = new_record_id()
        async with factory() as session, session.begin():
            await seed_authorized_project(session, project_id=str(other), name='Other project', slug='other-' + uuid4().hex)
        await seed_review_actor(factory, other, actor=actor)
        # Supply a structurally consistent request under the manager's other project.
        foreign_body = json.loads(json.dumps(body).replace(str(command.project_id), str(other)))
        target = foreign_body['target']
        target['upstream']['target_digest'] = canonical_json_hash(target['proposal'])
        target['upstream_output_digest'] = canonical_json_hash(target['upstream'])
        assert GuideActivationInput.model_validate(foreign_body).target.proposal.project_id == other
        before = await activation_state(factory, command.guide_id)
        async with factory() as holder, holder.begin():
            await holder.execute(text('select id from project_guides where id=:id for update'), {'id': str(command.guide_id)})
            read = await asyncio.wait_for(manager.get(policy_path.replace(str(command.project_id), str(other))), 5)
            activate = await asyncio.wait_for(manager.post(
                path.replace(str(command.project_id), str(other)), json=foreign_body,
                headers={'Idempotency-Key': str(uuid4())},
            ), 5)
            assert read.status_code == activate.status_code == 404, (read.text, activate.text)
        assert await activation_state(factory, command.guide_id) == before
