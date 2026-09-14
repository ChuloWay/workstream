"""Post-commit publication; immutable approvals are the durable recovery source."""

import asyncio
import logging
from uuid import UUID

from celery.exceptions import CeleryError
from kombu.exceptions import KombuError

from app.modules.projects.api.post_policy import post_policy_task_id
from app.workers.errors import CeleryConfigurationError
from app.workers.task_settings import sync_task_settings

logger = logging.getLogger(__name__)


def enqueue_derivation(approval_operation_id: UUID) -> None:
    """Publish the exact approved chain without resolving any policy or principal."""
    from app.workers.post_policy import derive_post_policy

    sync_task_settings(derive_post_policy)
    derive_post_policy.apply_async(
        args=(str(approval_operation_id),),
        task_id=str(post_policy_task_id(approval_operation_id)),
    )


async def dispatch_after_commit(approval_operation_id: UUID) -> bool:
    """Keep committed approval successful when the broker needs later recovery."""
    try:
        await asyncio.to_thread(enqueue_derivation, approval_operation_id)
    except (CeleryConfigurationError, CeleryError, KombuError, OSError):
        logger.warning("post-policy publication unavailable; approval retained for recovery")
        return False
    return True
