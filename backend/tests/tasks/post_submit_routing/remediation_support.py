"""Real current contributor failure, router authority and invoked completion."""

from contextlib import asynccontextmanager

from sqlalchemy import text

from tests.authorization.post_submit_routing.support import provision_router
from tests.checkers.execution.completion_fixture import completed_evidence
from tests.tasks.post_submit_routing.outcome_support import invoked_completion


@asynccontextmanager
async def remediation_source(tmp_path, database_url, *, human_review_required=True):
    async with completed_evidence(
        tmp_path, database_url, human_review_required=human_review_required,
    ) as h:
        async with h.factory() as session, session.begin():
            await session.execute(text(
                "UPDATE public.task_assignments SET accepted_at=clock_timestamp() WHERE id=:id"
            ), {"id": h.request.assignment_id})
        await provision_router(h.factory)
        h.envelope = await invoked_completion(h)
        yield h


async def no_economic_effects(session):
    """Check every product owner that must remain absent for contributor failure."""
    for table in (
        "reviews", "review_findings", "review_queue_entries", "final_acceptances",
        "contribution_records", "compensation_awards",
    ):
        assert await session.scalar(text(f"SELECT count(*) FROM public.{table}")) == 0
