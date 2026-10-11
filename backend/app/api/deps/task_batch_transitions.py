"""Compose a batch root inside the existing canonical Task denial lifecycle."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.authorization import get_authorization_actor_identity, get_task_commands
from app.db.session import get_db_session
from app.modules.authorization.api import ActorIdentityFacts
from app.modules.tasks.api.task_batch_transition import TaskBatchTransitionPort


async def get_task_batch_transition_commands(
    identity: Annotated[ActorIdentityFacts, Depends(get_authorization_actor_identity)],
    tasks: Annotated[object, Depends(get_task_commands)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TaskBatchTransitionPort:
    """Reuse the actual issuing AUTH owner for rollback and denial-only restaging."""
    from app.adapters.tasks import task_batch_transition_commands

    return task_batch_transition_commands(
        session, tasks=tasks, actor_profile_id=identity.actor_profile_id,
        identity_link_id=identity.identity_link_id,
    )
