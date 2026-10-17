"""Retained predecessor contribution/economic rows for migrations only."""

from contextlib import asynccontextmanager
from uuid import UUID
from sqlalchemy import text
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.contributions.records.schemas import ContributionRecordInput
from tests.reviews.acceptance.historical_support import (
    historical_acceptance_source,
    insert_historical_acceptance,
)


@asynccontextmanager
async def historical_contribution_source(
    tmp_path,
    url,
    *,
    decision="accept",
    paid=False,
    persist_acceptance=True,
):
    if type(paid) is not bool:
        raise ValueError("Archived contribution paid selection must be boolean")
    snapshot_name = None
    if paid:
        async with db_session.get_session_factory()() as session:
            revision = await session.scalar(text("SELECT version_num FROM public.alembic_version"))
        if revision not in {
            "0015_contribution_awards", "0018_task_routing_request",
            "0024_require_second_review_false",
        }:
            raise ValueError("No archived paid contribution snapshot for this revision")
        snapshot_name = revision + "_paid"
    async with historical_acceptance_source(
        tmp_path,
        url,
        decision=decision,
        snapshot_name=snapshot_name,
    ) as h:
        async with h.factory() as session:
            if decision == "accept" and persist_acceptance:
                await insert_historical_acceptance(session, h.acceptance)
                await session.commit()
            row = (
                (
                    await session.execute(
                        text("""
                SELECT task_assignment_id, contribution_policy_version_id, contributor_id
                FROM public.submissions WHERE id=:id
            """),
                        {"id": h.review["submission_id"]},
                    )
                )
                .mappings()
                .one()
            )
        common = dict(
            project_id=h.review["project_id"],
            task_id=h.review["task_id"],
            submission_id=h.review["submission_id"],
            artifact_hash=h.review["artifact_hash"],
        )
        h.reviewer_record = ContributionRecordInput(
            **common,
            id=new_record_id(),
            contribution_type="completed_review",
            contributor_id=h.review["reviewer_id"],
            source_review_id=h.review["id"],
            source_review_lease_id=h.review["review_lease_id"],
            source_final_acceptance_id=None,
            source_task_assignment_id=None,
            contribution_policy_version_id=h.review["reviewer_contribution_policy_version_id"],
        )
        h.submitter_record = ContributionRecordInput(
            **common,
            id=new_record_id(),
            contribution_type="accepted_submission",
            contributor_id=UUID(str(row["contributor_id"])),
            source_review_id=None,
            source_review_lease_id=None,
            source_final_acceptance_id=h.acceptance["id"],
            source_task_assignment_id=UUID(str(row["task_assignment_id"])),
            contribution_policy_version_id=row["contribution_policy_version_id"],
        )
        yield h
