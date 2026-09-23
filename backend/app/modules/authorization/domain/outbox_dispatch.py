"""Exact OUTBOX phase resources for canonical transaction-bound AUTH."""

from uuid import UUID
import re

from pydantic import BaseModel, ConfigDict, model_validator

from app.modules.authorization.api.outbox_dispatch import (
    OUTBOX_DISPATCH_RESOURCE,
    OutboxDispatchFacts,
    outbox_dispatch_resource_digest,
)
from app.modules.authorization.catalogue import ActionId


class OutboxDispatchResourceContext(BaseModel):
    """Bind owner-verified facts without importing OUTBOX persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: str
    resource_id: UUID
    scope_project_id: UUID
    facts: OutboxDispatchFacts

    @model_validator(mode="after")
    def validate_identity(self):
        """Revalidate even forged dataclasses and independently substituted selectors."""
        outbox_dispatch_resource_digest(self.facts)
        if (
            self.resource_type != OUTBOX_DISPATCH_RESOURCE
            or self.resource_id != self.facts.event_id
            or self.scope_project_id != self.facts.project_id
        ):
            raise ValueError("invalid outbox dispatch resource")
        return self


def outbox_dispatch_resource(facts: OutboxDispatchFacts) -> OutboxDispatchResourceContext:
    """Keep the existing public digest as the only phase commitment."""
    outbox_dispatch_resource_digest(facts)
    return OutboxDispatchResourceContext(
        resource_type=OUTBOX_DISPATCH_RESOURCE,
        resource_id=facts.event_id,
        scope_project_id=facts.project_id,
        facts=facts,
    )


def prepared_outbox_digest(action_id, request_value, invalid_error):
    """Bind one exact digest without introducing another facts parser."""
    if action_id is not ActionId.OUTBOX_DISPATCH:
        return None
    value = request_value.get("outbox_dispatch_digest")
    if (
        set(request_value) != {"outbox_dispatch_digest"}
        or type(value) is not str
        or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
    ):
        raise invalid_error("invalid prepared outbox authority")
    return value
