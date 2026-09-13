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
