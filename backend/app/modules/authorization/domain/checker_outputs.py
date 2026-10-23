"""Exact prepared resources for private checker-model output custody."""

from __future__ import annotations

import json
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.authorization.catalogue import ActionId
from app.modules.checkers.api.output_custody import (
    CheckerOutputReservation,
    CheckerOutputSelector,
)


WRITE = ActionId.ARTIFACT_CHECKER_OUTPUT_WRITE
BIND = ActionId.ARTIFACT_CHECKER_OUTPUT_BINDING_CREATE
CHECKER_OUTPUT_ACTIONS = frozenset({WRITE, BIND})

_STRICT_FROZEN = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")


class CheckerOutputCommitmentFacts(BaseModel):
    """Server-computed content commitment without source bytes or scratch identity."""

    model_config = _STRICT_FROZEN
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(strict=True, ge=0, le=1_048_576)
    media_type: Literal["application/json"]


class CheckerOutputStoredAuthorityFacts(BaseModel):
    """Verified ART ancestry selected under the exact model-call reservation."""

    model_config = _STRICT_FROZEN
    put_attempt_id: UUID
    checker_request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    byte_count: int = Field(strict=True, ge=0, le=1_048_576)
    media_type: Literal["application/json"]
    status: Literal[
        "prepared",
        "put_in_flight",
        "acknowledgement_unknown",
        "object_confirmed",
        "absent_replay_required",
        "integrity_mismatch",
        "provider_unavailable",
        "conflict",
        "verified",
    ]
    content_id: UUID | None
    replica_id: UUID | None
    verification_receipt_id: UUID | None

    @model_validator(mode="after")
    def exact_verification(self) -> Self:
        present = (
            self.content_id is not None,
            self.replica_id is not None,
            self.verification_receipt_id is not None,
        )
        if self.status == "verified" and not all(present):
            raise ValueError("verified checker output ancestry is incomplete")
        if self.status != "verified" and any(present):
            raise ValueError("unverified checker output has verified ancestry")
        return self


class CheckerOutputResourceContext(BaseModel):
    """One exact selector prepared before owner locks and closed by stored facts."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["checker_model_output"] = "checker_model_output"
    resource_id: UUID
    scope_project_id: UUID
    action_id: ActionId
    selector: CheckerOutputSelector
    selector_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    reservation: CheckerOutputReservation | None = None
    commitment: CheckerOutputCommitmentFacts | None = None
    stored: CheckerOutputStoredAuthorityFacts | None = None

    @model_validator(mode="after")
    def exact_selector(self) -> Self:
        if self.action_id not in CHECKER_OUTPUT_ACTIONS:
            raise ValueError("invalid checker output action")
        if (
            self.resource_id != self.selector.model_call_attempt_id
            or self.scope_project_id != self.selector.paid_slot.project_id
            or self.selector_digest != checker_output_selector_digest(self.selector)
        ):
            raise ValueError("invalid checker output selector resource")
        if self.reservation is not None:
            slot = self.reservation.select(self.selector)
            if self.commitment is not None and (
                self.commitment.byte_count > slot.maximum_bytes
                or self.commitment.media_type != slot.media_type
            ):
                raise ValueError("checker output commitment exceeds its reservation")
            if self.stored is not None and (
                self.stored.byte_count > slot.maximum_bytes
                or self.stored.media_type != slot.media_type
                or self.stored.checker_request_digest
                != canonical_json_hash(_checker_output_request_digest_facts(self.reservation, slot))
            ):
                raise ValueError("stored checker output differs from its reservation")
        if self.commitment is not None and self.action_id is not WRITE:
            raise ValueError("checker output commitment requires write authority")
        if self.stored is not None and self.stored.sha256 != self.selector.content_sha256:
            raise ValueError("stored checker output differs from selector")
        if (
            self.reservation is not None
            and self.action_id is BIND
            and (self.stored is None or self.stored.status != "verified")
        ):
            raise ValueError("checker output binding requires verified ancestry")
        if self.commitment is not None and self.commitment.sha256 != self.selector.content_sha256:
            raise ValueError("checker output commitment differs from selector")
        if self.commitment is not None and self.stored is not None:
            raise ValueError("checker output authority facts are ambiguous")
        return self


def checker_output_selector_digest(selector: CheckerOutputSelector) -> str:
    """Hash the entire typed selector prepared before protected owner access."""
    checked = CheckerOutputSelector.model_validate(selector)
    return canonical_json_hash(checked.model_dump(mode="json"))


def checker_output_prepare_resource(
    action: ActionId, selector: CheckerOutputSelector
) -> CheckerOutputResourceContext:
    """Build the preliminary resource bound only to the caller's exact selector."""
    checked = CheckerOutputSelector.model_validate(selector)
    return CheckerOutputResourceContext(
        resource_id=checked.model_call_attempt_id,
        scope_project_id=checked.paid_slot.project_id,
        action_id=action,
        selector=checked,
        selector_digest=checker_output_selector_digest(checked),
    )


def checker_output_admission_resource(
    selector: CheckerOutputSelector,
    facts: object,
) -> CheckerOutputResourceContext:
    """Bind prepared write authority to server-computed content facts."""
    prepared = checker_output_prepare_resource(WRITE, selector)
    return CheckerOutputResourceContext(
        resource_id=prepared.resource_id,
        scope_project_id=prepared.scope_project_id,
        action_id=prepared.action_id,
        selector=prepared.selector,
        selector_digest=prepared.selector_digest,
        reservation=facts.reservation,
        commitment=CheckerOutputCommitmentFacts(
            sha256=facts.sha256,
            byte_count=facts.byte_count,
            media_type=facts.media_type,
        ),
    )


def checker_output_stored_resource(
    action: ActionId,
    selector: CheckerOutputSelector,
    reservation: CheckerOutputReservation,
    facts: object,
) -> CheckerOutputResourceContext:
    """Bind prepared authority to storage facts selected by ART itself."""
    prepared = checker_output_prepare_resource(action, selector)
    return CheckerOutputResourceContext(
        resource_id=prepared.resource_id,
        scope_project_id=prepared.scope_project_id,
        action_id=prepared.action_id,
        selector=prepared.selector,
        selector_digest=prepared.selector_digest,
        reservation=reservation,
        stored=CheckerOutputStoredAuthorityFacts(
            put_attempt_id=facts.put_attempt_id,
            checker_request_digest=facts.checker_request_digest,
            sha256=facts.sha256,
            byte_count=facts.byte_count,
            media_type=facts.media_type,
            status=facts.status,
            content_id=facts.content_id,
            replica_id=facts.replica_id,
            verification_receipt_id=facts.verification_receipt_id,
        ),
    )


def _checker_output_request_digest_facts(reservation, slot) -> dict[str, object]:
    """Mirror ART's stable owner facts without importing the ART runtime."""
    selector = reservation.selector
    return {
        "model_call_slot_id": str(selector.model_call_slot_id),
        "model_call_attempt_id": str(selector.model_call_attempt_id),
        "paid_slot": selector.paid_slot.model_dump(mode="json"),
        "task_id": str(selector.task_id),
        "content_sha256": selector.content_sha256,
        "slot_key": slot.key,
        "media_type": slot.media_type,
        "maximum_bytes": slot.maximum_bytes,
    }


def parse_checker_output_prepare(
    action: ActionId, value: object, invalid_error: type[Exception]
) -> CheckerOutputResourceContext | None:
    """Parse only preliminary selector resources at PREP issuance."""
    if action not in CHECKER_OUTPUT_ACTIONS:
        return None
    try:
        resource = CheckerOutputResourceContext.model_validate_json(json.dumps(value))
        if (
            resource.action_id is not action
            or resource.reservation is not None
            or resource.commitment is not None
            or resource.stored is not None
        ):
            raise ValueError("checker output prepare resource is not preliminary")
        return resource
    except (TypeError, ValueError) as error:
        raise invalid_error("invalid prepared checker output authority") from error


def checker_output_prepare_matches(
    prepared: CheckerOutputResourceContext | None,
    resource: object,
) -> bool:
    """Require final facts to retain the exact selector committed at preparation."""
    return (
        prepared is not None
        and type(resource) is CheckerOutputResourceContext
        and resource.action_id is prepared.action_id
        and resource.resource_id == prepared.resource_id
        and resource.scope_project_id == prepared.scope_project_id
        and resource.selector == prepared.selector
        and resource.selector_digest == prepared.selector_digest
        and resource.reservation is not None
        and ((resource.commitment is not None) ^ (resource.stored is not None))
    )


__all__ = (
    "BIND",
    "CHECKER_OUTPUT_ACTIONS",
    "CheckerOutputResourceContext",
    "WRITE",
    "checker_output_admission_resource",
    "checker_output_prepare_matches",
    "checker_output_prepare_resource",
    "checker_output_selector_digest",
    "checker_output_stored_resource",
    "parse_checker_output_prepare",
)
