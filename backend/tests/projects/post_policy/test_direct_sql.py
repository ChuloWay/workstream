"""Bypass ORM persistence with complete otherwise-valid approval output custody."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
from app.modules.projects.api.post_policy import PostPolicyApproval
from app.modules.projects.post_policy.models import PostPolicyOperation
from app.modules.projects.post_policy.service import PostPolicyService
from tests.projects.guide_compilation.helpers import service_actor
from tests.projects.guide_compilation.proposals.pg_support import proposal_case
from .pg_support import PostAuthority, prepare_post_policy, operate
from .test_authority import foreign_manager, state


@pytest.mark.parametrize('change,error', [
    ('output_digest', 'post-policy operation lineage mismatch'),
    ('foreign_grant', 'guide proposal current authority missing'),
    ('wrong_action', 'post-policy authority evidence mismatch'),
])
async def test_direct_sql_rejects_one_substituted_commitment(clean_postgres_database, monkeypatch, change, error):
    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        _, projected = await prepare_post_policy(factory, command, actor, grant, service_actor(values))
        _, _, _, foreign_grant = await foreign_manager(factory, actor)
        payload = PostPolicyApproval(target=projected.target, idempotency_key=uuid4())
        before = await state(factory)
        async with factory() as session:
            await session.begin()
            captured = []
            original_add = session.add

            def capture_operation(row, **kwargs):
                if isinstance(row, PostPolicyOperation):
                    captured.append(row)
                else:
                    original_add(row, **kwargs)

            try:
                # Arrange actual outputs and decision; capture only the yet-unpersisted operation.
                with monkeypatch.context() as patch:
                    patch.setattr(session, 'add', capture_operation)
                    service = PostPolicyService(session, PostAuthority(session, actor, command.project_id, grant), current_post_submit_catalogue())
                    receipt = await service.approve(payload, actor=actor, request_id=uuid4())
                assert len(captured) == 1
                row = {c.name: getattr(captured[0], c.name) for c in PostPolicyOperation.__table__.columns}
                row['created_at'] = datetime.now(UTC)
                assert row['operation_id'] == receipt.operation_id
                if change == 'output_digest':
                    row['output_digest'] = 'sha256:'+'b'*64
                elif change == 'foreign_grant':
                    row['admin_role_grant_id'] = foreign_grant
                else:
                    wrong_event = str(uuid4())
                    await session.execute(text(
                        'INSERT INTO audit_events SELECT (jsonb_populate_record(NULL::audit_events, '
                        'to_jsonb(source)||CAST(:patch AS jsonb))).* FROM audit_events source WHERE id=:id'),
                        dict(id=row['authorization_decision_event_id'], patch=json.dumps(dict(
                            id=wrong_event, entity_id=wrong_event,
                            action_id='project.post_submit_checker_policy.correction.request'))))
                    row['authorization_decision_event_id'] = wrong_event
                await session.execute(text(
                    'INSERT INTO project_post_policy_operations SELECT '
                    '(jsonb_populate_record(NULL::project_post_policy_operations, CAST(:row AS jsonb))).*'),
                    dict(row=json.dumps(row, default=str)))
                # All immediate constraints pass; force this guard before other deferred constraints.
                with pytest.raises(DBAPIError, match=error):
                    await session.execute(text('SET CONSTRAINTS post_policy_operation_custody IMMEDIATE'))
            finally:
                await session.rollback()
        assert await state(factory) == before
        assert (await operate(factory, actor, command.project_id, grant, 'approve', payload)).kind == 'approve'


@pytest.mark.parametrize('classification', ['project_required', 'project_warning'])
async def test_database_rejects_unrequested_project_selection(clean_postgres_database, monkeypatch, classification):
    from app.modules.projects.post_policy import service
    from app.modules.projects.post_submit_policy import (
        build_project_post_submit_checker_spec, compile_project_post_submit_checker_spec,
    )
    from .pg_support import prepare_upstream

    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        payload = await prepare_upstream(factory, command, actor, grant)
        before = await state(factory)
        calls = []

        def extra_selection(*, project_id, guide_version, result, catalogue):
            assert result.post_submit_bindings == ()
            field = 'required_checkers' if classification == 'project_required' else 'warning_checkers'
            compiled = compile_project_post_submit_checker_spec(
                project_id=str(project_id), guide_version=guide_version,
                spec=build_project_post_submit_checker_spec(
                    project_id=str(project_id), guide_version=guide_version,
                    **{field: ['check_acceptance_criteria_present']}),
            )
            compiled.validate_catalogue(catalogue)
            calls.append(compiled)
            return compiled

        with monkeypatch.context() as patch:
            # Faulty compiler output remains a valid canonical body with real hash/custody.
            patch.setattr(service, 'compile_saved_post_policy', extra_selection)
            with pytest.raises(DBAPIError, match='post-policy compiled selection not requested'):
                await operate(factory, service_actor(values), command.project_id, None, 'derive', payload)
        assert len(calls) == 1
        assert calls[0].entries[-1].classification == classification
        assert await state(factory) == before
        # Platform defaults remain valid with no project bindings, including separate approval.
        projected = await operate(factory, service_actor(values), command.project_id, None, 'derive', payload)
        approved = await operate(factory, actor, command.project_id, grant, 'approve',
                                 PostPolicyApproval(target=projected.target, idempotency_key=uuid4()))
        assert approved.kind == 'approve'


@pytest.mark.parametrize('binding_count', [1, 2])
async def test_database_accepts_exact_selection_shared_by_requirements(clean_postgres_database, binding_count):
    from app.interfaces.project_agents import ProjectGuideCompilationResult
    from .test_compiler import selected_result

    body = selected_result()
    if binding_count == 2:
        body['requirements'].append(body['requirements'][0] | dict(requirement_id='criteria-two'))
        body['post_submit_bindings'].append(body['post_submit_bindings'][0] | dict(requirement_id='criteria-two'))
    outcome = ProjectGuideCompilationResult.model_validate(body)
    async with proposal_case(clean_postgres_database, outcome=outcome) as (values, factory, command, actor, grant):
        _, projected = await prepare_post_policy(factory, command, actor, grant, service_actor(values))
        approved = await operate(factory, actor, command.project_id, grant, 'approve',
                                 PostPolicyApproval(target=projected.target, idempotency_key=uuid4()))
        async with factory() as session:
            policy = await session.scalar(text('SELECT policy_body FROM checker_policies WHERE id=:id'),
                                          dict(id=str(projected.target.policy_id)))
        selections = [entry for entry in policy['entries'] if entry['classification'] != 'platform_default']
        assert len(selections) == 1
        assert selections[0]['checker_id'] == 'check_acceptance_criteria_present'
        assert selections[0]['classification'] == 'project_required'
        assert approved.kind == 'approve'


async def test_database_rejects_missing_required_selection(clean_postgres_database, monkeypatch):
    from app.interfaces.project_agents import ProjectGuideCompilationResult
    from app.modules.projects.post_policy import service
    from app.modules.projects.post_submit_policy import (
        build_project_post_submit_checker_spec, compile_project_post_submit_checker_spec,
    )
    from .pg_support import prepare_upstream
    from .test_compiler import selected_result

    async with proposal_case(clean_postgres_database, outcome=ProjectGuideCompilationResult.model_validate(
        selected_result()
    )) as (values, factory, command, actor, grant):
        payload = await prepare_upstream(factory, command, actor, grant)
        before = await state(factory)
        calls = []

        def missing_selection(*, project_id, guide_version, result, catalogue):
            assert len(result.post_submit_bindings) == 1
            compiled = compile_project_post_submit_checker_spec(
                project_id=str(project_id), guide_version=guide_version,
                spec=build_project_post_submit_checker_spec(project_id=str(project_id), guide_version=guide_version))
            compiled.validate_catalogue(catalogue)
            calls.append(compiled)
            return compiled

        with monkeypatch.context() as patch:
            patch.setattr(service, 'compile_saved_post_policy', missing_selection)
            with pytest.raises(DBAPIError, match='post-policy compiled required binding missing'):
                await operate(factory, service_actor(values), command.project_id, None, 'derive', payload)
        assert len(calls) == 1
        assert await state(factory) == before
        assert (await operate(factory, service_actor(values), command.project_id, None, 'derive', payload)).kind == 'derive'
