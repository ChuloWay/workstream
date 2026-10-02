"""Real immutable source fixtures; no runtime recognition or payment authority."""

from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import insert, select, text

from app.core.identifiers import new_record_id
from app.modules.compensation.awards.models import CompensationAward
from app.modules.contributions.models import ContributionAwardDefinition
from app.modules.contributions.records.models import ContributionRecord
from app.modules.contributions.records.schemas import ContributionRecordInput
from tests.reviews.acceptance.support import acceptance_source, insert_acceptance


@asynccontextmanager
async def contribution_source(tmp_path, url, *, decision="accept", paid=False, persist_acceptance=True, **options):
    async with acceptance_source(
        tmp_path, url, decision=decision,
        contribution_awards=("money", "project_points") if paid else (), **options,
    ) as h:
        async with h.factory() as session:
            if decision == "accept" and persist_acceptance:
                await insert_acceptance(session, h.acceptance)
                await session.commit()
            row = (await session.execute(text("""
                SELECT task_assignment_id, contribution_policy_version_id, contributor_id
                FROM public.submissions WHERE id=:id
            """), {"id": h.review.submission_id})).mappings().one()
        common = dict(
            project_id=h.review.project_id, task_id=h.review.task_id,
            submission_id=h.review.submission_id, artifact_hash=h.review.artifact_hash,
        )
        h.reviewer_record = ContributionRecordInput(
            **common, id=new_record_id(), contribution_type="completed_review",
            contributor_id=h.review.reviewer_id, source_review_id=h.review.id,
            source_review_lease_id=h.review.review_lease_id, source_final_acceptance_id=None,
            source_task_assignment_id=None,
            contribution_policy_version_id=h.review.reviewer_contribution_policy_version_id,
        )
        h.submitter_record = ContributionRecordInput(
            **common, id=new_record_id(), contribution_type="accepted_submission",
            contributor_id=UUID(str(row["contributor_id"])), source_review_id=None,
            source_review_lease_id=None, source_final_acceptance_id=h.acceptance.id,
            source_task_assignment_id=UUID(str(row["task_assignment_id"])),
            contribution_policy_version_id=row["contribution_policy_version_id"],
        )
        yield h


async def insert_record(session, record, **changes):
    values = record.model_dump() | changes
    for name in ("project_id", "task_id", "submission_id", "contributor_id", "source_task_assignment_id"):
        if values[name] is not None:
            values[name] = str(values[name])
    await session.execute(insert(ContributionRecord).values(**values))


async def award_values(session, record):
    definitions = (await session.scalars(select(ContributionAwardDefinition).where(
        ContributionAwardDefinition.contribution_policy_version_id == record.contribution_policy_version_id,
        ContributionAwardDefinition.contribution_type == record.contribution_type,
    ).order_by(ContributionAwardDefinition.instrument_type))).all()
    return [dict(
        id=new_record_id(), project_id=record.project_id, contribution_record_id=record.id,
        contributor_id=record.contributor_id,
        contribution_policy_version_id=record.contribution_policy_version_id,
        award_definition_id=d.id, adapter_binding_id=d.adapter_binding_id,
        instrument_type=d.instrument_type, unit_code=d.unit_code, quantity=d.quantity,
        correlation_id=new_record_id(),
    ) for d in definitions]


async def insert_award(session, values, **changes):
    values = values | changes
    for name in ("project_id", "contributor_id"):
        values[name] = str(values[name])
    await session.execute(insert(CompensationAward).values(**values))


async def rows(session, table):
    assert table in {"contribution_records", "compensation_awards", "final_acceptances", "reviews"}
    return list((await session.scalars(text(
        f"SELECT to_jsonb(r) FROM public.{table} r ORDER BY id"
    ))).all())


async def retire_policy_and_suspend_bindings(h):
    """Change current availability through real Finance owners after work is frozen."""
    from types import SimpleNamespace
    from app.adapters.auth import compensation_adapter_binding_authorization
    from app.modules.actors.compensation_adapter import CompensationAdapterActorEligibility
    from app.modules.authorization.runtime import HumanAuthorizationContext, ActorKind, ActorStatus, IdentityLinkStatus
    from app.modules.compensation.api import AdapterBindingSuspendRequest
    from app.modules.compensation.service import AdapterBindingService
    from app.modules.projects.compensation_binding import ProjectCompensationBindingEligibility
    from tests.authorization.contribution_policies.postgresql_support import PolicyWorld
    from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor

    actor, grant = await seed_review_actor(h.factory, h.review.project_id, role="finance_authority")
    context = HumanAuthorizationContext(
        actor_profile_id=actor.actor_profile_id, identity_link_id=actor.identity_link_id,
        actor_kind=ActorKind.HUMAN, actor_status=ActorStatus.ACTIVE,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=new_record_id(), correlation_id=new_record_id(),
    )
    world = PolicyWorld(None, h.review.project_id, new_record_id(), context, str(grant))
    async with h.factory() as session, session.begin():
        policy_id = await session.scalar(text(
            "SELECT contribution_policy_id FROM public.contribution_policy_versions WHERE id=:id"
        ), {"id": h.submitter_record.contribution_policy_version_id})
        prior = SimpleNamespace(contribution_policy_id=policy_id,
                                contribution_policy_version_id=h.submitter_record.contribution_policy_version_id)
        await world.service(session).retire(world.request("retire", prior))
    async with h.factory() as session:
        bindings = (await session.execute(text(
            "SELECT DISTINCT adapter_binding_id FROM public.contribution_award_definitions "
            "WHERE contribution_policy_version_id=:id"
        ), {"id": prior.contribution_policy_version_id})).scalars().all()
    for binding in bindings:
        async with h.factory() as session, session.begin():
            service = AdapterBindingService(
                session, mutation_authorization=compensation_adapter_binding_authorization(session, context),
                projects=ProjectCompensationBindingEligibility(session),
                actors=CompensationAdapterActorEligibility(session),
            )
            await service.suspend(AdapterBindingSuspendRequest(
                operation_id=new_record_id(), actor_profile_id=context.actor_profile_id,
                project_id=h.review.project_id, adapter_binding_id=binding, expected_lifecycle_version=1,
            ))
    async with h.factory() as session:
        assert await session.scalar(text(
            "SELECT status FROM public.contribution_policy_versions WHERE id=:id"
        ), {"id": prior.contribution_policy_version_id}) == "retired"
        states = (await session.scalars(text(
            "SELECT status FROM public.project_compensation_adapter_bindings WHERE project_id=:id"
        ), {"id": h.review.project_id})).all()
        assert len(states) == 2 and set(states) == {"suspended"}
