"""Closed retained Review inputs and stable preallocation request identity."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.hashing import canonical_json_hash

ReviewDecision = Literal["accept", "needs_revision", "reject"]
FindingKind = Literal["blocking", "advisory"]
ResolutionResult = Literal["resolved", "unresolved", "not_applicable"]
Narrative = Annotated[str, StringConstraints(min_length=1, max_length=4000, pattern=r"\S")]
Digest = Annotated[str, StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$")]


class ReviewFindingInput(BaseModel):
    """One ordered finding; its generated ID is not request identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    id: UUID
    finding_kind: FindingKind
    area: Annotated[str, StringConstraints(min_length=1, max_length=200, pattern=r"\S")]
    issue: Narrative
    required_fix: Narrative


class FindingResolutionInput(BaseModel):
    """A later judgment about an existing finding, without response authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    id: UUID
    finding_id: UUID
    result: ResolutionResult
    rationale: Narrative


class ReviewSourceInput(BaseModel):
    """Complete metadata aggregate; construction grants no decision authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    id: UUID
    project_id: UUID
    task_id: UUID
    task_assignment_id: UUID
    submission_id: UUID
    submission_version: int = Field(gt=0)
    review_queue_entry_id: UUID
    review_lease_id: UUID
    packet_manifest_id: UUID
    packet_manifest_digest: Digest
    artifact_hash: Digest
    reviewer_id: UUID
    reviewer_contribution_policy_version_id: UUID
    locked_guide_version: str = Field(min_length=1, max_length=50, pattern=r"\S")
    locked_review_policy_id: UUID
    locked_review_policy_generation: int = Field(gt=0)
    locked_review_policy_hash: Digest
    predecessor_review_id: UUID | None
    decision: ReviewDecision
    summary: Narrative
    findings: tuple[ReviewFindingInput, ...] = Field(max_length=100)
    resolutions: tuple[FindingResolutionInput, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def distinct_members(self):
        """Reject ambiguous member identity before storage validates ancestry."""
        for values in (
            [f.id for f in self.findings],
            [r.id for r in self.resolutions],
            [r.finding_id for r in self.resolutions],
        ):
            if len(values) != len(set(values)):
                raise ValueError("duplicate Review member")
        return self

    def semantic_payload(self, *, request: bool = False) -> dict:
        """Canonical normalized content shared with the database validator."""
        values = self.model_dump(mode="json")
        values["finding_count"] = len(self.findings)
        values["blocking_finding_count"] = sum(f.finding_kind == "blocking" for f in self.findings)
        values["resolution_count"] = len(self.resolutions)
        if request:
            values.pop("id")
            for members in (values["findings"], values["resolutions"]):
                for member in members:
                    member.pop("id")
            values["action"] = "review.decision"
            values["domain"] = "workstream.review_decision_request.v0.1"
        else:
            values["domain"] = "workstream.review_source.v0.1"
        return values

    @property
    def aggregate_digest(self) -> str:
        """Seal all retained identities and content, including nested members."""
        return canonical_json_hash(self.semantic_payload())

    @property
    def request_digest(self) -> str:
        """Match exact first deliveries independently of generated record IDs."""
        return canonical_json_hash(self.semantic_payload(request=True))
