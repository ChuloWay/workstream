"""Public ART authority facts for call-stable checker output custody."""

from dataclasses import dataclass
from typing import Protocol, final
from uuid import UUID

from app.modules.checkers.api.output_custody import (
    CheckerOutputReservation,
    CheckerOutputSelector,
)


@final
@dataclass(frozen=True, slots=True)
class CheckerOutputCommitmentAuthorityFacts:
    """Server-computed commitment without source bytes or scratch identity."""

    reservation: CheckerOutputReservation
    slot_key: str
    sha256: str
    byte_count: int
    media_type: str


@final
@dataclass(frozen=True, slots=True)
class CheckerOutputStoredFacts:
    """Exact storage facts selected by ART under the prepared call selector."""

    put_attempt_id: UUID
    checker_request_digest: str
    sha256: str
    byte_count: int
    media_type: str
    status: str
    content_id: UUID | None
    replica_id: UUID | None
    verification_receipt_id: UUID | None


class CheckerOutputWriteAuthority(Protocol):
    """Fresh write authority; no prepared handle survives storage I/O."""

    async def preflight(self, selector: CheckerOutputSelector) -> None: ...

    async def prepare(self, selector: CheckerOutputSelector) -> None: ...

    async def consume(self, facts: CheckerOutputCommitmentAuthorityFacts) -> None: ...

    async def consume_existing(
        self, reservation: CheckerOutputReservation, facts: CheckerOutputStoredFacts
    ) -> None: ...

    def discard(self) -> None: ...


class CheckerOutputBindingAuthority(Protocol):
    """Fresh publication authority for independently verified call evidence."""

    async def preflight(self, selector: CheckerOutputSelector) -> None: ...

    async def prepare(self, selector: CheckerOutputSelector) -> None: ...

    async def consume(
        self, reservation: CheckerOutputReservation, facts: CheckerOutputStoredFacts
    ) -> None: ...

    def discard(self) -> None: ...


__all__ = (
    "CheckerOutputBindingAuthority",
    "CheckerOutputCommitmentAuthorityFacts",
    "CheckerOutputStoredFacts",
    "CheckerOutputWriteAuthority",
)
