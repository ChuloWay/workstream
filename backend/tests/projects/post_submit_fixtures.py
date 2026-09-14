"""Arrange downstream post policy through the actual hidden projection and approval."""

from contextlib import contextmanager
from uuid import UUID, uuid4

from sqlalchemy import select

from app.modules.actors.models import ActorProfile, ActorIdentityLink
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.projects.api.guide_proposals import GuideProposalSelection
from app.modules.projects.api.post_policy import PostPolicyDerive, PostPolicyApproval
from app.modules.projects.guide_compilation.models import ProjectGuideProposalApproval
from tests.projects.post_policy.pg_support import operate


async def seed_post_submit_policy_for_downstream_tests(
    *, project_id: str, guide_id: str, source_snapshot: dict, pre_submit_checker_policy: dict, sessions,
) -> dict:
    """Use complete approved upstream custody; never fabricate an approved policy row."""
    async with sessions() as session:
        upstream = (await session.scalars(select(ProjectGuideProposalApproval).where(
            ProjectGuideProposalApproval.project_id == project_id,
            ProjectGuideProposalApproval.guide_id == guide_id,
            ProjectGuideProposalApproval.pre_submit_policy_id == pre_submit_checker_policy['id'],
        ))).one()
        assert upstream.target_json['source_snapshot_id'] == source_snapshot['id']
        assert upstream.target_json['source_snapshot_hash'] == source_snapshot['bundle_hash']
        setup_id, setup_link = (await session.execute(select(ActorProfile.id, ActorIdentityLink.id)
            .join(ActorIdentityLink, ActorIdentityLink.actor_profile_id == ActorProfile.id)
            .where(ActorProfile.service_identity == 'workstream.project.setup', ActorIdentityLink.status == 'active'))).one()
    actor = ActorIdentityFacts(UUID(upstream.actor_profile_id), UUID(upstream.identity_link_id), ActorKind.HUMAN)
    setup = ActorIdentityFacts(UUID(setup_id), UUID(setup_link), ActorKind.SERVICE, 'workstream.project.setup')
    selection = GuideProposalSelection(project_id=project_id, guide_id=guide_id, compilation_id=upstream.compilation_id)
    projected = await operate(sessions, setup, UUID(project_id), None, 'derive', PostPolicyDerive(
        selection=selection, upstream_approval_operation_id=upstream.operation_id,
        upstream_approval_output_digest=upstream.output_digest,
    ))
    approved = await operate(sessions, actor, UUID(project_id), upstream.admin_role_grant_id, 'approve', PostPolicyApproval(
        target=projected.target, idempotency_key=uuid4(),
    ))
    from app.modules.projects.models import PostSubmitCheckerPolicy
    async with sessions() as session:
        policy = await session.get(PostSubmitCheckerPolicy, str(approved.target.policy_id))
        return {key: getattr(policy, key) for key in (
            'id', 'required_checkers', 'warning_checkers', 'blocking_severities', 'policy_hash', 'policy_body',
            'lifecycle_status', 'projection_operation_id', 'approval_operation_id',
        )}



@contextmanager
def crossed_post_policy_read(policy_id):
    """Inject one corrupted read without modifying immutable stored evidence."""
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    from sqlalchemy.orm.attributes import set_committed_value
    from app.modules.projects.models import PostSubmitCheckerPolicy

    seen = []

    def loaded(_session, row):
        if isinstance(row, PostSubmitCheckerPolicy) and row.id == policy_id:
            seen.append(row.id)
            set_committed_value(row, 'required_checkers', [
                *row.required_checkers, 'check_acceptance_criteria_present',
            ])

    event.listen(Session, 'loaded_as_persistent', loaded)
    try:
        yield seen
    finally:
        event.remove(Session, 'loaded_as_persistent', loaded)
