"""Current PostgreSQL review-policy semantics-shape proof."""

import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.projects.models import ReviewPolicy
from projects.client_fixtures import (
    project_client as project_client,
    project_database_env as project_database_env,
)
from projects.guide_fixtures import complete_guide_payload, create_guide, create_project


async def _selected(project_id: str, guide_version: str) -> ReviewPolicy:
    async with db_session.get_session_factory()() as session:
        policy = await session.scalar(
            text(
                "select id from review_policies where project_id=:project "
                "and guide_version=:version order by policy_generation desc limit 1"
            ),
            {"project": project_id, "version": guide_version},
        )
        assert policy is not None
        return await session.get(ReviewPolicy, policy)


@pytest.mark.parametrize(
    "human_review_required,semantics_format,expected",
    (
        (False, "v1", "review_policy_semantics_format"),
        (True, "v3", "review_policy_semantics_format"),
        (None, "v2", 'null value in column "human_review_required"'),
        (True, None, 'null value in column "semantics_format"'),
    ),
)
async def test_review_policy_shape_rejects_invalid_mode_and_format_combinations(
    project_client,
    human_review_required,
    semantics_format,
    expected,
) -> None:
    project = await create_project(project_client)
    guide = await create_guide(project_client, project["id"], complete_guide_payload())
    source = await _selected(project["id"], guide["version"])
    statement = text(
        "insert into review_policies select "
        "(jsonb_populate_record(null::review_policies, to_jsonb(p) || "
        "cast(:changes as jsonb))).* from review_policies p where p.id=:source"
    )
    engine = db_session.get_engine()
    async with engine.connect() as connection:
        transaction = await connection.begin()
        try:
            control_id = str(new_record_id())
            control = {
                "id": control_id,
                "policy_generation": source.policy_generation + 1,
                "supersedes_policy_id": source.id,
                "predecessor_policy_hash": source.policy_hash,
                "human_review_required": True,
                "semantics_format": "v2",
            }
            await connection.execute(
                statement,
                {"source": source.id, "changes": json.dumps(control)},
            )
            assert (
                await connection.scalar(
                    text("select count(*) from review_policies where id=:id"),
                    {"id": control_id},
                )
                == 1
            )

            changes = {
                **control,
                "id": str(new_record_id()),
                "policy_generation": source.policy_generation + 2,
                "human_review_required": human_review_required,
                "semantics_format": semantics_format,
            }
            with pytest.raises(DBAPIError, match=expected):
                async with connection.begin_nested():
                    await connection.execute(
                        statement,
                        {"source": source.id, "changes": json.dumps(changes)},
                    )
        finally:
            await transaction.rollback()
