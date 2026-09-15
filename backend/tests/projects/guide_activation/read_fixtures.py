"""Activate the existing approved public-flow fixture through CP07 custody."""

from uuid import UUID, uuid4

from sqlalchemy import select

from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.projects.api.post_policy import PostPolicyReceipt
from app.modules.projects.models import PostSubmitCheckerPolicy, ProjectGuide
from app.modules.projects.post_policy.models import PostPolicyOperation
from .pg_support import activation_command, activation_service, publish_policy


async def activate_approved_guide(factory, *, project_id, guide_id):
    async with factory() as session:
        policy = (
            await session.scalars(
                select(PostSubmitCheckerPolicy).where(
                    PostSubmitCheckerPolicy.project_id == project_id,
                    PostSubmitCheckerPolicy.guide_id == guide_id,
                    PostSubmitCheckerPolicy.lifecycle_status == "approved",
                )
            )
        ).one()
        approval = await session.get(PostPolicyOperation, policy.approval_operation_id)
        approved = PostPolicyReceipt.model_validate(approval.receipt_json)
        actor = ActorIdentityFacts(
            UUID(approval.actor_profile_id), UUID(approval.identity_link_id), ActorKind.HUMAN
        )
        grant = approval.admin_role_grant_id
    _, contribution = await publish_policy(factory, UUID(project_id))
    command = await activation_command(factory, approved, contribution)
    async with factory() as session, session.begin():
        receipt = await activation_service(session, actor, command, grant).activate(
            command, actor=actor, request_id=uuid4()
        )
    async with factory() as session:
        guide = await session.get(ProjectGuide, guide_id)
        return {
            "guide": {
                "id": guide.id,
                "version": guide.version,
                "status": guide.status,
                "approved_by": guide.approved_by,
                "effective_at": receipt.effective_at.isoformat(),
            }
        }
