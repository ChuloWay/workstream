"""Locked external-checker policies compiled from approved guide bindings."""

from __future__ import annotations

import json
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
    WORKSTREAM_DEFAULT_CHECKER_ID,
    WORKSTREAM_DEFAULT_CHECKER_VERSION,
)
from app.modules.checkers.api.external import (
    EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS,
    ExternalCheckerPhase,
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistryPort,
    external_checker_json_hash,
)


WORKSTREAM_DEFAULT_EXECUTION_BUDGET_MS = 60_000
MAXIMUM_SELECTED_PRE_EXECUTION_BUDGET_MS = 7_200_000
SELECTED_POST_MATERIALIZATION_BUDGET_MS = 60_000
# The outbox claim is natively bounded to one hour. Keep explicit time for the
# request reader/authority prelude, execution finalization and delivery commit.
MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS = 3_400_000
SELECTED_POST_HANDLER_PRELUDE_MARGIN_MS = 60_000
SELECTED_POST_FINALIZATION_MARGIN_MS = 60_000
SELECTED_POST_HANDLER_TIMEOUT_SECONDS = (
    MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS
    + SELECTED_POST_HANDLER_PRELUDE_MARGIN_MS
    + SELECTED_POST_FINALIZATION_MARGIN_MS
) // 1000
SELECTED_POST_DELIVERY_LEASE_SECONDS = 3_600


class ExternalCheckerPolicyError(ValueError):
    """Reject incomplete, stale or phase-substituted locked checker policy."""


class _PolicyValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class LockedExternalCheckerBinding(_PolicyValue):
    """One requirement bound to an exact immutable registry publication."""

    requirement_id: str = Field(min_length=1, max_length=100)
    stage: ExternalCheckerPhase
    registry: ExternalCheckerRegistryEntry
    configuration: dict[str, JsonValue]
    configuration_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        if self.registry.phase != self.stage:
            raise ExternalCheckerPolicyError("checker binding phase mismatch")
        self.registry.configuration_schema.validate_instance(self.configuration)
        if self.configuration_sha256 != external_checker_json_hash(self.configuration):
            raise ExternalCheckerPolicyError("checker binding configuration mismatch")
        return self


class LockedWorkstreamDefault(_PolicyValue):
    """Code-owned default identity included in every approved pre policy."""

    checker_id: Literal[WORKSTREAM_DEFAULT_CHECKER_ID] = WORKSTREAM_DEFAULT_CHECKER_ID
    checker_version: Literal[WORKSTREAM_DEFAULT_CHECKER_VERSION] = (
        WORKSTREAM_DEFAULT_CHECKER_VERSION
    )
    behavior_sha256: str = Field(
        default=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_behavior(self) -> Self:
        """Bind the locked identity to the executable code-owned manifest."""
        if self.behavior_sha256 != WORKSTREAM_DEFAULT_BEHAVIOR_SHA256:
            raise ExternalCheckerPolicyError("default checker behavior mismatch")
        return self


class LockedExternalPreSubmitPolicy(_PolicyValue):
    """One default followed by every required project pre-submit image."""

    schema_version: Literal["external_pre_submit_policy.v1"] = "external_pre_submit_policy.v1"
    workstream_default: LockedWorkstreamDefault = Field(default_factory=LockedWorkstreamDefault)
    entries: tuple[LockedExternalCheckerBinding, ...]
    policy_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        _validate_entries(self.entries, "pre_submit")
        if self.policy_sha256 != canonical_json_hash(
            self.model_dump(mode="json", exclude={"policy_sha256"})
        ):
            raise ExternalCheckerPolicyError("pre-submit policy digest mismatch")
        selected_pre_submit_execution_budget_ms(
            self, artifact_deadline_ms=MAXIMUM_SELECTED_PRE_EXECUTION_BUDGET_MS
        )
        return self


class LockedExternalPostSubmitPolicy(_PolicyValue):
    """Every required post-submit image; checkers retain no acceptance authority."""

    schema_version: Literal["external_post_submit_policy.v1"] = "external_post_submit_policy.v1"
    entries: tuple[LockedExternalCheckerBinding, ...]
    policy_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_policy(self) -> Self:
        _validate_entries(self.entries, "post_submit")
        if self.policy_sha256 != canonical_json_hash(
            self.model_dump(mode="json", exclude={"policy_sha256"})
        ):
            raise ExternalCheckerPolicyError("post-submit policy digest mismatch")
        # Approval, admission and dispatch share this closed runnable policy.
        selected_post_submit_execution_budget_ms(self)
        return self


class LockedExternalCheckerPolicies(_PolicyValue):
    """Complete approval-time pre/post policy custody for one guide generation."""

    schema_version: Literal["external_checker_policies.v1"] = "external_checker_policies.v1"
    pre_submit: LockedExternalPreSubmitPolicy
    post_submit: LockedExternalPostSubmitPolicy
    policies_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_policies(self) -> Self:
        if self.policies_sha256 != canonical_json_hash(
            self.model_dump(mode="json", exclude={"policies_sha256"})
        ):
            raise ExternalCheckerPolicyError("checker policies digest mismatch")
        return self


def validate_stored_external_checker_policies(
    value: object,
) -> LockedExternalCheckerPolicies:
    """Decode retained JSON through strict UUID and timestamp model boundaries."""
    return LockedExternalCheckerPolicies.model_validate_json(
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    )


def validate_stored_external_pre_policy(value: object) -> LockedExternalPreSubmitPolicy:
    """Decode one retained selected PRE policy without Python-string coercion."""
    return LockedExternalPreSubmitPolicy.model_validate_json(
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    )


def validate_stored_external_post_policy(value: object) -> LockedExternalPostSubmitPolicy:
    """Decode one retained selected POST policy without Python-string coercion."""
    return LockedExternalPostSubmitPolicy.model_validate_json(
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    )


def _validate_entries(
    entries: tuple[LockedExternalCheckerBinding, ...], phase: ExternalCheckerPhase
) -> None:
    identities = [
        (
            item.requirement_id,
            item.registry.capability_id,
            item.registry.capability_version,
        )
        for item in entries
    ]
    if any(item.stage != phase for item in entries) or identities != sorted(identities):
        raise ExternalCheckerPolicyError("checker policy order is not canonical")
    if len(identities) != len(set(identities)):
        raise ExternalCheckerPolicyError("checker policy binding is duplicated")


async def compile_external_checker_policies(
    result: object,
    registry: ExternalCheckerRegistryPort,
) -> tuple[LockedExternalPreSubmitPolicy, LockedExternalPostSubmitPolicy]:
    """Resolve every supported binding to exact immutable registry custody."""
    from app.interfaces.project_agents import ProjectGuideCompilationResult

    result = ProjectGuideCompilationResult.model_validate(result)
    if result.status == "guide_blocked":
        raise ExternalCheckerPolicyError("checker capability coverage is incomplete")
    requirements = {item.requirement_id: item for item in result.requirements}
    if len(requirements) != len(result.requirements):
        raise ExternalCheckerPolicyError("checker requirements are duplicated")
    pre = await _resolve(result.pre_submit_bindings, requirements, registry, "pre_submit")
    post = await _resolve(result.post_submit_bindings, requirements, registry, "post_submit")
    return _make_policy(LockedExternalPreSubmitPolicy, pre), _make_policy(
        LockedExternalPostSubmitPolicy, post
    )


async def compile_external_checker_policy_bundle(
    result: object,
    registry: ExternalCheckerRegistryPort,
) -> LockedExternalCheckerPolicies:
    """Lock both execution phases into one immutable approval-time value."""
    pre, post = await compile_external_checker_policies(result, registry)
    body = {
        "schema_version": "external_checker_policies.v1",
        "pre_submit": pre.model_dump(mode="json"),
        "post_submit": post.model_dump(mode="json"),
    }
    return LockedExternalCheckerPolicies(
        pre_submit=pre,
        post_submit=post,
        policies_sha256=canonical_json_hash(body),
    )


async def _resolve(bindings, requirements, registry, phase):
    from app.interfaces.project_agents import (
        RequirementDisposition,
    )

    expected = (
        RequirementDisposition.SUPPORTED_PRE_SUBMIT
        if phase == "pre_submit"
        else RequirementDisposition.SUPPORTED_POST_SUBMIT
    )
    resolved = []
    for binding in sorted(
        bindings,
        key=lambda item: (item.requirement_id, item.capability_id, item.capability_version),
    ):
        if (
            requirements.get(binding.requirement_id) is None
            or requirements[binding.requirement_id].disposition is not expected
            or binding.stage.value != phase
        ):
            raise ExternalCheckerPolicyError("checker binding does not cover requirement")
        entry = await registry.read_identity(
            capability_id=binding.capability_id,
            capability_version=binding.capability_version,
            phase=phase,
        )
        if (
            entry.capability_id != binding.capability_id
            or entry.capability_version != binding.capability_version
            or entry.phase != phase
        ):
            raise ExternalCheckerPolicyError("checker registry identity mismatch")
        configuration = {
            parameter.name: parameter.model_dump(mode="json")["value"]
            for parameter in binding.parameters
        }
        resolved.append(
            LockedExternalCheckerBinding(
                requirement_id=binding.requirement_id,
                stage=phase,
                registry=entry,
                configuration=configuration,
                configuration_sha256=external_checker_json_hash(configuration),
            )
        )
    expected_ids = {
        item.requirement_id for item in requirements.values() if item.disposition is expected
    }
    if {item.requirement_id for item in resolved} != expected_ids:
        raise ExternalCheckerPolicyError("checker requirement coverage is incomplete")
    return tuple(resolved)


def _make_policy(model, entries):
    hash_body = {
        "schema_version": model.model_fields["schema_version"].default,
        "entries": [item.model_dump(mode="json") for item in entries],
    }
    if model is LockedExternalPreSubmitPolicy:
        default = LockedWorkstreamDefault()
        hash_body["workstream_default"] = default.model_dump(mode="json")
        return model(
            workstream_default=default,
            entries=entries,
            policy_sha256=canonical_json_hash(hash_body),
        )
    return model(entries=entries, policy_sha256=canonical_json_hash(hash_body))


def selected_pre_submit_execution_budget_ms(
    policy: LockedExternalPreSubmitPolicy,
    *,
    artifact_deadline_ms: int,
) -> int:
    """Return the exact ordered work budget only when ART can keep custody alive."""
    if (
        type(policy) is not LockedExternalPreSubmitPolicy
        or type(artifact_deadline_ms) is not int
        or artifact_deadline_ms <= 0
        or artifact_deadline_ms > MAXIMUM_SELECTED_PRE_EXECUTION_BUDGET_MS
    ):
        raise ExternalCheckerPolicyError("selected PRE execution budget is invalid")
    required = WORKSTREAM_DEFAULT_EXECUTION_BUDGET_MS + sum(
        binding.registry.resources.deadline_ms + EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS
        for binding in policy.entries
    )
    if required > artifact_deadline_ms:
        raise ExternalCheckerPolicyError("selected PRE execution exceeds ART custody deadline")
    return required


def selected_post_submit_execution_budget_ms(
    policy: LockedExternalPostSubmitPolicy,
    *,
    artifact_deadline_ms: int | None = None,
) -> int:
    """Bound ART materialization and every ordered POST image under one lease."""
    if (
        type(policy) is not LockedExternalPostSubmitPolicy
        or artifact_deadline_ms is not None
        and (type(artifact_deadline_ms) is not int or artifact_deadline_ms <= 0)
    ):
        raise ExternalCheckerPolicyError("selected POST execution budget is invalid")
    required = SELECTED_POST_MATERIALIZATION_BUDGET_MS + sum(
        binding.registry.resources.deadline_ms + EXTERNAL_CHECKER_EXECUTION_CLEANUP_MARGIN_MS
        for binding in policy.entries
    )
    if required > MAXIMUM_SELECTED_POST_EXECUTION_BUDGET_MS:
        raise ExternalCheckerPolicyError("selected POST execution exceeds durable worker deadline")
    if artifact_deadline_ms is not None and required > artifact_deadline_ms:
        raise ExternalCheckerPolicyError("selected POST execution exceeds ART custody deadline")
    return required
