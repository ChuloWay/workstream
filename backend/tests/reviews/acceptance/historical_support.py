"""Literal predecessor acceptance storage, never current acceptance authority."""

from contextlib import asynccontextmanager
from sqlalchemy import insert, text

from app.core.identifiers import new_record_id
from app.modules.reviews.acceptance.models import FinalAcceptance
from tests.migration_ancestor_rows import archived_review_ancestors, seed_review_row


@asynccontextmanager
async def historical_acceptance_source(tmp_path, database_url, *, decision="accept", **options):
    async with archived_review_ancestors(tmp_path, database_url, decision=decision, **options) as h:
        async with h.factory() as session, session.begin():
            await seed_review_row(session, h.review)
        await attach_historical_acceptance(h)
        yield h


async def attach_historical_acceptance(h):
    async with h.factory() as session:
        revision = await session.scalar(text("SELECT version_num FROM public.alembic_version"))
        assert 13 <= int(revision[:4]) <= 28
        contributor = await session.scalar(text(
            "SELECT contributor_id FROM public.submissions WHERE id=:id"
        ), {"id": h.review["submission_id"]})
    h.acceptance = {
        "id": new_record_id(), "project_id": h.review["project_id"], "task_id": h.review["task_id"],
        "submission_id": h.review["submission_id"], "acceptance_source": "human_review",
        "source_review_id": h.review["id"], "source_routing_manifest_id": None,
        "accepted_submitter_id": contributor, "recorded_by": h.review["reviewer_id"],
        "policy_context_ref": h.review["locked_review_policy_id"],
    }


async def insert_historical_acceptance(session, source, **overrides):
    revision = await session.scalar(text("SELECT version_num FROM public.alembic_version"))
    assert 14 <= int(revision[:4]) <= 28
    values = source | overrides
    for field in ("project_id", "task_id", "submission_id", "accepted_submitter_id", "recorded_by", "policy_context_ref"):
        values[field] = str(values[field])
    await session.execute(insert(FinalAcceptance).values(**values))
