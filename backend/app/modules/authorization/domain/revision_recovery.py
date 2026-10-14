"""Closed fixed-service resource for retained revision-window recovery."""

import json

from pydantic import model_validator

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.task_authority import TaskAuthorityResourceContext
from app.modules.tasks.api.revision_recovery import RECOVERY_REASON


class RevisionRecoveryResourceContext(TaskAuthorityResourceContext):
    """Bind the service to one routed source and optional exact existing root."""

    @model_validator(mode="after")
    def require_recovery_source(self):
        """Require one assigned revision source and paired optional root evidence."""
        if (
            self.task_status != "needs_revision"
            or self.assigned_to is None
            or self.assigned_to != self.assignment_contributor_id
            or self.assignment_id is None
            or self.revision_routing_manifest_id is None
            or self.reason != RECOVERY_REASON
            or self.idempotency_key != self.revision_routing_manifest_id
            or self.request_digest is None
            or self.replay_assignment_id is not None
            or self.replay_command_id is not None
            or self.revision_replay_preparation_id is not None
            or (self.revision_preparation_id is None)
            != (self.revision_preparation_sha256 is None)
        ):
            raise ValueError("retained revision recovery source differs")
        return self


def parse_revision_recovery_binding(action, request, invalid_error):
    """Parse only recovery actions into the closed retained-source resource."""
    if action is not ActionId.TASK_REVISION_RECOVER:
        return None
    try:
        return RevisionRecoveryResourceContext.model_validate_json(json.dumps(dict(request)))
    except (TypeError, ValueError) as exc:
        raise invalid_error("invalid revision recovery authority") from exc
