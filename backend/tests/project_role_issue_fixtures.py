"""Shared real role-issuance helpers independent of retired checker execution."""

from uuid import UUID

from app.core.identifiers import new_record_id
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service import ResolvedActor
from app.modules.authorization import router as authorization_router
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.project_role_schemas import ProjectRoleGrantIssueBody
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    HumanAuthorizationContext,
    IdentityLinkStatus,
)


def issue_body(target_actor_id: UUID) -> ProjectRoleGrantIssueBody:
    """Build the exact bounded reviewer grant request used by concurrency tests."""
    return ProjectRoleGrantIssueBody.model_validate({
        "target_actor_profile_id": target_actor_id,
        "role": "reviewer",
        "reason": "Concurrent project-role issue lock-order proof",
        "qualification": {
            "skills_snapshot": {
                "availability": "available",
                "reference_ids": ["skill:reviewer"],
                "unavailable_reason": None,
            },
            "reputation_snapshot": {
                "availability": "unavailable",
                "reference_ids": [],
                "unavailable_reason": "no_record",
            },
            "prior_project_work_refs": [],
            "external_expertise_refs": [],
        },
    })


async def issue_runtime(session, actor_id: UUID, link_id: UUID):
    """Compose the real prepared role authority for an existing manager."""
    context = HumanAuthorizationContext(
        actor_profile_id=actor_id,
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=link_id,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=new_record_id(),
        correlation_id=new_record_id(),
    )
    repository = AdminAuthorizationRepository(session)
    authority = AuthorizationService(session, context, admin_repository=repository)
    prepared = PreparedAuthorizationService(session, context, authority, repository)
    profile = await session.get(ActorProfile, str(actor_id))
    link = await session.get(ActorIdentityLink, str(link_id))
    assert profile is not None and link is not None
    await session.commit()
    return prepared, ResolvedActor(profile, link)


async def issue_role(session, project_id, body, issue_key, resolved, prepared):
    """Invoke the actual project-role route owner and preserve rollback behavior."""
    try:
        return await authorization_router.issue_project_role_grant(
            project_id=project_id,
            payload=body,
            idempotency_key=issue_key,
            resolved=resolved,
            prepared=prepared,
            session=session,
        )
    except BaseException:
        await session.rollback()
        raise
