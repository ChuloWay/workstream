"""Exact AUTH resources for project-owned checker model effects."""

from __future__ import annotations

import json
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.authorization.catalogue import ActionId
from app.modules.checkers.api.model_calls import (
    ModelBudgetProvisioningFacts,
    ModelCallEffectAuthorityFacts,
    ModelCallEvidence,
    ModelCallExecutionFacts,
    ModelPaidSlotKey,
    ModelProfileProvisioningFacts,
    PreparedModelCallAttempt,
    model_action_digest,
)


PROFILE_PROVISION = ActionId.PROJECT_MODEL_PROFILE_PROVISION
BUDGET_CONFIGURE = ActionId.PROJECT_MODEL_BUDGET_CONFIGURE
RECOVERY_CHILD_AUTHORIZE = ActionId.PROJECT_MODEL_CALL_RECOVERY_CHILD_AUTHORIZE
PREPARE = ActionId.CHECKER_MODEL_CALL_PREPARE
DISPATCH = ActionId.CHECKER_MODEL_CALL_DISPATCH
RECOVER = ActionId.CHECKER_MODEL_CALL_RECOVER
OBSERVE = ActionId.CHECKER_MODEL_CALL_OBSERVE
COMPLETE = ActionId.CHECKER_MODEL_CALL_COMPLETE
GRANT = ActionId.CHECKER_MODEL_CALL_GRANT

MODEL_ADMIN_ACTIONS = frozenset({PROFILE_PROVISION, BUDGET_CONFIGURE, RECOVERY_CHILD_AUTHORIZE})
CHECKER_MODEL_CALL_ACTIONS = frozenset({PREPARE, DISPATCH, RECOVER, OBSERVE, COMPLETE, GRANT})
CHECKER_MODEL_ACTIONS = MODEL_ADMIN_ACTIONS | CHECKER_MODEL_CALL_ACTIONS

_STRICT_FROZEN = ConfigDict(extra="forbid", frozen=True, strict=True, revalidate_instances="always")
_Sha256 = str


class ModelCallPrepareAuthorityFacts(BaseModel):
    """Exact current execution, stable slot and first request commitment."""

    model_config = _STRICT_FROZEN
    execution: ModelCallExecutionFacts
    slot: ModelPaidSlotKey
    request_sha256: _Sha256 = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ModelCallDispatchAuthorityFacts(BaseModel):
    """Exact current execution, prepared attempt and verified request evidence."""

    model_config = _STRICT_FROZEN
    execution: ModelCallExecutionFacts
    attempt: PreparedModelCallAttempt
    request_evidence: ModelCallEvidence


class ModelCallRecoverAuthorityFacts(BaseModel):
    """A current execution attaching to one existing provider effect."""

    model_config = _STRICT_FROZEN
    execution: ModelCallExecutionFacts
    effect: ModelCallEffectAuthorityFacts


class ModelCallGrantAuthorityFacts(BaseModel):
    """Current execution and opaque invocation-grant commitment."""

    model_config = _STRICT_FROZEN
    execution: ModelCallExecutionFacts
    slot: ModelPaidSlotKey
    external_request_digest: _Sha256 = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    token_hash: _Sha256 = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ModelCallObserveAuthorityFacts(BaseModel):
    """Lease-independent uncertain-effect observation facts."""

    model_config = _STRICT_FROZEN
    effect: ModelCallEffectAuthorityFacts
    provider_response_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    observation_digest: _Sha256 = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ModelCallCompleteAuthorityFacts(BaseModel):
    """Lease-independent terminal effect and optional response evidence."""

    model_config = _STRICT_FROZEN
    effect: ModelCallEffectAuthorityFacts
    response_evidence: ModelCallEvidence | None
    terminal_digest: _Sha256 = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ModelCallRecoveryChildAuthorityFacts(BaseModel):
    """Operator-authorized child after one exact terminal parent effect."""

    model_config = _STRICT_FROZEN
    project_id: UUID
    parent_attempt_id: UUID
    terminal_digest: _Sha256 = Field(pattern=r"^sha256:[0-9a-f]{64}$")


RuntimeFacts = (
    ModelCallPrepareAuthorityFacts
    | ModelCallDispatchAuthorityFacts
    | ModelCallRecoverAuthorityFacts
    | ModelCallObserveAuthorityFacts
    | ModelCallCompleteAuthorityFacts
    | ModelCallGrantAuthorityFacts
)
AdminFacts = (
    ModelProfileProvisioningFacts
    | ModelBudgetProvisioningFacts
    | ModelCallRecoveryChildAuthorityFacts
)


class CheckerModelCallResourceContext(BaseModel):
    """One exact fixed-service model-call phase in a project scope."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["checker_model_call"] = "checker_model_call"
    resource_id: UUID
    scope_project_id: UUID
    action_id: ActionId
    facts: RuntimeFacts
    facts_digest: _Sha256 = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def exact_phase(self) -> Self:
        expected = {
            PREPARE: ModelCallPrepareAuthorityFacts,
            DISPATCH: ModelCallDispatchAuthorityFacts,
            RECOVER: ModelCallRecoverAuthorityFacts,
            OBSERVE: ModelCallObserveAuthorityFacts,
            COMPLETE: ModelCallCompleteAuthorityFacts,
            GRANT: ModelCallGrantAuthorityFacts,
        }.get(self.action_id)
        if expected is None or type(self.facts) is not expected:
            raise ValueError("invalid checker model call authority phase")
        project_id, resource_id = _runtime_identity(self.facts)
        if (
            self.scope_project_id != project_id
            or self.resource_id != resource_id
            or self.facts_digest != model_action_digest(self.action_id.value, self.facts)
        ):
            raise ValueError("invalid checker model call authority resource")
        return self


class ProjectModelAdministrationResourceContext(BaseModel):
    """Exact project target governed only by a current system Operator grant."""

    model_config = _STRICT_FROZEN
    resource_type: Literal["project_model_administration"] = "project_model_administration"
    resource_id: UUID
    project_id: UUID
    actor_profile_id: UUID
    action_id: ActionId
    facts: AdminFacts
    facts_digest: _Sha256 = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def exact_operation(self) -> Self:
        expected = {
            PROFILE_PROVISION: ModelProfileProvisioningFacts,
            BUDGET_CONFIGURE: ModelBudgetProvisioningFacts,
            RECOVERY_CHILD_AUTHORIZE: ModelCallRecoveryChildAuthorityFacts,
        }.get(self.action_id)
        if expected is None or type(self.facts) is not expected:
            raise ValueError("invalid project model administration phase")
        project_id, resource_id, actor_profile_id = _admin_identity(
            self.facts, self.actor_profile_id
        )
        if (
            self.project_id != project_id
            or self.resource_id != resource_id
            or self.actor_profile_id != actor_profile_id
            or self.facts_digest != model_action_digest(self.action_id.value, self.facts)
        ):
            raise ValueError("invalid project model administration resource")
        return self


CHECKER_MODEL_RESOURCE_BY_ACTION = {
    **{action: CheckerModelCallResourceContext for action in CHECKER_MODEL_CALL_ACTIONS},
    **{action: ProjectModelAdministrationResourceContext for action in MODEL_ADMIN_ACTIONS},
}
MODEL_ADMIN_RESOURCE_BY_ACTION = {
    action: ProjectModelAdministrationResourceContext for action in MODEL_ADMIN_ACTIONS
}


def checker_model_call_resource(
    action: ActionId, facts: RuntimeFacts
) -> CheckerModelCallResourceContext:
    """Build the only valid fixed-service resource for one phase."""
    project_id, resource_id = _runtime_identity(facts)
    return CheckerModelCallResourceContext(
        resource_id=resource_id,
        scope_project_id=project_id,
        action_id=action,
        facts=facts,
        facts_digest=model_action_digest(action.value, facts),
    )


def project_model_admin_resource(
    action: ActionId,
    facts: AdminFacts,
    *,
    actor_profile_id: UUID,
) -> ProjectModelAdministrationResourceContext:
    """Build one system-Operator resource retaining its exact project target."""
    project_id, resource_id, checked_actor = _admin_identity(facts, actor_profile_id)
    return ProjectModelAdministrationResourceContext(
        resource_id=resource_id,
        project_id=project_id,
        actor_profile_id=checked_actor,
        action_id=action,
        facts=facts,
        facts_digest=model_action_digest(action.value, facts),
    )


def parse_checker_model_prepare(
    action: ActionId, value: object, invalid_error: type[Exception]
) -> CheckerModelCallResourceContext | ProjectModelAdministrationResourceContext | None:
    """Parse the exact resource committed before AUTH locks product owners."""
    expected = CHECKER_MODEL_RESOURCE_BY_ACTION.get(action)
    if expected is None:
        return None
    try:
        # Prepared requests are retained as JSON-compatible values. Re-enter through
        # JSON validation so strict UUID/datetime fields receive their wire types
        # without weakening integer, boolean, enum or object validation.
        resource = expected.model_validate_json(json.dumps(value))
        if resource.action_id is not action:
            raise ValueError("checker model action mismatch")
        return resource
    except (TypeError, ValueError) as error:
        raise invalid_error("invalid prepared checker model authority") from error


def checker_model_prepare_matches(
    prepared: CheckerModelCallResourceContext | ProjectModelAdministrationResourceContext | None,
    resource: object,
) -> bool:
    """Require final facts to equal the resource committed at preparation."""
    return prepared is not None and type(resource) is type(prepared) and resource == prepared


def _runtime_identity(facts: RuntimeFacts) -> tuple[UUID, UUID]:
    if type(facts) is ModelCallPrepareAuthorityFacts:
        if not _execution_matches_slot(facts.execution, facts.slot):
            raise ValueError("checker model project mismatch")
        return facts.execution.project_id, facts.execution.evaluation_request_id
    if type(facts) is ModelCallDispatchAuthorityFacts:
        if not _execution_matches_slot(facts.execution, facts.attempt.slot_key):
            raise ValueError("checker model project mismatch")
        return facts.execution.project_id, facts.attempt.attempt_id
    if type(facts) is ModelCallRecoverAuthorityFacts:
        if (
            not _execution_matches_slot(facts.execution, facts.effect.slot_key)
            or facts.execution.project_id != facts.effect.project_id
            or facts.execution.task_id != facts.effect.task_id
        ):
            raise ValueError("checker model recovery effect mismatch")
        return facts.execution.project_id, facts.effect.attempt_id
    if type(facts) is ModelCallGrantAuthorityFacts:
        if not _execution_matches_slot(facts.execution, facts.slot):
            raise ValueError("checker model grant project mismatch")
        return facts.execution.project_id, facts.execution.evaluation_request_id
    if type(facts) in {ModelCallObserveAuthorityFacts, ModelCallCompleteAuthorityFacts}:
        if facts.effect.project_id != facts.effect.slot_key.project_id:
            raise ValueError("checker model project mismatch")
        return facts.effect.project_id, facts.effect.attempt_id
    raise ValueError("invalid checker model runtime facts")


def _execution_matches_slot(execution: ModelCallExecutionFacts, slot: ModelPaidSlotKey) -> bool:
    return (
        execution.project_id,
        execution.assignment_id,
        execution.submission_id,
        execution.submission_version,
    ) == (
        slot.project_id,
        slot.assignment_id,
        slot.submission_id,
        slot.submission_version,
    )


def _admin_identity(facts: AdminFacts, actor_profile_id: UUID) -> tuple[UUID, UUID, UUID]:
    if type(facts) in {ModelProfileProvisioningFacts, ModelBudgetProvisioningFacts}:
        return facts.spec.project_id, facts.operation_id, facts.actor_profile_id
    if type(facts) is ModelCallRecoveryChildAuthorityFacts:
        return facts.project_id, facts.parent_attempt_id, actor_profile_id
    raise ValueError("invalid project model administration facts")


__all__ = (
    "BUDGET_CONFIGURE",
    "CHECKER_MODEL_ACTIONS",
    "CHECKER_MODEL_CALL_ACTIONS",
    "CHECKER_MODEL_RESOURCE_BY_ACTION",
    "COMPLETE",
    "CheckerModelCallResourceContext",
    "DISPATCH",
    "GRANT",
    "MODEL_ADMIN_ACTIONS",
    "MODEL_ADMIN_RESOURCE_BY_ACTION",
    "ModelCallCompleteAuthorityFacts",
    "ModelCallDispatchAuthorityFacts",
    "ModelCallGrantAuthorityFacts",
    "ModelCallObserveAuthorityFacts",
    "ModelCallPrepareAuthorityFacts",
    "ModelCallRecoverAuthorityFacts",
    "ModelCallRecoveryChildAuthorityFacts",
    "OBSERVE",
    "PREPARE",
    "PROFILE_PROVISION",
    "ProjectModelAdministrationResourceContext",
    "RECOVER",
    "RECOVERY_CHILD_AUTHORIZE",
    "checker_model_call_resource",
    "checker_model_prepare_matches",
    "parse_checker_model_prepare",
    "project_model_admin_resource",
)
