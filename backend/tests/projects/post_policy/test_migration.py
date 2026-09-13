"""Retained post-policy custody cannot be removed by migration rollback."""

import pytest
from sqlalchemy import inspect, text

from migration_fixtures import run_alembic_revision
from app.modules.projects.post_policy.models import PostPolicyOperation
from tests.projects.guide_compilation.helpers import service_actor
from tests.projects.guide_compilation.proposals.pg_support import proposal_case
from .pg_support import prepare_post_policy, operate


async def test_downgrade_preserves_retained_post_policy_evidence(clean_postgres_database, capfd):
    async with proposal_case(clean_postgres_database) as (values, factory, command, actor, grant):
        setup = service_actor(values)
        payload, receipt = await prepare_post_policy(factory, command, actor, grant, setup)
        with pytest.raises(RuntimeError, match='isolated migration subprocess failed'):
            await run_alembic_revision('downgrade', '0019_guide_proposal_review')
        assert 'retained post-policy evidence prevents downgrade' in capfd.readouterr().err
        async with factory() as session:
            assert await session.scalar(text('SELECT version_num FROM alembic_version')) == '0020_post_submit_policy_custody'
        assert await operate(factory, setup, command.project_id, None, 'derive', payload) == receipt


async def test_post_policy_operation_model_matches_migrated_columns_and_relations(clean_postgres_database):
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(clean_postgres_database)
    try:
        async with engine.connect() as connection:
            def compare(sync):
                inspector = inspect(sync)
                table = PostPolicyOperation.__table__
                actual = inspector.get_columns(table.name)
                assert {(c['name'], str(c['type'].compile(dialect=sync.dialect)), c['nullable']) for c in actual} == {
                    (c.name, str(c.type.compile(dialect=sync.dialect)), c.nullable) for c in table.columns}
                actual_fks = {(tuple(fk['constrained_columns']), fk['referred_table'], tuple(fk['referred_columns']))
                              for fk in inspector.get_foreign_keys(table.name)}
                expected_fks = {(tuple(fk.column_keys), fk.referred_table.name,
                                 tuple(element.column.name for element in fk.elements))
                                for fk in table.foreign_key_constraints}
                assert actual_fks == expected_fks
                assert {tuple(item['column_names']) for item in inspector.get_unique_constraints(table.name)} == {
                    tuple(c.name for c in constraint.columns) for constraint in table.constraints
                    if constraint.__class__.__name__ == 'UniqueConstraint'}
            await connection.run_sync(compare)
    finally:
        await engine.dispose()
