"""Forward/reverse schema proof with retained-evidence protection."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from migration_fixtures import run_alembic_revision


async def test_empty_proposal_migration_round_trip(clean_postgres_database):
    engine = create_async_engine(clean_postgres_database)

    async def definitions():
        async with engine.connect() as connection:
            functions = (
                await connection.execute(
                    text(
                        "SELECT proname,pg_get_functiondef(p.oid) FROM pg_proc p "
                        "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' "
                        "AND p.prokind='f' ORDER BY proname,p.oid::regprocedure::text"
                    )
                )
            ).all()
            constraints = (
                await connection.execute(
                    text(
                        "SELECT conrelid::regclass::text,conname,pg_get_constraintdef(oid) "
                        "FROM pg_constraint WHERE connamespace='public'::regnamespace "
                        "ORDER BY conrelid::regclass::text,conname"
                    )
                )
            ).all()
            return functions, constraints

    try:
        before = await definitions()
        await run_alembic_revision("downgrade", "0018_guide_document_creation")
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT to_regclass('project_guide_proposal_approvals')")
                )
                is None
            )
            assert (
                await connection.scalar(
                    text("SELECT to_regclass('project_guide_proposal_corrections')")
                )
                is None
            )
        await run_alembic_revision("upgrade", "head")
        assert await definitions() == before
    finally:
        await engine.dispose()
