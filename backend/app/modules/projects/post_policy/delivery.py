"""Recover deterministic derivation from committed upstream approval custody."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.authorization.api import ActorIdentityFacts, AuthorizationDenied
from app.modules.authorization.api.post_policy import PostPolicyAuthorizationPort
from app.modules.checkers.api.post_submit_catalogue import PostSubmitCatalogue
from app.modules.projects.api.guide_proposals import GuideProposalError, GuideProposalSelection
from app.modules.projects.api.post_policy import PostPolicyDelivery, PostPolicyDerive
from app.modules.projects.guide_compilation.models import (
    ProjectGuideCompilation, ProjectGuideProposalApproval,
)
from app.modules.projects.models import ProjectSetupRun, SubmissionArtifactPolicy

from .models import PostPolicyOperation
from .service import PostPolicyService

PostPolicyServiceAuthority = Callable[
    [AsyncSession, UUID],
    AbstractAsyncContextManager[tuple[PostPolicyAuthorizationPort, ActorIdentityFacts]],
]


async def pending_approval_ids(
    session: AsyncSession, *, after: UUID | None, limit: int,
) -> list[UUID]:
    """Page metadata only; current custody and authority are rechecked on delivery."""
    approval = ProjectGuideProposalApproval
    completed = exists().where(
        PostPolicyOperation.upstream_approval_operation_id == approval.operation_id,
        PostPolicyOperation.kind == "derive",
    )
    newer_setup = exists().where(
        ProjectSetupRun.guide_id == approval.guide_id,
        ProjectSetupRun.setup_generation > ProjectGuideCompilation.setup_generation,
    )
    query = (
        select(approval.operation_id)
        .join(SubmissionArtifactPolicy, SubmissionArtifactPolicy.id == approval.artifact_policy_id)
        .join(ProjectGuideCompilation, ProjectGuideCompilation.id == approval.compilation_id)
        .where(SubmissionArtifactPolicy.lifecycle_status == "approved", ~completed, ~newer_setup)
        .order_by(approval.operation_id).limit(limit)
    )
    if after is not None:
        query = query.where(approval.operation_id > after)
    return list(await session.scalars(query))


class PostPolicyDeliveryService:
    """Run the existing derive operation in its own fresh authorized transaction."""

    def __init__(
        self, sessions: async_sessionmaker[AsyncSession], *,
        authority: PostPolicyServiceAuthority, catalogue: PostSubmitCatalogue,
    ) -> None:
        self.sessions, self.authority, self.catalogue = sessions, authority, catalogue

    async def run(self, delivery: PostPolicyDelivery) -> dict:
        """Reload immutable selection, then leave all policy decisions to its owner."""
        delivery = PostPolicyDelivery.model_validate(delivery)
        async with self.sessions() as session:
            approval = ProjectGuideProposalApproval
            row = (await session.execute(select(
                approval.project_id, approval.guide_id, approval.compilation_id,
                approval.output_digest,
            ).where(approval.operation_id == delivery.approval_operation_id))).one_or_none()
            await session.rollback()
            if row is None:
                return {"status": "delivery_rejected"}
            command = PostPolicyDerive(
                selection=GuideProposalSelection(
                    project_id=row.project_id, guide_id=row.guide_id,
                    compilation_id=row.compilation_id,
                ),
                upstream_approval_operation_id=delivery.approval_operation_id,
                upstream_approval_output_digest=row.output_digest,
            )
            try:
                async with self.authority(session, delivery.task_id) as (authority, actor):
                    async with session.begin():
                        receipt = await PostPolicyService(session, authority, self.catalogue).derive(
                            command, actor=actor, request_id=delivery.task_id,
                        )
                return {"status": "policy_draft_ready", "policy_id": str(receipt.target.policy_id)}
            except AuthorizationDenied:
                return {"status": "delivery_rejected"}
            except GuideProposalError as exc:
                return {"status": "derivation_unavailable" if exc.code == "storage_unavailable"
                        else "delivery_rejected"}
