"""Compose the existing guide activation owner inside one request transaction."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth import guide_activation_authorization
from app.adapters.checkers import project_guide_approval_compiler
from app.adapters.contributions import contribution_policy_validation_port
from app.adapters.projects import project_guide_activation_port
from app.adapters.projects.contribution_validation import GuideContributionPolicyValidation
from app.api.deps.authorization import (
    _authorization_context, get_authorization_actor, get_authorization_actor_identity,
)
from app.core.api_controls import request_ids
from app.db.session import get_db_session
from app.modules.authorization.api import ActorIdentityFacts
from app.modules.projects.api.guide_activation import GuideActivationPort


@dataclass(frozen=True)
class ActivationRequest:
    """Explicit authenticated identity and transaction-bound activation owner."""

    session: AsyncSession
    service: GuideActivationPort[ActorIdentityFacts]
    actor: ActorIdentityFacts
    request_id: UUID


async def get_activation_request(
    request: Request,
    resolved: Annotated[Any, Depends(get_authorization_actor)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncIterator[ActivationRequest]:
    """End identity reads before preparing AUTH and taking product locks."""
    request_id, correlation_id = (UUID(value) for value in request_ids(request))
    context = _authorization_context(resolved, request_id, correlation_id)
    actor = await get_authorization_actor_identity(resolved)
    await session.rollback()
    planner, pre, post = project_guide_approval_compiler()
    try:
        async with session.begin():
            yield ActivationRequest(
                session,
                project_guide_activation_port(
                    session,
                    contribution=GuideContributionPolicyValidation(contribution_policy_validation_port(session)),
                    planner=planner, pre_catalogue=pre, post_catalogue=post,
                    authorization=guide_activation_authorization(session, context),
                ),
                actor, request_id,
            )
    finally:
        if session.in_transaction():
            await session.rollback()
