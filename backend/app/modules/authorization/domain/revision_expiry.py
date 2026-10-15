"""Exact fixed-service authority for one due TASK revision expiration."""

import json
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.modules.authorization.catalogue import ActionId
from app.modules.tasks.api.revision_expiry import TaskRevisionExpiryAuthorityFacts


class RevisionExpiryResourceContext(BaseModel):
    """Closed AUTH resource binding the target and locked invocation facts."""
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal["task_authority"] = "task_authority"
    resource_id: UUID
    scope_project_id: UUID
    facts: TaskRevisionExpiryAuthorityFacts

    @model_validator(mode="after")
    def exact_target(self):
        """Reject a resource selector that differs from the scheduled TASK target."""
        if (self.resource_id != self.facts.target.task_id
                or self.scope_project_id != self.facts.target.project_id):
            raise ValueError("revision expiry authority target differs")
        return self


def revision_expiry_resource(facts):
    """Normalize exact TASK facts into the closed expiry authority resource."""
    facts = TaskRevisionExpiryAuthorityFacts.model_validate_json(facts.model_dump_json())
    return RevisionExpiryResourceContext(
        resource_id=facts.target.task_id, scope_project_id=facts.target.project_id, facts=facts,
    )


def parse_revision_expiry_binding(action, request, invalid_error):
    """Parse only expiry actions and conceal malformed resource input."""
    if action is not ActionId.TASK_REVISION_EXPIRE:
        return None
    try:
        return RevisionExpiryResourceContext.model_validate_json(json.dumps(dict(request)))
    except (TypeError, ValueError) as exc:
        raise invalid_error("invalid revision expiry authority") from exc
