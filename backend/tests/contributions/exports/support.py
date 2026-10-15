"""Signed callers over actual hidden accepted source facts and exact read audits."""

from uuid import UUID, uuid4

from sqlalchemy import text

from tests.authentication.support import issue_asymmetric_token
from tests.authorization.admin_access.support import SignedActor


async def prepared_reviewer_sibling(source):
    """One more valid Review source in the same project, without a contribution yet."""
    from app.core.identifiers import new_record_id
    from app.modules.contributions.records.schemas import ContributionRecordInput
    from tests.reviews.decision.support import attach_review_source, insert_review
    from tests.reviews.packet.support import prepare_packet
    from tests.tasks.post_submit_routing.support import completed_sibling_source

    sibling = await completed_sibling_source(source)
    await prepare_packet(sibling)
    await attach_review_source(sibling)
    async with sibling.factory() as session, session.begin():
        await insert_review(session, sibling.review)
    return ContributionRecordInput(
        id=new_record_id(), project_id=sibling.review.project_id,
        task_id=sibling.review.task_id, submission_id=sibling.review.submission_id,
        artifact_hash=sibling.review.artifact_hash, contribution_type="completed_review",
        contributor_id=sibling.review.reviewer_id, source_review_id=sibling.review.id,
        source_review_lease_id=sibling.review.review_lease_id,
        source_final_acceptance_id=None, source_task_assignment_id=None,
        contribution_policy_version_id=sibling.review.reviewer_contribution_policy_version_id,
    )


async def source_actor(signed, h):
    """Sign the actual identity link already used to create the canonical source."""
    actor_id = h.actor_context.actor_profile_id
    subject = f"human-{actor_id}"
    token = issue_asymmetric_token(signed.private_key, claims={"sub": subject, "jti": str(uuid4())})
    actor = SignedActor(actor_id, subject, token)
    response = await signed.client.get("/api/v1/actors/me", headers=actor.headers)
    assert response.status_code == 200 and response.json()["actor_profile_id"] == str(actor_id)
    return actor


def export_path(project_id):
    return f"/api/v1/projects/{project_id}/contributions/export"


async def export_audits(factory):
    async with factory() as session:
        result = (await session.execute(text("""
            SELECT action_id, permission_id, project_id, resource_type, resource_id,
                   target_ref_kind, target_ref_id, matched_grant_id, after_facts
            FROM public.audit_events WHERE action_id IN ('contribution.read_self','contribution.read_project')
            ORDER BY created_at,id
        """))).mappings()
        return [{key: str(value) if isinstance(value, UUID) else value for key, value in row.items()}
                for row in result]
