"""Exact post-policy projection, review and decision values; no execution authority."""

from typing import Generic, Literal, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.projects.api.guide_proposal_package import GuideProposalReviewPackage
from app.modules.projects.api.guide_proposals import (
    Digest, GuideProposalApprovalReceipt, GuideProposalCorrection,
    GuideProposalCorrectionReceipt, GuideProposalSelection, GuideProposalTarget,
)


class PostPolicyValue(BaseModel):
    """Closed immutable input with nested instance revalidation."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class PostPolicyDerive(PostPolicyValue):
    """Select a saved result and its exact separately approved upstream chain."""

    selection: GuideProposalSelection
    upstream_approval_operation_id: UUID
    upstream_approval_output_digest: Digest


class PostPolicyTarget(PostPolicyValue):
    """Source, upstream and sole canonical policy hash shown before a decision."""

    proposal: GuideProposalTarget
    upstream: GuideProposalApprovalReceipt
    upstream_output_digest: Digest
    policy_id: UUID
    projection_operation_id: UUID
    policy_hash: Digest
    predecessor_policy_id: UUID | None = None

    @model_validator(mode="after")
    def require_upstream(self):
        if (
            self.proposal.artifact_policy_id is None
            or self.upstream.target_digest != self.proposal.digest
            or self.upstream.artifact_policy_id != self.proposal.artifact_policy_id
            or self.upstream_output_digest != canonical_json_hash(self.upstream.model_dump(mode="json"))
        ):
            raise ValueError("post-policy upstream approval mismatch")
        return self

    @property
    def digest(self) -> str:
        return canonical_json_hash(self.model_dump(mode="json"))


class PostPolicySelection(GuideProposalSelection):
    """Read an exact retained policy, never a silently substituted current row."""

    policy_id: UUID


class PostPolicyApproval(PostPolicyValue):
    """Approve only the exact displayed policy; content editing is not approval."""

    target: PostPolicyTarget
    idempotency_key: UUID


class PostPolicyCorrection(GuideProposalCorrection):
    """Reuse canonical manager feedback validation for a unified successor."""

    target: PostPolicyTarget


class PostPolicyReceipt(PostPolicyValue):
    """Immutable operation output, including discoverable correction lineage."""

    operation_id: UUID
    kind: Literal["derive", "approve", "correction"]
    target: PostPolicyTarget
    correction: GuideProposalCorrectionReceipt | None = None

    @model_validator(mode="after")
    def require_correction(self):
        if (self.kind == "correction") != (self.correction is not None):
            raise ValueError("post-policy correction receipt must be complete or absent")
        if self.correction and self.correction.target_digest != self.target.proposal.digest:
            raise ValueError("post-policy correction predecessor mismatch")
        return self


_PolicyT = TypeVar("_PolicyT", covariant=True)


class PostPolicyReviewPackage(PostPolicyValue, Generic[_PolicyT]):
    """Complete canonical draft and safe unified findings, separately authorized."""

    target: PostPolicyTarget
    policy: _PolicyT
    proposal: GuideProposalReviewPackage
    lifecycle_status: Literal["compiled", "approved", "superseded"]
    current: bool
    approval_operation_id: UUID | None
    correction: GuideProposalCorrectionReceipt | None


_ActorT = TypeVar("_ActorT", contravariant=True)
_GuideAuthorityT = TypeVar("_GuideAuthorityT", contravariant=True)


class PostPolicyOperationsPort(Protocol[_ActorT, _GuideAuthorityT, _PolicyT]):
    """Typed hidden operations; composition supplies authority without a default adapter."""

    async def derive(self, command: PostPolicyDerive, *, actor: _ActorT, request_id: UUID) -> PostPolicyReceipt: ...

    async def approve(self, command: PostPolicyApproval, *, actor: _ActorT, request_id: UUID) -> PostPolicyReceipt: ...

    async def review_package(self, selection: PostPolicySelection, *, actor: _ActorT, request_id: UUID) -> PostPolicyReviewPackage[_PolicyT]: ...

    async def request_correction(
        self, command: PostPolicyCorrection, *, actor: _ActorT, request_id: UUID,
        guide_authorization: _GuideAuthorityT,
    ) -> PostPolicyReceipt: ...
