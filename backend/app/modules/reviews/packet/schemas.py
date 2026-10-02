"""Detached packet facts, without authority or storage capabilities."""

from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt

from app.modules.artifacts.api.review_packet import ReviewPacketMembership


class ReviewPacketConflict(RuntimeError):
    """The same lease already retains different packet membership."""

    def __init__(self) -> None:
        super().__init__("review_packet_conflict")


class ReviewPacketStored(BaseModel):
    """Immutable stored identity plus canonical ART metadata shape."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    packet_id: UUID
    review_lease_id: UUID
    review_queue_entry_id: UUID
    packet_manifest_generation: StrictInt = Field(ge=1)
    packet_manifest_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    created_at: AwareDatetime
    membership: ReviewPacketMembership
