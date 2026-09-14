"""Durable delivery of deterministic setup policies; no agent or document ports."""

from uuid import UUID

from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.auth import post_policy_service_authority
from app.adapters.projects import (
    dispatch_post_policy_derivation_after_commit, pending_post_policy_approvals,
    project_post_policy_delivery_port,
)
from app.db.session import get_database_url
from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue
from app.modules.projects.api.post_policy import PostPolicyDelivery
from app.workers.async_runner import run_async_task
from app.workers.celery_app import celery_app

POST_POLICY_SCAN_PAGE_SIZE = 100
logger = get_task_logger(__name__)


@celery_app.task(
    name="workstream.project_setup.derive_post_policy", bind=True,
    acks_late=True, reject_on_worker_lost=True,
)
def derive_post_policy(self, approval_operation_id):
    """Fence the actual broker task identity and retry bounded infrastructure failures."""
    try:
        delivery = PostPolicyDelivery(
            approval_operation_id=approval_operation_id, task_id=self.request.id,
        )
    except (TypeError, ValueError):
        return {"status": "delivery_rejected"}
    outcome = run_async_task(lambda: _derive(delivery))
    if outcome["status"] == "derivation_unavailable":
        raise self.retry(exc=RuntimeError("post-policy derivation unavailable"),
                         countdown=30 * (2 ** self.request.retries), max_retries=3)
    return outcome


async def _derive(delivery: PostPolicyDelivery) -> dict:
    """Own SQL resources while the PROJECTS port owns authority and policy writes."""
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    try:
        return await project_post_policy_delivery_port(
            async_sessionmaker(engine, expire_on_commit=False),
            authority=post_policy_service_authority, catalogue=current_post_submit_catalogue(),
        ).run(delivery)
    except Exception:
        logger.warning("post-policy derivation unavailable")
        return {"status": "derivation_unavailable"}
    finally:
        await engine.dispose()


@celery_app.task(name="workstream.project_setup.scan_post_policy_approvals", bind=True)
def scan_post_policy_approvals(self, after=None):
    """Continue a stable keyset page even when earlier candidates cannot derive."""
    try:
        cursor = UUID(after) if after is not None else None
    except (TypeError, ValueError):
        return {"status": "scan_rejected"}
    try:
        result = run_async_task(lambda: _scan(cursor))
        if result["next_after"] is not None:
            scan_post_policy_approvals.apply_async(args=(result["next_after"],))
        return result
    except Exception as exc:
        logger.warning("post-policy recovery scan unavailable")
        raise self.retry(exc=RuntimeError("post-policy scan unavailable"),
                         countdown=30 * (2 ** self.request.retries), max_retries=3) from exc


async def _scan(after: UUID | None) -> dict:
    """Release metadata reads before broker calls; failed publication stays pending."""
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    try:
        candidates = await pending_post_policy_approvals(
            async_sessionmaker(engine, expire_on_commit=False),
            after=after, limit=POST_POLICY_SCAN_PAGE_SIZE,
        )
        published = 0
        for approval_id in candidates:
            published += bool(await dispatch_post_policy_derivation_after_commit(approval_id))
        return {"selected": len(candidates), "published": published,
                "next_after": str(candidates[-1])
                if len(candidates) == POST_POLICY_SCAN_PAGE_SIZE else None}
    finally:
        await engine.dispose()
