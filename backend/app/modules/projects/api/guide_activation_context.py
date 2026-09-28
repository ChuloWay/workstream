"""Exact activation selectors disclosed by the authorized draft-policy read."""

from typing import Annotated, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.projects.api.guide_proposals import Digest


class GuidePolicySelection(BaseModel):
    """One selected review/revision version, never a latest-row lookup."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    policy_id: UUID
    generation: Annotated[int, Field(strict=True, gt=0)]
    policy_hash: Digest


class GuidePublishedContributionSelection(BaseModel):
    """Published CON identities only; no draft or Finance policy contents."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID


class GuideContributionDiscoveryPort(Protocol):
    """Read bounded CON selectors while the caller holds the project lock."""

    async def published_selection(self, project_id: UUID) -> GuidePublishedContributionSelection | None: ...


class GuideActivationContext(BaseModel):
    """Displayed inputs are selections, not a promise that activation is ready."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    guide_mutation_generation: Annotated[int, Field(strict=True, gt=0)]
    review: GuidePolicySelection | None
    revision: GuidePolicySelection | None
    contribution: GuidePublishedContributionSelection | None
    expected_previous_active_guide_id: UUID | None
    expected_previous_active_guide_generation: Annotated[int, Field(strict=True, gt=0)] | None
    post_approval_operation_id: UUID | None
    post_approval_output_digest: Digest | None

    @model_validator(mode="after")
    def complete_pairs(self):
        if (self.expected_previous_active_guide_id is None) != (self.expected_previous_active_guide_generation is None):
            raise ValueError("previous active guide selection must be complete or absent")
        if (self.post_approval_operation_id is None) != (self.post_approval_output_digest is None):
            raise ValueError("post approval selection must be complete or absent")
        return self
