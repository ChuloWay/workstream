"""Exact system-Operator resource for one terminal checker retry."""

from __future__ import annotations

import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.modules.authorization.catalogue import ActionId
from app.modules.checkers.api.execution import CheckerRetryPreparation, CheckerRetrySuccessor


CHECKER_RETRY_ACTIONS = frozenset({ActionId.OPERATIONS_CHECKER_RETRY})


class CheckerRetryResourceContext(BaseModel):
    """Bind the source and the actual successor without granting project authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    resource_type: Literal["checker_run"] = "checker_run"
    resource_id: UUID
    project_id: UUID
    identity_link_id: UUID
    preparation: CheckerRetryPreparation
    successor: CheckerRetrySuccessor

    @model_validator(mode="after")
    def validate_identity(self):
        if (
            self.resource_id != self.preparation.source.source_run_id
            or self.project_id != self.preparation.source.project_id
            or self.successor.generation != self.preparation.source.source_generation + 1
        ):
            raise ValueError("invalid checker retry resource")
        return self


class CheckerRetryPrepareDenialResourceContext(BaseModel):
    """Bind a prepare-time denial to the exact source without inventing a successor."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    resource_type: Literal["checker_run"] = "checker_run"
    resource_id: UUID
    project_id: UUID
    identity_link_id: UUID
    preparation: CheckerRetryPreparation

    @model_validator(mode="after")
    def validate_identity(self):
        if (
            self.resource_id != self.preparation.source.source_run_id
            or self.project_id != self.preparation.source.project_id
        ):
            raise ValueError("invalid checker retry denial resource")
        return self


def parse_checker_retry_prepare(action_id, caller_input, scope, context, invalid_error):
    """Admit only the complete system-scoped Operator request before AUTH locking."""
    if action_id is not ActionId.OPERATIONS_CHECKER_RETRY:
        return None
    try:
        if (
            scope.kind.value != "system"
            or caller_input.idempotency_key != context.request_id
            or context.request_id != context.correlation_id
        ):
            raise ValueError
        preparation = CheckerRetryPreparation.model_validate_json(
            json.dumps(dict(caller_input.request_value))
        )
        if (
            preparation.actor_profile_id != context.actor_profile_id
            or preparation.request_key != caller_input.idempotency_key
            or not preparation.reason.strip()
        ):
            raise ValueError
        return preparation
    except (TypeError, ValueError, AttributeError):
        raise invalid_error("invalid prepared checker retry") from None


def checker_retry_resource_matches(
    preparation, resource, identity_link_id: UUID, historical_link: bool,
) -> bool:
    """A successor can differ only in fields absent from the prepared source."""
    return (
        type(resource) is CheckerRetryResourceContext
        and preparation == resource.preparation
        and (historical_link or resource.identity_link_id == identity_link_id)
    )


def checker_retry_denial_resource_matches(
    preparation: CheckerRetryPreparation | None,
    resource: object,
    identity_link_id: UUID,
) -> bool:
    """Bind a prepare-time denial to the original source and current identity."""
    return (
        type(resource) is CheckerRetryPrepareDenialResourceContext
        and preparation == resource.preparation
        and resource.identity_link_id == identity_link_id
        and resource.resource_id == resource.preparation.source.source_run_id
        and resource.project_id == resource.preparation.source.project_id
    )


def checker_retry_resource_json(resource: CheckerRetryResourceContext) -> str:
    """The exact canonical AUTH digest input retained for SQL closure."""
    resource = CheckerRetryResourceContext.model_validate(resource)
    return json.dumps(
        {"resource_context": resource.model_dump(mode="json", exclude_none=True)},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    )
