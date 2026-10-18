"""Public TASK ports for retained post-submit delivery source facts."""

from typing import Protocol

from app.modules.outbox.api import OutboxEventEnvelope


class EvaluationDeliveryUnavailable(RuntimeError):
    """The event and retained request do not have exact TASK custody."""


class EvaluationDeliveryRequestReadPort(Protocol):
    """Read one retained request without staging or repairing owner rows."""

    async def read(
        self, envelope: OutboxEventEnvelope,
    ) -> object: ...
