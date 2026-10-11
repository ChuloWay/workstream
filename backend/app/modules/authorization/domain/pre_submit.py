"""Exact fixed-service resources for selected pre-submit execution phases."""

from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.modules.authorization.catalogue import ActionId
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitExecuteFacts,
    SelectedPreSubmitFinalizeFacts,
    SelectedPreSubmitReservationFacts,
)


EXECUTE = ActionId.CHECKER_PRE_SUBMIT_EXECUTE
FINALIZE = ActionId.CHECKER_PRE_SUBMIT_FINALIZE
PRE_SUBMIT_ACTIONS = frozenset({EXECUTE, FINALIZE})


class PreSubmitResourceContext(BaseModel):
    """One selected run phase under its exact project and durable request."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    resource_type: Literal["selected_pre_submit_run"] = "selected_pre_submit_run"
    resource_id: UUID
    scope_project_id: UUID
    action_id: ActionId
    facts: SelectedPreSubmitExecuteFacts | SelectedPreSubmitFinalizeFacts

    @model_validator(mode="after")
    def validate_identity(self):
        expected = (
            SelectedPreSubmitExecuteFacts
            if self.action_id is EXECUTE
            else SelectedPreSubmitFinalizeFacts
            if self.action_id is FINALIZE
            else None
        )
        if expected is None or type(self.facts) is not expected:
            raise ValueError("invalid selected PRE authority phase")
        reservation = self.facts.lease.reservation
        if (
            self.resource_id != reservation.attempt_id
            or self.scope_project_id != reservation.project_id
        ):
            raise ValueError("invalid selected PRE authority resource")
        return self


def pre_submit_resource(
    action: ActionId,
    facts: SelectedPreSubmitExecuteFacts | SelectedPreSubmitFinalizeFacts,
) -> PreSubmitResourceContext:
    """Build a typed exact-run resource without provider or workspace facts."""
    reservation = facts.lease.reservation
    return PreSubmitResourceContext(
        action_id=action,
        resource_id=reservation.attempt_id,
        scope_project_id=reservation.project_id,
        facts=facts,
    )


def pre_submit_prepare_values(
    reservation: SelectedPreSubmitReservationFacts,
) -> dict[str, str]:
    """Bind fixed-service preparation to the selected request before owner locks."""
    return {
        "project_id": str(reservation.project_id),
        "run_id": str(reservation.attempt_id),
        "request_digest": reservation.request_digest,
    }


def parse_pre_submit_prepare(action, values, invalid_error):
    """Reject extra or malformed fixed-service selectors."""
    if action not in PRE_SUBMIT_ACTIONS:
        return None
    try:
        if set(values) != {"project_id", "run_id", "request_digest"}:
            raise ValueError("invalid keys")
        for key in ("project_id", "run_id"):
            if type(values[key]) is not str or str(UUID(values[key])) != values[key]:
                raise ValueError("invalid identity")
        if (
            type(values["request_digest"]) is not str
            or re.fullmatch(r"sha256:[0-9a-f]{64}", values["request_digest"])
            is None
        ):
            raise ValueError("invalid digest")
    except (KeyError, TypeError, ValueError) as error:
        raise invalid_error("invalid prepared selected PRE authority") from error
    return dict(values)


def pre_submit_prepare_matches(action, prepared, resource) -> bool:
    """Match final phase facts to the exact prepared selected request."""
    if (
        action not in PRE_SUBMIT_ACTIONS
        or type(resource) is not PreSubmitResourceContext
        or resource.action_id is not action
    ):
        return False
    resource.validate_identity()
    return prepared == pre_submit_prepare_values(resource.facts.lease.reservation)


__all__ = (
    "EXECUTE",
    "FINALIZE",
    "PRE_SUBMIT_ACTIONS",
    "PreSubmitResourceContext",
    "parse_pre_submit_prepare",
    "pre_submit_prepare_matches",
    "pre_submit_prepare_values",
    "pre_submit_resource",
)
