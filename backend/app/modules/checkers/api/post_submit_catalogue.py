"""Immutable post-submit catalogue and compiled-policy value contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
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
POST_SUBMIT_IMPLEMENTATION_ID = "workstream-structural"
POST_SUBMIT_COMPILER_ID = "workstream-post-submit-compiler"
POST_SUBMIT_CATALOGUE_ID = "workstream.post_submission_checkers"
POST_SUBMIT_CATALOGUE_SCHEMA = "post_submission_checker_capability_projection"
POST_SUBMIT_POLICY_SCHEMA = "post_submit_checker_policy"


class PostSubmitValue(BaseModel):
    """Reject unknown fields and revalidate even previously constructed instances."""

    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")


class EmptyPostSubmitConfiguration(PostSubmitValue):
    """The current registered structural implementations accept no parameters."""


class PostSubmitResourceLimits(PostSubmitValue):
    """Code-owned input ceilings; deadline enforcement belongs to the executor."""

    maximum_input_bytes: Literal[1_048_576] = 1_048_576
    maximum_result_bytes: Literal[4096] = 4096
    maximum_results: Literal[1] = 1
    maximum_generated_output_bytes: Literal[0] = 0
    deadline_ms: Literal[5000] = 5000
    phase_deadline_ms: Literal[45000] = 45000
    maximum_manifest_items: Literal[1024] = 1024
    maximum_evidence_items: Literal[1024] = 1024
    maximum_policy_items: Literal[256] = 256
    maximum_text_characters: Literal[65536] = 65536

    @model_validator(mode="before")
    @classmethod
    def reject_noninteger_limits(cls, value: object) -> object:
        """Exact integer literals must reject boolean, float and string coercion."""
        if isinstance(value, Mapping) and any(type(item) is not int for item in value.values()):
            raise ValueError("post-submit limits require integers")
        return value


class PostSubmitDefinition(PostSubmitValue):
    """Registered implementation metadata, never a callable or authority grant."""

    capability_id: Identifier
    capability_version: Literal["v0.1"] = "v0.1"
    implementation_version: Identifier
    stage: Literal["post_submit"] = "post_submit"
    platform_default: StrictBool
    selectable: StrictBool
    state: Literal["enabled", "disabled"] = "enabled"
    disabled_behavior: Literal["unavailable"] = "unavailable"
    execution_method: Literal["deterministic"] = "deterministic"
    configuration_schema: Literal["post_submit_empty_configuration"] = (
        "post_submit_empty_configuration"
    )
    input_schema: Literal["post_submit_structural_input"] = "post_submit_structural_input"
    result_schema: Literal["post_submit_structural_result"] = "post_submit_structural_result"
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
        if len(self.dependencies) != len(set(self.dependencies)):
            raise ValueError("post-submit definition has duplicate dependencies")
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
    source_version: Literal["v0.1"] = "v0.1"
    schema_version: Literal["post_submission_checker_capability_projection"] = (
        POST_SUBMIT_CATALOGUE_SCHEMA
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
    definition_version: Literal["v0.1"]
    implementation_version: Identifier
    classification: Literal["platform_default", "project_required", "project_warning"]
    configuration: EmptyPostSubmitConfiguration


class CompiledPostSubmitPolicy(PostSubmitValue):
    """Canonical policy body; its existing policy_hash remains the only plan hash."""

    schema_version: Literal["post_submit_checker_policy"] = POST_SUBMIT_POLICY_SCHEMA
    compiler_version: Literal["workstream-post-submit-compiler"] = POST_SUBMIT_COMPILER_ID
    project_id: ResourceId
    guide_version: GuideVersion
    catalogue_id: Literal["workstream.post_submission_checkers"] = POST_SUBMIT_CATALOGUE_ID
    catalogue_source_version: Literal["v0.1"] = "v0.1"
    catalogue_schema_version: Literal["post_submission_checker_capability_projection"] = (
        POST_SUBMIT_CATALOGUE_SCHEMA
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

    @property
    def policy_body(self) -> dict:
        """Return the one serialized policy representation."""
        return self.model_dump(mode="json")

    @property
    def default_checkers(self) -> list[str]:
        """Derive mandatory entries from the canonical policy."""
        return [
            entry.checker_id for entry in self.entries if entry.classification == "platform_default"
        ]

    @property
    def required_checkers(self) -> list[str]:
        """Derive project-required entries from the canonical policy."""
        return [
            entry.checker_id for entry in self.entries if entry.classification == "project_required"
        ]

    @property
    def warning_checkers(self) -> list[str]:
        """Derive advisory project entries from the canonical policy."""
        return [
            entry.checker_id for entry in self.entries if entry.classification == "project_warning"
        ]

    @property
    def execution_checkers(self) -> list[str]:
        """Derive execution order without another stored plan."""
        return [entry.checker_id for entry in self.entries]

    def validate_sidecars(
        self,
        *,
        required_checkers: list[str],
        warning_checkers: list[str],
        blocking_severities: list[str],
    ) -> None:
        """Reject persisted policy summaries that disagree with the canonical body."""
        if (
            required_checkers != self.required_checkers
            or warning_checkers != self.warning_checkers
            or blocking_severities != list(self.blocking_severities)
        ):
            raise ValueError("post-submit policy summaries disagree with canonical body")

    def validate_catalogue(self, catalogue: PostSubmitCatalogue) -> None:
        """Validate exact pinned members, defaults, configuration and ordering."""
        self = CompiledPostSubmitPolicy.model_validate(self)
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


_STRUCTURAL_DEFINITIONS = (
    ("check_submission_packet", "packet_presence", "packet_fields_missing", "submission_structure"),
    (
        "check_policy_context_present",
        "policy_context_consistency",
        "policy_context_invalid",
        "task_configuration",
    ),
    ("check_evidence_present", "evidence_presence", "evidence_missing", "submission_structure"),
    (
        "check_evidence_integrity",
        "evidence_structure",
        "evidence_structure_invalid",
        "submission_structure",
    ),
    (
        "check_required_files",
        "required_path_presence",
        "required_files_missing",
        "submission_structure",
    ),
    (
        "check_forbidden_files",
        "forbidden_path_detection",
        "forbidden_path_present",
        "submission_structure",
    ),
    (
        "check_confidentiality_attestation",
        "attestation_presence",
        "attestation_missing",
        "submission_structure",
    ),
    (
        "check_low_quality_generated_artifacts",
        "placeholder_signal_detection",
        "placeholder_signal",
        "submission_structure",
    ),
    (
        "check_acceptance_criteria_present",
        "criteria_presence",
        "acceptance_criteria_missing",
        "task_configuration",
    ),
)


def structural_definition(name: str) -> PostSubmitDefinition:
    """Mint the code-owned metadata attached to an explicit registration entry."""
    for order, (checker_id, claim, failure, category) in enumerate(_STRUCTURAL_DEFINITIONS, 1):
        if checker_id == name:
            warning = name == "check_low_quality_generated_artifacts"
            return PostSubmitDefinition(
                capability_id=name,
                implementation_version=POST_SUBMIT_IMPLEMENTATION_ID,
                platform_default=order <= 8,
                selectable=order == 9,
                order=order,
                supported_claim=claim,
                failure_code=failure,
                failure_category=category,
                failure_status="warning" if warning else "failed",
                failure_severity="medium" if warning else "high",
            )
    raise ValueError("unknown structural post-submit definition")


def current_post_submit_catalogue() -> PostSubmitCatalogue:
    """Return code-owned immutable metadata, without execution authority."""
    definitions = tuple(structural_definition(row[0]) for row in _STRUCTURAL_DEFINITIONS)
    body = {
        "catalogue_id": POST_SUBMIT_CATALOGUE_ID,
        "source_version": "v0.1",
        "schema_version": POST_SUBMIT_CATALOGUE_SCHEMA,
        "definitions": [item.model_dump(mode="json") for item in definitions],
    }
    return PostSubmitCatalogue(**body, manifest_sha256=canonical_json_hash(body))
