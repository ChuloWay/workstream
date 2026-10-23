"""Require bounded Redis-prefork delivery for guide inference."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from celery.concurrency import get_implementation
from celery.concurrency.prefork import TaskPool
from celery.exceptions import WorkerShutdown
from celery.signals import worker_init

from app.core.config import get_settings

PROJECT_GUIDE_HARD_LIMIT_SECONDS = 7_260
PROJECT_GUIDE_DRAIN_SECONDS = 7_320
CELERY_VISIBILITY_TIMEOUT_SECONDS = 7_380
PROJECT_GUIDE_QUEUE = "celery"
_validated_parent: int | None = None


def _uses_inference() -> bool:
    """Report whether the selected runtime requires an inference worker."""
    return get_settings().project_agent_runtime != "manager_authored"


def _redis_url(value: object) -> bool:
    """Accept only Redis transports that implement the required visibility controls."""
    return isinstance(value, str) and urlsplit(value).scheme in {"redis", "rediss"}


def _valid_delivery_settings(app: object) -> bool:
    """Check the exact no-prefetch and visibility settings for guide delivery."""
    conf = app.conf
    return (
        _redis_url(conf.broker_url)
        and conf.worker_disable_prefetch is True
        and conf.visibility_timeout == CELERY_VISIBILITY_TIMEOUT_SECONDS
        and conf.broker_transport_options == {
            "visibility_timeout": CELERY_VISIBILITY_TIMEOUT_SECONDS
        }
        and conf.result_backend_transport_options == {
            "visibility_timeout": CELERY_VISIBILITY_TIMEOUT_SECONDS
        }
    )


@worker_init.connect
def validate_project_setup_worker(sender, **_kwargs: object) -> None:
    """Validate inference workers before they can reserve guide work."""
    global _validated_parent
    _validated_parent = None
    if not _uses_inference():
        return
    if PROJECT_GUIDE_QUEUE not in sender.app.amqp.queues.consume_from:
        return
    pool = sender.pool_cls
    if isinstance(pool, str):
        pool = get_implementation(pool)
    if (
        pool is not TaskPool
        or sender.app.conf.task_always_eager
        or not _valid_delivery_settings(sender.app)
    ):
        raise WorkerShutdown(
            "project guide inference requires bounded Redis prefork delivery"
        )
    _validated_parent = os.getpid()


def require_project_setup_worker(task: object) -> None:
    """Reject inference outside the startup-validated prefork child."""
    if not _uses_inference():
        return
    request = task.request
    if (
        _validated_parent is None
        or os.getppid() != _validated_parent
        or task.app.conf.task_always_eager
        or request.is_eager
        or request.called_directly
        or not _valid_delivery_settings(task.app)
    ):
        raise RuntimeError(
            "project guide inference requires a validated Redis prefork worker"
        )
    message_limit = (request.timelimit or (None, None))[0]
    if (
        type(task.time_limit) is not int
        or task.time_limit != PROJECT_GUIDE_HARD_LIMIT_SECONDS
        or message_limit is not None
        and (
            type(message_limit) is not int
            or message_limit != PROJECT_GUIDE_HARD_LIMIT_SECONDS
        )
    ):
        raise RuntimeError("project guide inference requires a bounded hard time limit")
