"""Same-session composition for public project-manager post-policy operations."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth import guide_proposal_authorization, post_policy_authorization
from app.adapters.projects import project_post_policy_service
from app.api.deps.authorization import (
    _authorization_context, get_authorization_actor, get_authorization_actor_identity,
)
from app.core.api_controls import request_ids
from app.db.session import get_db_session
from app.modules.authorization.api import ActorIdentityFacts
from app.modules.authorization.api.guide_proposal_review import GuideProposalAuthorizationPort
from app.modules.checkers.api.post_submit_catalogue import (
    CompiledPostSubmitPolicy, current_post_submit_catalogue,
)
from app.modules.projects.api.post_policy import PostPolicyOperationsPort


@dataclass(frozen=True)
class PostPolicyRequest:
    """Explicit product and both correction authorities in one root transaction."""

    session: AsyncSession
    service: PostPolicyOperationsPort[
        ActorIdentityFacts, GuideProposalAuthorizationPort, CompiledPostSubmitPolicy,
    ]
    guide_authorization: GuideProposalAuthorizationPort
    actor: ActorIdentityFacts
    request_id: UUID


async def get_post_policy_request(
    request: Request,
    resolved: Annotated[Any, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[PostPolicyRequest]:
    """End identity reads before the canonical owner prepares authority and locks."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    context = _authorization_context(resolved, request_id, correlation_id)
    actor = await get_authorization_actor_identity(resolved)
    await session.rollback()
    try:
        async with session.begin():
            yield PostPolicyRequest(
                session,
                project_post_policy_service(
                    session, post_policy_authorization(session, context),
                    current_post_submit_catalogue(),
                ),
                guide_proposal_authorization(session, context), actor, request_id,
            )
    finally:
        if session.in_transaction():
            await session.rollback()
