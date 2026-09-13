"""Nominal post-policy PREP seam; AUTH-12G supplies live authority later."""

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict, dataclass
import json
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.hashing import canonical_json_hash

PostPolicyAction = Literal[
    "project.post_submit_checker_policy.derive",
    "project.post_submit_checker_policy.approve",
    "project.post_submit_checker_policy.correction.request",
    "project.guide_compilation.review_package.read",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class PostPolicyAuthorizationLocator:
    """Authority selectors resolved before any guide or policy lock."""

    project_id: UUID
    guide_id: UUID
    compilation_id: UUID
    actor_profile_id: UUID
    identity_link_id: UUID
    action_id: PostPolicyAction
    operation_id: UUID
    request_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class PostPolicyAuthorizationFacts:
    """Exact commitments recomposed under the existing product serialization."""

    locator: PostPolicyAuthorizationLocator
    policy_id: UUID
    finalization_id: UUID
    setup_run_id: UUID
    setup_generation: int
    upstream_approval_operation_id: UUID
    upstream_approval_output_digest: str
    policy_hash: str
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str
    result_hash: str
    post_component_hash: str
    requirement_inventory_hash: str
    catalogue_manifest_hash: str
    effective_policy_id: UUID
    effective_policy_hash: str
    pre_submit_policy_id: UUID
    pre_submit_bundle_hash: str
    projection_operation_id: UUID
    lifecycle_status: Literal["compiled", "approved", "superseded"]
    target_digest: str
    request_digest: str
    output_digest: str

    def resource_json(self) -> dict:
        values = json.loads(json.dumps(asdict(self), default=str))
        del values["locator"]["request_id"]
        return values

    @property
    def digest(self) -> str:
        return canonical_json_hash(self.resource_json())


@dataclass(frozen=True, slots=True, kw_only=True)
class PostPolicyAuthorityReceipt:
    """An exact human project grant or fixed setup-service decision."""

    actor_profile_id: UUID
    identity_link_id: UUID
    authorization_decision_event_id: UUID
    action_id: PostPolicyAction
    permission_id: str
    scope_project_id: UUID
    resource_context_digest: str
    admin_role_grant_id: UUID | None
    service_identity: str | None


class PreparedPostPolicyOperation(ABC):
    """Request-local, root-transaction-bound capability; no duck-typed approval."""

    __slots__ = ()

    def __reduce_ex__(self, _protocol):
        raise TypeError("prepared post-policy authority is process-local")

    @abstractmethod
    async def authorize_read(self, facts: PostPolicyAuthorizationFacts) -> None: ...

    @abstractmethod
    async def consume_new(self, facts: PostPolicyAuthorizationFacts) -> PostPolicyAuthorityReceipt: ...

    @abstractmethod
    async def validate_replay(self, facts: PostPolicyAuthorizationFacts, decision_event_id: UUID) -> None: ...


class PostPolicyAuthorizationPort(Protocol):
    """No default, live adapter or runtime composition is provided by POL-06A."""

    def prepare_post_policy_operation(
        self, locator: PostPolicyAuthorizationLocator,
    ) -> AbstractAsyncContextManager[PreparedPostPolicyOperation]: ...


class ProjectPostSubmitCheckerPolicyMutationResourceContext(BaseModel):
    """Exact finalized compilation and approved upstream commitments for post policy."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    resource_type: Literal["project_post_submit_checker_policy_mutation"]
    resource_id: UUID
    scope_project_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    target_kind: Literal["approve", "correction_request", "derive"]
    execution_kind: Literal["human", "setup_service"]
    checker_policy_id: UUID
    setup_run_id: UUID
    setup_generation: int = Field(ge=1)
    compilation_id: UUID
    finalization_id: UUID
    result_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    post_component_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    requirement_inventory_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    catalogue_manifest_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    upstream_approval_operation_id: UUID
    upstream_approval_output_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    effective_policy_id: UUID
    effective_policy_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    pre_submit_policy_id: UUID
    pre_submit_bundle_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    projection_operation_id: UUID
    operation_id: UUID
    request_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    target_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    policy_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    lifecycle_status: Literal["compiled", "approved", "superseded"]

    @model_validator(mode="after")
    def require_checker_policy_identity(self):
        """No unfinished setup step authorizes a downstream finalized-policy mutation."""
        if self.resource_id != self.checker_policy_id:
            raise ValueError("checker policy resource must match policy")
        if (self.execution_kind == "setup_service") != (self.target_kind == "derive"):
            raise ValueError("checker derivation requires setup-service authority")
        return self
