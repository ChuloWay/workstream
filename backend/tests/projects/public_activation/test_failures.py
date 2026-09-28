"""Public activation preserves exact selections and rolls back failed responses."""

from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.guide_activation.service import GuideActivationService
from .support import activation_case, activation_state


@pytest.mark.parametrize('mismatched_id', ['project_id', 'guide_id'])
async def test_path_body_mismatch_never_calls_activation(
    isolated_database_env, monkeypatch, post_policy_worker, mismatched_id,
):
    async with activation_case(isolated_database_env, monkeypatch, post_policy_worker) as (
        factory, command, _, _, manager, _, _, path, body, _, _,
    ):
        before = await activation_state(factory, command.guide_id)
        original = GuideActivationService.activate
        calls = []

        async def tracked(owner, *args, **kwargs):
            calls.append((args, kwargs))
            return await original(owner, *args, **kwargs)

        monkeypatch.setattr(GuideActivationService, 'activate', tracked)
        # Keep the complete valid body unchanged; substitute only one URL identity.
        mismatch_path = path.replace(str(getattr(command, mismatched_id)), str(uuid4()))
        response = await manager.post(
            mismatch_path, json=body, headers={'Idempotency-Key': str(uuid4())},
        )
        assert response.status_code == 404, response.text
        assert response.json()['error']['code'] == 'proposal_unavailable'
        assert calls == []
        assert await activation_state(factory, command.guide_id) == before

        # The same body can activate through the matching URL.
        accepted = await manager.post(
            path, json=body, headers={'Idempotency-Key': str(uuid4())},
        )
        assert accepted.status_code == 200, accepted.text
        assert len(calls) == 1


async def test_independently_stale_selections_cannot_activate(isolated_database_env, monkeypatch, post_policy_worker):
    async with activation_case(isolated_database_env, monkeypatch, post_policy_worker) as (
        factory, command, _, _, manager, _, _, path, body, _, _,
    ):
        before = await activation_state(factory, command.guide_id)
        changes = [
            {'guide_mutation_generation': body['guide_mutation_generation'] + 1},
            {'expected_previous_active_guide_id': str(uuid4()), 'expected_previous_active_guide_generation': 1},
            {'review': body['review'] | {'generation': body['review']['generation'] + 1}},
            {'revision': body['revision'] | {'generation': body['revision']['generation'] + 1}},
            {'contribution_policy_version_id': str(uuid4())},
            {'post_approval_output_digest': 'sha256:' + '0' * 64},
        ]
        for change in changes:
            response = await manager.post(path, json=deepcopy(body) | change, headers={'Idempotency-Key': str(uuid4())})
            assert response.status_code == 409, (change, response.text)
            assert response.json()['error']['code'] == 'proposal_stale'
            assert await activation_state(factory, command.guide_id) == before
        response = await manager.post(path, json=body, headers={'Idempotency-Key': str(uuid4())})
        assert response.status_code == 200, response.text


@pytest.mark.parametrize('failure', ['validation', 'serialization'])
async def test_response_failure_rolls_back_activation_and_authority(isolated_database_env, monkeypatch, post_policy_worker, failure):
    async with activation_case(isolated_database_env, monkeypatch, post_policy_worker) as (
        factory, command, _, _, manager, _, _, path, body, _, _,
    ):
        before = await activation_state(factory, command.guide_id)
        original = GuideActivationService.activate
        async def corrupt(owner, *args, **kwargs):
            receipt = await original(owner, *args, **kwargs)
            assert await owner.session.scalar(text("select count(*) from guide_mutation_idempotency_records where action_id='project.guide.activate'")) == 1
            assert await owner.session.scalar(text("select count(*) from audit_events where action_id='project.guide.activate'")) == 1
            return receipt.model_copy(update={'activation_generation': 0} if failure == 'validation' else {'effective_at': object()})
        with monkeypatch.context() as patch:
            patch.setattr(GuideActivationService, 'activate', corrupt)
            response = await manager.post(path, json=body, headers={'Idempotency-Key': str(uuid4())})
        assert response.status_code == 503, response.text
        assert await activation_state(factory, command.guide_id) == before


async def test_real_audit_insert_failure_rolls_back(isolated_database_env, monkeypatch, post_policy_worker):
    async with activation_case(isolated_database_env, monkeypatch, post_policy_worker) as (
        factory, command, _, _, manager, _, _, path, body, _, _,
    ):
        before = await activation_state(factory, command.guide_id)
        async with factory() as session, session.begin():
            await session.execute(text("CREATE FUNCTION fail_activation_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test audit insert rejected' USING ERRCODE='23514'; END $$"))
            await session.execute(text("CREATE TRIGGER fail_activation_audit BEFORE INSERT ON audit_events FOR EACH ROW WHEN (NEW.action_id='project.guide.activate') EXECUTE FUNCTION fail_activation_audit()"))
        try:
            response = await manager.post(path, json=body, headers={'Idempotency-Key': str(uuid4())})
            assert response.status_code == 503, response.text
            assert await activation_state(factory, command.guide_id) == before
        finally:
            async with factory() as session, session.begin():
                await session.execute(text("DROP TRIGGER fail_activation_audit ON audit_events"))
                await session.execute(text("DROP FUNCTION fail_activation_audit()"))


@pytest.mark.parametrize('failure', ['validation', 'serialization'])
async def test_context_response_failure_rolls_back_read_evidence(isolated_database_env, monkeypatch, post_policy_worker, failure):
    from app.modules.projects.post_policy.service import PostPolicyService

    async with activation_case(isolated_database_env, monkeypatch, post_policy_worker) as (
        factory, _, _, _, manager, _, policy_path, _, _, _, _,
    ):
        async def evidence_count():
            async with factory() as session:
                return await session.scalar(text("select count(*) from audit_events"))
        before = await evidence_count()
        original = PostPolicyService.review_package
        async def corrupt(owner, *args, **kwargs):
            package = await original(owner, *args, **kwargs)
            assert await owner.session.scalar(text("select count(*) from audit_events")) == before + 1
            context = package.activation_context.model_copy(update={
                'guide_mutation_generation': 0 if failure == 'validation' else object(),
            })
            return package.model_copy(update={'activation_context': context})
        with monkeypatch.context() as patch:
            patch.setattr(PostPolicyService, 'review_package', corrupt)
            response = await manager.get(policy_path)
        assert response.status_code == 503, response.text
        assert await evidence_count() == before


async def test_retired_displayed_contribution_selection_is_not_replaced(isolated_database_env, monkeypatch, post_policy_worker):
    async with activation_case(isolated_database_env, monkeypatch, post_policy_worker) as (
        factory, command, _, _, manager, finance, policy_path, path, body, _, version_path,
    ):
        before = await activation_state(factory, command.guide_id)
        retired = await finance.post(version_path + '/retirement', json={}, headers={'Idempotency-Key': str(uuid4())})
        assert retired.status_code == 200, retired.text
        display = await manager.get(policy_path)
        assert display.status_code == 200, display.text
        assert display.json()['activation_context']['contribution'] is None
        rejected = await manager.post(path, json=body, headers={'Idempotency-Key': str(uuid4())})
        assert rejected.status_code == 409, rejected.text
        assert rejected.json()['error']['code'] == 'proposal_stale'
        assert await activation_state(factory, command.guide_id) == before
