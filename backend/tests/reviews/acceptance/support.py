"""Direct storage fixtures, never authorized acceptance or lifecycle effects."""

from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import insert, text

from app.core.identifiers import new_record_id
from app.modules.reviews.acceptance.models import FinalAcceptance
from app.modules.reviews.acceptance.schemas import FinalAcceptanceInput
from tests.reviews.decision.support import finding, insert_review, review_source


@asynccontextmanager
async def acceptance_source(tmp_path, database_url, *, decision="accept", **options):
    async with review_source(tmp_path, database_url, **options) as h:
        h.review = h.review.model_copy(
            update={
                "decision": decision,
                "findings": (finding(),) if decision == "needs_revision" else (),
            }
        )
        async with h.factory() as session:
            await insert_review(session, h.review)
            await session.commit()
        await attach_acceptance(h)
        yield h


async def attach_acceptance(h):
    async with h.factory() as session:
        contributor = await session.scalar(
            text("SELECT contributor_id FROM public.submissions WHERE id=:id"),
            {"id": h.review.submission_id},
        )
    h.acceptance = FinalAcceptanceInput(
        id=new_record_id(),
        project_id=h.review.project_id,
        task_id=h.review.task_id,
        submission_id=h.review.submission_id,
        acceptance_source="human_review",
        source_review_id=h.review.id,
        source_routing_manifest_id=None,
        accepted_submitter_id=UUID(str(contributor)),
        recorded_by=h.review.reviewer_id,
        policy_context_ref=h.review.locked_review_policy_id,
    )


async def insert_acceptance(session, source, **overrides):
    values = source.model_dump()
    values.update(overrides)
    for field in (
        "project_id",
        "task_id",
        "submission_id",
        "accepted_submitter_id",
        "recorded_by",
        "policy_context_ref",
    ):
        if values[field] is not None:
            values[field] = str(values[field])
    await session.execute(insert(FinalAcceptance).values(**values))
