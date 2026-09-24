"""Current-schema read-only guards for retained guide and runtime fields."""

import json

import pytest
from sqlalchemy import insert, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.identifiers import new_record_id
from app.modules.projects.guide_compilation.models import ProjectGuideCompilationAttempt
from project_create_fixtures import guide_example_columns
from .helpers import context, identity, seed_database


pytestmark = pytest.mark.postgres_schema_contract


async def test_retained_guide_content_and_compilation_runtime_are_read_only(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    attempt_identity = identity(context(values))
    attempt_id = new_record_id()
    row = attempt_identity.model_dump(mode="json") | {
        "id": attempt_id,
        "provider_idempotency_key": attempt_identity.provider_idempotency_key(),
        "status": "compilation_reserved",
    }
    engine = create_async_engine(clean_postgres_database)
    examples = guide_example_columns()
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "alter table project_guide_compilation_attempts disable trigger "
                    "project_guide_runtime_configuration_guard"
                )
            )
            await connection.execute(insert(ProjectGuideCompilationAttempt).values(**row))
            await connection.execute(
                text(
                    "alter table project_guide_compilation_attempts enable trigger "
                    "project_guide_runtime_configuration_guard"
                )
            )
            await connection.execute(
                text("alter table project_guides disable trigger retained_guide_content_guard")
            )
            await connection.execute(
                text("alter table project_guides disable trigger guide_mutation_product_custody")
            )
            await connection.execute(
                text(
                    "update project_guides set retained_content_markdown='retained original text' "
                    "where id=:id"
                ),
                {"id": str(values["guide"])},
            )
            await connection.execute(
                text("alter table project_guides enable trigger guide_mutation_product_custody")
            )
            await connection.execute(
                text("alter table project_guides enable trigger retained_guide_content_guard")
            )

        for statement, params in (
            (
                "update project_guides set retained_content_markdown='replacement' where id=:id",
                {"id": str(values["guide"])},
            ),
            (
                "insert into project_guides(id,project_id,version,status,"
                "retained_content_markdown,created_by,task_examples,task_examples_hash) "
                "values(:id,:project,'new-guide','draft','new inline body','fixture',"
                "cast(:examples as json),:examples_hash)",
                {
                    "id": str(new_record_id()),
                    "project": str(values["project"]),
                    "examples": json.dumps(examples["task_examples"]),
                    "examples_hash": examples["task_examples_hash"],
                },
            ),
        ):
            async with engine.begin() as connection:
                with pytest.raises(
                    DBAPIError, match="retained guide content is read only"
                ) as error:
                    await connection.execute(text(statement), params)
                assert error.value.orig.sqlstate == "23514"

        async with engine.begin() as connection:
            with pytest.raises(
                DBAPIError, match="retained compilation runtime is read only"
            ) as error:
                await connection.execute(
                    text(
                        "update project_guide_compilation_attempts "
                        "set status='compilation_provider_uncertain',provider_uncertain_at=now() "
                        "where id=:id"
                    ),
                    {"id": attempt_id},
                )
            assert error.value.orig.sqlstate == "23514"
    finally:
        await engine.dispose()
