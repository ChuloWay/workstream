"""Current post-policy model and database schema parity."""

from sqlalchemy import inspect

from app.modules.projects.post_policy.models import PostPolicyOperation


async def test_post_policy_operation_model_matches_current_columns_and_relations(
    clean_postgres_database,
):
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(clean_postgres_database)
    try:
        async with engine.connect() as connection:

            def compare(sync):
                inspector = inspect(sync)
                table = PostPolicyOperation.__table__
                actual = inspector.get_columns(table.name)
                assert {
                    (c["name"], str(c["type"].compile(dialect=sync.dialect)), c["nullable"])
                    for c in actual
                } == {
                    (c.name, str(c.type.compile(dialect=sync.dialect)), c.nullable)
                    for c in table.columns
                }
                actual_fks = {
                    (
                        tuple(fk["constrained_columns"]),
                        fk["referred_table"],
                        tuple(fk["referred_columns"]),
                    )
                    for fk in inspector.get_foreign_keys(table.name)
                }
                expected_fks = {
                    (
                        tuple(fk.column_keys),
                        fk.referred_table.name,
                        tuple(element.column.name for element in fk.elements),
                    )
                    for fk in table.foreign_key_constraints
                }
                assert actual_fks == expected_fks
                assert {
                    tuple(item["column_names"])
                    for item in inspector.get_unique_constraints(table.name)
                } == {
                    tuple(c.name for c in constraint.columns)
                    for constraint in table.constraints
                    if constraint.__class__.__name__ == "UniqueConstraint"
                }

            await connection.run_sync(compare)
    finally:
        await engine.dispose()
