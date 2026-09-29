"""CHECKERS-owned output reservation facts; production reservations are unavailable."""

from typing import Annotated, Literal, Protocol, Self

from pydantic import Field, StrictInt, model_validator

from app.modules.checkers.api.post_submit import PostSubmissionEvaluationRequest
from app.modules.checkers.api.post_submit_catalogue import (
    Identifier,
    PostSubmitValue,
    ResourceId,
    VersionNumber,
)


class CheckerOutputUnavailable(RuntimeError):
    """Conceal missing, stale or unauthorized checker output custody."""


class CheckerOutputSelector(PostSubmitValue):
    """Select exact immutable evaluation and the caller's claimed execution lease."""

    evaluation: PostSubmissionEvaluationRequest
    checker_run_id: ResourceId
    worker_lease_id: ResourceId
    worker_lease_generation: VersionNumber
    slot_key: Identifier


class CheckerOutputSlot(PostSubmitValue):
    """One globally unique run slot issued by CHECKERS, not by a contributor."""

    key: Identifier
    media_type: Literal["application/json", "application/octet-stream", "text/plain"]
    maximum_bytes: Annotated[StrictInt, Field(ge=1, le=536_870_912)]


class CheckerOutputReservation(PostSubmitValue):
    """Detached owner facts, never a substitute for fresh action authority."""

    evaluation: PostSubmissionEvaluationRequest
    checker_run_id: ResourceId
    worker_lease_id: ResourceId
    worker_lease_generation: VersionNumber
    slots: tuple[CheckerOutputSlot, ...] = Field(max_length=64)

    @model_validator(mode="after")
    def unique_slots(self) -> Self:
        """Keep generic ART binding's run/role scope unambiguous."""
        if len({slot.key for slot in self.slots}) != len(self.slots):
            raise ValueError("checker output slots repeat")
        return self

    def select(self, selector: CheckerOutputSelector) -> CheckerOutputSlot:
        """Match the caller's claimed lease as well as immutable evaluation facts."""
        current = CheckerOutputReservation.model_validate(self)
        selector = CheckerOutputSelector.model_validate(selector)
        if (
            current.evaluation,
            current.checker_run_id,
            current.worker_lease_id,
            current.worker_lease_generation,
        ) != (
            selector.evaluation,
            selector.checker_run_id,
            selector.worker_lease_id,
            selector.worker_lease_generation,
        ):
            raise CheckerOutputUnavailable("checker_output_reservation_unavailable")
        for slot in current.slots:
            if slot.key == selector.slot_key:
                return slot
        raise CheckerOutputUnavailable("checker_output_slot_unavailable")


class CheckerOutputReservationPort(Protocol):
    """Resolve current owner custody before ART locks; CHECKERS owns lease fencing."""

    async def resolve(self, selector: CheckerOutputSelector) -> CheckerOutputReservation:
        """Return exact current facts under the caller's CHECKERS transaction locks."""


class UnavailableCheckerOutputReservation:
    """ARCH-04C must install the real reservation producer before activation."""

    async def resolve(self, selector: CheckerOutputSelector) -> CheckerOutputReservation:
        """Deny without reading protected facts or fabricating a reservation."""
        del selector
        raise CheckerOutputUnavailable("checker_output_reservation_unavailable")
