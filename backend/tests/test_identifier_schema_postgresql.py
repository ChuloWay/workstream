"""Real PostgreSQL enforcement, independent of ORM input validation."""

from collections.abc import Callable
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.identifiers import new_record_id
from app.db import models  # noqa: F401 - compile the complete registered graph
from app.db.base import Base
from app.modules.actors.models import ActorProfile


async def test_native_uuid_metadata_checks_compile_in_postgresql(
    isolated_database_env: str,
) -> None:
    """The ORM must compile too; a corrected SQL baseline cannot hide raw text operators."""
    engine = create_async_engine(isolated_database_env)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(text("create schema uuid_metadata_check"))
                translated = await connection.execution_options(
                    schema_translate_map={None: "uuid_metadata_check"},
                )
                await translated.run_sync(Base.metadata.create_all)
            finally:
                # All schema objects are owned by this isolated test transaction.
                await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "invalid_identity",
    [
        uuid4,
        lambda: uuid5(NAMESPACE_URL, "workstream:invalid-row-id"),
        lambda: UUID(int=new_record_id().int & ~(3 << 62)),
    ],
    ids=["uuid4", "uuid5", "non_rfc_variant"],
)
async def test_native_uuid_round_trip_and_direct_sql_version_guard(
    isolated_database_env: str,
    invalid_identity: Callable[[], UUID],
) -> None:
    engine = create_async_engine(isolated_database_env)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    identity = new_record_id()
    insert = text(
        "insert into actor_profiles "
        "(id, actor_kind, status, provisioning_method, created_by) "
        "values (:id, 'human', 'active', 'automatic_first_access', 'uuid7-proof')"
    )
    try:
        async with sessions() as session, session.begin():
            # These are parseable UUIDs: failure must be the version/variant guard,
            # not parsing, missing fields, or an unrelated business constraint.
            with pytest.raises(IntegrityError, match="ck_actor_profiles_id_uuid7"):
                async with session.begin_nested():
                    await session.execute(insert, {"id": invalid_identity()})
            await session.execute(insert, {"id": identity})
            native, sql_type = (await session.execute(
                text("select id, pg_typeof(id)::text from actor_profiles where id=:id"),
                {"id": identity},
            )).one()
            assert isinstance(native, UUID) and native == identity
            assert native.version == 7 and sql_type == "uuid"
            profile = await session.scalar(select(ActorProfile).where(ActorProfile.id == str(identity)))
            assert profile is not None and profile.id == str(identity)
            # Rollback keeps this probe from creating a retained actor.
            await session.rollback()
        async with sessions() as observer:
            assert await observer.get(ActorProfile, str(identity)) is None
    finally:
        await engine.dispose()
