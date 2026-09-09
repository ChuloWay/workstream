"""Immutable post-submit catalogue and compiled-policy value contracts."""

from __future__ import annotations

import json
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, model_validator

from app.core.hashing import canonical_json_hash

Sha256 = Annotated[StrictStr, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
Identifier = Annotated[
    StrictStr, Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_.-]*$")
]
VersionNumber = Annotated[StrictInt, Field(ge=1, le=2_147_483_647)]
GuideVersion = Annotated[StrictStr, Field(min_length=1, max_length=50, pattern=r"\S")]
ResourceId = Annotated[UUID, Field(strict=True)]
ByteCount = Annotated[StrictInt, Field(ge=0, le=9_223_372_036_854_775_807)]
Severity = Literal["info", "low", "medium", "high", "critical"]
LEGACY_IMPLEMENTATION_VERSION = "workstream-structural-v1"
MODERN_CONTEXT_IMPLEMENTATION_VERSION = "workstream-policy-context-v2"
POST_SUBMIT_COMPILER_V2 = "workstream-post-submit-compiler-v0.2"
POST_SUBMIT_CATALOGUE_ID = "workstream.post_submission_checkers"
POST_SUBMIT_CATALOGUE_SCHEMA_V2 = "post_submission_checker_capability_projection.v2"
POST_SUBMIT_POLICY_SCHEMA_V2 = "post_submit_checker_policy.v2"


class PostSubmitValue(BaseModel):
    """Reject unknown fields and revalidate even previously constructed instances."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class EmptyPostSubmitConfiguration(PostSubmitValue):
    """The current registered structural implementations accept no parameters."""


class PostSubmitResourceLimits(PostSubmitValue):
    """Code-owned input ceilings; deadline enforcement belongs to the executor."""

    maximum_input_bytes: StrictInt = Field(default=1_048_576, ge=1, le=1_048_576)
    maximum_result_bytes: StrictInt = Field(default=4096, ge=1, le=4096)
    maximum_results: Literal[1] = 1
    maximum_generated_output_bytes: Literal[0] = 0
    deadline_ms: StrictInt = Field(default=5000, ge=1, le=5000)
    phase_deadline_ms: StrictInt = Field(default=45000, ge=1, le=45000)
    maximum_manifest_items: StrictInt = Field(default=1024, ge=1, le=1024)
    maximum_evidence_items: StrictInt = Field(default=1024, ge=1, le=1024)
    maximum_policy_items: StrictInt = Field(default=256, ge=1, le=256)
    maximum_text_characters: StrictInt = Field(default=65536, ge=1, le=65536)

    @model_validator(mode="before")
    @classmethod
    def reject_boolean_limits(cls, value: object) -> object:
        """Literal integer fields must not accept Python boolean equality."""
        if isinstance(value, dict) and any(type(item) is bool for item in value.values()):
            raise ValueError("post-submit limits require integers")
        return value


class PostSubmitDefinition(PostSubmitValue):
    """Registered implementation metadata, never a callable or authority grant."""

    capability_id: Identifier
    capability_version: Literal["v0.2"] = "v0.2"
    implementation_version: Identifier
    stage: Literal["post_submit"] = "post_submit"
    platform_default: StrictBool
    selectable: StrictBool
    state: Literal["enabled", "disabled"] = "enabled"
    disabled_behavior: Literal["unavailable"] = "unavailable"
    execution_method: Literal["deterministic"] = "deterministic"
    configuration_schema: Literal["post_submit_empty_configuration.v1"] = (
        "post_submit_empty_configuration.v1"
    )
    input_schema: Literal["post_submit_structural_input.v1"] = "post_submit_structural_input.v1"
    result_schema: Literal["post_submit_structural_result.v1"] = "post_submit_structural_result.v1"
    order: Annotated[StrictInt, Field(ge=1, le=9)]
    dependencies: tuple[Identifier, ...] = Field(default=(), max_length=8)
    supported_claim: Literal[
        "packet_presence",
        "policy_context_consistency",
        "evidence_presence",
        "evidence_structure",
        "required_path_presence",
        "forbidden_path_detection",
        "attestation_presence",
        "placeholder_signal_detection",
        "criteria_presence",
    ]
    failure_code: Literal[
        "packet_fields_missing",
        "policy_context_invalid",
        "evidence_missing",
        "evidence_structure_invalid",
        "required_files_missing",
        "forbidden_path_present",
        "attestation_missing",
        "placeholder_signal",
        "acceptance_criteria_missing",
    ]
    failure_category: Literal["submission_structure", "task_configuration"]
    failure_status: Literal["warning", "failed"] = "failed"
    failure_severity: Literal["medium", "high"] = "high"
    resources: PostSubmitResourceLimits = PostSubmitResourceLimits()
    provider_recovery: Literal["none"] = "none"
    required_output_roles: tuple[Identifier, ...] = Field(default=(), max_length=0)

    @model_validator(mode="after")
    def validate_classification(self) -> Self:
        """Require exactly one policy classification and consistent warning severity."""
        if self.platform_default == self.selectable:
            raise ValueError("post-submit definition classification is invalid")
        if (self.failure_status == "warning") != (self.failure_severity == "medium"):
            raise ValueError("post-submit failure severity is invalid")
        return self

    def validate_configuration(self, configuration: object) -> EmptyPostSubmitConfiguration:
        """Use the exact registered closed schema, including for empty parameters."""
        self = PostSubmitDefinition.model_validate(self)
        if self.state != "enabled":
            raise ValueError("post-submit definition is unavailable")
        return EmptyPostSubmitConfiguration.model_validate(configuration)


class PostSubmitCatalogue(PostSubmitValue):
    """A canonical frozen snapshot; its hash proves identity, not installation."""

    catalogue_id: Literal["workstream.post_submission_checkers"] = POST_SUBMIT_CATALOGUE_ID
    source_version: Literal["v0.2"] = "v0.2"
    schema_version: Literal["post_submission_checker_capability_projection.v2"] = (
        POST_SUBMIT_CATALOGUE_SCHEMA_V2
    )
    definitions: tuple[PostSubmitDefinition, ...] = Field(min_length=1, max_length=9)
    manifest_sha256: Sha256

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        """Validate order/dependencies and all hash-bound definition semantics."""
        seen: set[str] = set()
        orders: set[int] = set()
        previous = 0
        for definition in self.definitions:
            if definition.capability_id in seen or definition.order in orders:
                raise ValueError("post-submit catalogue has duplicate definitions")
            if definition.order <= previous or not set(definition.dependencies).issubset(seen):
                raise ValueError("post-submit catalogue order or dependency is invalid")
            seen.add(definition.capability_id)
            orders.add(definition.order)
            previous = definition.order
        if self.manifest_sha256 != canonical_json_hash(
            self.model_dump(mode="json", exclude={"manifest_sha256"})
        ):
            raise ValueError("post-submit catalogue hash mismatch")
        return self

    def definition(self, capability_id: str, version: str) -> PostSubmitDefinition:
        """Select exactly the pinned definition, with no latest-version substitution."""
        self = PostSubmitCatalogue.model_validate(self)
        for definition in self.definitions:
            if (definition.capability_id, definition.capability_version) == (
                capability_id,
                version,
            ):
                return definition
        raise ValueError("post-submit capability or version is unavailable")


class PostSubmitPolicyEntry(PostSubmitValue):
    """One ordered compiled entry pinned to an exact registered implementation."""

    checker_id: Identifier
    definition_version: Literal["v0.2"]
    implementation_version: Identifier
    classification: Literal["platform_default", "project_required", "project_warning"]
    configuration: EmptyPostSubmitConfiguration


class CompiledPostSubmitPolicyV2(PostSubmitValue):
    """Canonical policy body; its existing policy_hash remains the only plan hash."""

    schema_version: Literal["post_submit_checker_policy.v2"] = POST_SUBMIT_POLICY_SCHEMA_V2
    compiler_version: Literal["workstream-post-submit-compiler-v0.2"] = POST_SUBMIT_COMPILER_V2
    project_id: ResourceId
    guide_version: GuideVersion
    catalogue_id: Literal["workstream.post_submission_checkers"] = POST_SUBMIT_CATALOGUE_ID
    catalogue_source_version: Literal["v0.2"] = "v0.2"
    catalogue_schema_version: Literal["post_submission_checker_capability_projection.v2"] = (
        POST_SUBMIT_CATALOGUE_SCHEMA_V2
    )
    catalogue_manifest_sha256: Sha256
    entries: tuple[PostSubmitPolicyEntry, ...] = Field(min_length=1, max_length=9)
    blocking_severities: tuple[Severity, ...] = Field(min_length=2, max_length=5)

    @model_validator(mode="after")
    def validate_unique_entries(self) -> Self:
        """Never repeat a member or weaken the mandatory blocking floor."""
        if len({entry.checker_id for entry in self.entries}) != len(self.entries):
            raise ValueError("post-submit policy has duplicate entries")
        order = ("critical", "high", "medium", "low", "info")
        expected = tuple(item for item in order if item in self.blocking_severities)
        if expected != self.blocking_severities or not {"critical", "high"}.issubset(expected):
            raise ValueError("post-submit policy blocking severities are invalid")
        return self

    @property
    def policy_hash(self) -> str:
        """Hash the canonical body without adding a second persisted hash field."""
        return canonical_json_hash(self.model_dump(mode="json"))

    def validate_catalogue(self, catalogue: PostSubmitCatalogue) -> None:
        """Validate exact pinned members, defaults, configuration and ordering."""
        self = CompiledPostSubmitPolicyV2.model_validate(self)
        catalogue = PostSubmitCatalogue.model_validate(catalogue)
        if self.catalogue_manifest_sha256 != catalogue.manifest_sha256:
            raise ValueError("post-submit policy catalogue hash mismatch")
        defaults = {item.capability_id for item in catalogue.definitions if item.platform_default}
        actual_defaults: set[str] = set()
        previous = 0
        seen: set[str] = set()
        for entry in self.entries:
            definition = catalogue.definition(entry.checker_id, entry.definition_version)
            if entry.implementation_version != definition.implementation_version:
                raise ValueError("post-submit implementation version mismatch")
            if (entry.classification == "platform_default") != definition.platform_default:
                raise ValueError("post-submit policy default classification mismatch")
            definition.validate_configuration(entry.configuration)
            if definition.order <= previous or not set(definition.dependencies).issubset(seen):
                raise ValueError("post-submit policy order or dependency mismatch")
            if definition.platform_default:
                actual_defaults.add(entry.checker_id)
            previous = definition.order
            seen.add(entry.checker_id)
        if defaults != actual_defaults:
            raise ValueError("post-submit policy omits mandatory defaults")


def canonical_post_submit_bytes(
    value: PostSubmitValue, *, exclude: set[str] | None = None
) -> bytes:
    """Use the canonical hash encoding for finite serialized-size checks."""
    return json.dumps(
        value.model_dump(mode="json", exclude=exclude),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
