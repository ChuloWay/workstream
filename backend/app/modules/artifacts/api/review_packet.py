"""Exact reviewer packet metadata; these values grant no artifact access."""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.modules.projects.api.guide_documents import GuideDocumentMediaType


class ReviewPacketMembershipUnavailable(RuntimeError):
    """Conceal absent, foreign or incomplete membership without private details."""

    def __init__(self) -> None:
        super().__init__("review_packet_membership_unavailable")


class ReviewPacketMembershipRequest(BaseModel):
    """Locked scope; result_id names CheckerRun.result_id, not CheckerResult.id."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: UUID
    task_id: UUID
    submission_id: UUID
    submission_version: StrictInt = Field(ge=1)
    checker_run_id: UUID
    result_id: UUID
    guide_id: UUID
    guide_version: str = Field(min_length=1, max_length=50)
    source_snapshot_id: UUID
    project_setup_run_id: UUID
    setup_generation: StrictInt = Field(ge=1)

    @field_validator("guide_version")
    @classmethod
    def nonblank_guide_version(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("guide version must not be blank")
        return value


class ReviewSubmissionMember(BaseModel):
    """Required original ZIP; binding_id identifies ART's artifact_bindings row."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    binding_id: UUID
    logical_role: Literal["submission_bundle_original"]
    media_type: Literal["application/zip"]


class ReviewGuideMember(BaseModel):
    """Required original document from ART's guide_source_artifact_bindings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    guide_binding_id: UUID
    source_item_id: UUID
    item_order: StrictInt = Field(ge=0)
    logical_role: Literal["guide_source_original"]
    media_type: GuideDocumentMediaType


class ReviewPacketMembership(BaseModel):
    """Complete metadata shape; stored ownership/completeness need owner resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request: ReviewPacketMembershipRequest
    submission: ReviewSubmissionMember
    guide_documents: tuple[ReviewGuideMember, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def canonical_documents(self) -> ReviewPacketMembership:
        for attribute in ("guide_binding_id", "source_item_id", "item_order"):
            values = [getattr(document, attribute) for document in self.guide_documents]
            if len(values) != len(set(values)):
                raise ValueError("review packet guide membership is duplicated")
        orders = tuple(document.item_order for document in self.guide_documents)
        if orders != tuple(sorted(orders)):
            raise ValueError("review packet guide documents are not in source order")
        return self

    def require_request(self, expected: ReviewPacketMembershipRequest) -> None:
        """Check echoed scope before use; this does not prove stored ownership."""
        if self.request != expected:
            raise ReviewPacketMembershipUnavailable()


class ReviewPacketMembershipPort(Protocol):
    """Future caller-transaction read; no implementation or authority is provided.

    Resolve the entire declared set from canonical owner facts for this exact
    activated setup run/generation. Never select a latest policy or accept a
    caller's binding list. Conceal missing, foreign or incomplete sets with
    ReviewPacketMembershipUnavailable. Consumers require_request before use;
    byte reads separately require exact lease/packet authorization.
    """

    async def resolve_membership(
        self, request: ReviewPacketMembershipRequest,
    ) -> ReviewPacketMembership: ...
