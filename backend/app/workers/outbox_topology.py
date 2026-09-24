"""Require a validated prefork worker for bounded OUTBOX effect delivery."""

import os

from celery.concurrency import get_implementation
from celery.concurrency.prefork import TaskPool
from celery.exceptions import WorkerShutdown
from celery.signals import worker_init

OUTBOX_HARD_LIMIT_SECONDS = 300
OUTBOX_QUEUE = "workstream.outbox"
OUTBOX_DELIVERY_TASK = "workstream.outbox.deliver_event"
_validated_parent: int | None = None


@worker_init.connect
def validate_outbox_worker(sender, **_kwargs):
    """Validate the actual selected queues and pool before the worker starts."""
    global _validated_parent
    _validated_parent = None
    if OUTBOX_QUEUE not in sender.app.amqp.queues.consume_from:
        return
    pool = sender.pool_cls
    if isinstance(pool, str):
        pool = get_implementation(pool)
    if pool is not TaskPool or sender.app.conf.task_always_eager:
        raise WorkerShutdown("OUTBOX delivery requires a non-eager prefork worker")
    _validated_parent = os.getpid()


def require_outbox_worker(task):
    """Reject direct/eager delivery and consumers not validated for this queue."""
    if (
        _validated_parent is None or os.getppid() != _validated_parent
        or task.app.conf.task_always_eager or task.request.is_eager
        or task.request.called_directly
    ):
        raise RuntimeError("OUTBOX delivery requires a validated prefork worker")
    hard_limit = (task.request.timelimit or (None, None))[0] or task.time_limit
    if type(hard_limit) not in (int, float) or not 0 < hard_limit <= OUTBOX_HARD_LIMIT_SECONDS:
        raise RuntimeError("OUTBOX delivery requires a bounded hard time limit")
