"""Exact complete-guide activation values; live authority is supplied separately."""

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Annotated, Literal, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.projects.api.guide_proposals import Digest
from app.modules.projects.api.post_policy import PostPolicyTarget


class ActivationValue(BaseModel):
    """Closed immutable activation evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class GuidePolicySelection(ActivationValue):
    """The selected review or revision version, never a latest-row lookup."""

    policy_id: UUID
    generation: Annotated[int, Field(strict=True, gt=0)]
    policy_hash: Digest


class GuideActivationCommand(ActivationValue):
    """Bind exactly the separately approved generation displayed to the manager."""

    target: PostPolicyTarget
    post_approval_operation_id: UUID
    post_approval_output_digest: Digest
    guide_mutation_generation: Annotated[int, Field(strict=True, gt=0)]
    review: GuidePolicySelection
    revision: GuidePolicySelection
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID
    expected_previous_active_guide_id: UUID | None
    expected_previous_active_guide_generation: Annotated[int, Field(strict=True, gt=0)] | None
    idempotency_key: UUID

    @model_validator(mode="after")
    def exact_predecessor(self):
        if (
            self.expected_previous_active_guide_id is None
            and self.expected_previous_active_guide_generation is not None
        ):
            raise ValueError("previous active guide identity must be complete or absent")
        if self.expected_previous_active_guide_id == self.target.proposal.guide_id:
            raise ValueError("activation cannot supersede its own guide")
        return self

    @property
    def digest(self) -> str:
        return canonical_json_hash(self.model_dump(mode="json"))


class GuideContributionPolicyFacts(ActivationValue):
    """PROJECTS-local facts returned by the injected CON public-port bridge."""

    project_id: UUID
    contribution_policy_id: UUID
    contribution_policy_version_id: UUID
    purpose: Literal["guide_activation"]
    version_number: Annotated[int, Field(strict=True, gt=0)]
    rules_and_definitions_digest: Digest
    adapter_binding_ids: tuple[UUID, ...]


class GuideContributionPolicyPort(Protocol):
    """Validate a new exact binding while retaining the caller transaction locks."""

    async def validate_for_activation(
        self,
        project_id: UUID,
        policy_id: UUID,
        version_id: UUID,
    ) -> GuideContributionPolicyFacts: ...


class GuideActivationReceipt(ActivationValue):
    """Immutable successful binding; later supersession never rewrites it."""

    operation_id: UUID
    command: GuideActivationCommand
    contribution: GuideContributionPolicyFacts
    activation_generation: Annotated[int, Field(strict=True, gt=0)]
    effective_at: datetime
    prior_project_status: Literal["draft", "active"]

    @model_validator(mode="after")
    def exact_binding(self):
        if (
            self.contribution.project_id != self.command.target.proposal.project_id
            or self.contribution.contribution_policy_id != self.command.contribution_policy_id
            or self.contribution.contribution_policy_version_id
            != self.command.contribution_policy_version_id
            or self.activation_generation != self.command.guide_mutation_generation + 1
            or self.effective_at.tzinfo is None
        ):
            raise ValueError("activation receipt binding mismatch")
        return self


class GuideActivationLocator(ActivationValue):
    """Authority identity selected before product locks."""

    project_id: UUID
    guide_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    operation_id: UUID
    request_id: UUID
    action_id: Literal["project.guide.activate"] = "project.guide.activate"


class GuideActivationFacts(ActivationValue):
    """Exact locked input/output commitments consumed by authority."""

    locator: GuideActivationLocator
    receipt: GuideActivationReceipt

    def resource_json(self) -> dict:
        value = self.model_dump(mode="json")
        value["locator"].pop("request_id")
        return value

    @property
    def digest(self) -> str:
        return canonical_json_hash(self.resource_json())


class GuideActivationAuthorityReceipt(ActivationValue):
    """Consumed manager authority over exactly one activation fact set."""

    actor_profile_id: UUID
    identity_link_id: UUID
    admin_role_grant_id: UUID
    authorization_decision_event_id: UUID
    action_id: Literal["project.guide.activate"]
    permission_id: Literal["project.guide.manage"]
    scope_project_id: UUID
    resource_context_digest: Digest


class PreparedGuideActivation(ABC):
    """Nominal, process-local participant bound to the caller root transaction."""

    __slots__ = ()

    def __reduce_ex__(self, _protocol):
        raise TypeError("prepared guide activation is process-local")

    @abstractmethod
    async def consume_new(self, facts: GuideActivationFacts) -> GuideActivationAuthorityReceipt: ...

    @abstractmethod
    async def validate_replay(
        self, facts: GuideActivationFacts, decision_event_id: UUID
    ) -> None: ...


class GuideActivationAuthorizationPort(Protocol):
    """Acquire full AUTH scope before owner locks; close the handle on every exit."""

    def lock_activation_scope(
        self,
        locator: GuideActivationLocator,
    ) -> AbstractAsyncContextManager[PreparedGuideActivation]: ...


_Actor = TypeVar("_Actor", contravariant=True)


class GuideActivationPort(Protocol[_Actor]):
    """One caller-owned atomic operation, with no public activation authority yet."""

    async def activate(
        self,
        command: GuideActivationCommand,
        *,
        actor: _Actor,
        request_id: UUID,
    ) -> GuideActivationReceipt: ...
