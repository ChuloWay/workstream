"""Immutable authority for bounded external-checker trial execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
import re
from types import MappingProxyType
from typing import Literal, Mapping
from uuid import UUID

from app.modules.checkers.api.external import external_checker_json_hash


Sha256 = str
Identifier = str
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_.-]{0,99}")
_RETAINABLE_OUTCOMES = frozenset({"succeeded", "exit_nonzero", "signalled"})


class TrialProfileError(ValueError):
    """A selector, trusted profile, or project projection is malformed."""


@dataclass(frozen=True, slots=True)
class TrialProfileSelector:
    """Exact immutable trial-profile version selected by locked policy."""

    profile_id: UUID
    profile_version: int
    profile_digest: Sha256

    def __post_init__(self) -> None:
        if (
            type(self.profile_id) is not UUID
            or type(self.profile_version) is not int
            or self.profile_version < 1
            or type(self.profile_digest) is not str
            or _DIGEST.fullmatch(self.profile_digest) is None
        ):
            raise TrialProfileError("trial profile selector is invalid")


@dataclass(frozen=True, slots=True)
class TrialProjectionSelector:
    """Exact immutable project projection selected by locked policy."""

    projection_id: UUID
    projection_version: int
    projection_digest: Sha256

    def __post_init__(self) -> None:
        if (
            type(self.projection_id) is not UUID
            or type(self.projection_version) is not int
            or self.projection_version < 1
            or type(self.projection_digest) is not str
            or _DIGEST.fullmatch(self.projection_digest) is None
        ):
            raise TrialProfileError("trial projection selector is invalid")


@dataclass(frozen=True, slots=True)
class TrialResourceCeilings:
    """Whole-invocation and per-operation limits owned by trusted config."""

    maximum_total_timeout_ms: int
    maximum_build_timeout_ms: int
    maximum_step_timeout_ms: int
    maximum_steps: int
    maximum_cpu_quota_millis: int
    maximum_cpu_time_ms: int
    maximum_wall_time_overrun_ms: int
    maximum_cpu_time_overrun_ms: int
    maximum_memory_bytes: int
    maximum_swap_bytes: int
    maximum_memory_overrun_bytes: int
    maximum_pids: int
    maximum_pids_overrun: int
    maximum_disk_bytes: int
    maximum_disk_overrun_bytes: int
    maximum_entries: int
    maximum_entries_overrun: int
    maximum_step_output_bytes: int
    maximum_observation_bytes: int
    maximum_receipt_bytes: int
    maximum_frame_bytes: int
    maximum_response_bytes: int

    def __post_init__(self) -> None:
        values = asdict(self)
        if any(type(value) is not int or value < 1 for value in values.values()):
            raise TrialProfileError("trial resource ceiling is invalid")
        if self.maximum_build_timeout_ms > self.maximum_total_timeout_ms or (
            self.maximum_step_timeout_ms > self.maximum_total_timeout_ms
        ):
            raise TrialProfileError("trial timeout ceiling is invalid")
        if self.maximum_memory_bytes != self.maximum_swap_bytes:
            raise TrialProfileError("trial swap must be disabled")
        if any(
            value > 4 * 1024 * 1024
            for value in (
                self.maximum_step_output_bytes,
                self.maximum_observation_bytes,
                self.maximum_receipt_bytes,
                self.maximum_frame_bytes,
                self.maximum_response_bytes,
            )
        ):
            raise TrialProfileError("trial byte ceiling is invalid")


@dataclass(frozen=True, slots=True)
class TrialExecutionProfile:
    """One trusted node-provisioned generic builder/runner profile."""

    schema_version: Literal["workstream.trial_execution_profile.v1"]
    selector: TrialProfileSelector
    runtime: Literal["runsc"]
    isolation_mode: Literal["gvisor"]
    outer_host_uds: Literal["open"]
    child_host_uds: Literal["none"]
    outer_runtime_config_digest: Sha256
    child_runtime_config_digest: Sha256
    engine_identity_digest: Sha256
    platform: str
    platform_identity_digest: Sha256
    builder_image_digest: Sha256
    offline_cache_digest: Sha256
    approved_base_digests: tuple[Sha256, ...]
    permitted_source_roles: tuple[Identifier, ...]
    permitted_material_roles: tuple[Identifier, ...]
    permitted_operations: tuple[Literal["run"], ...]
    permitted_state_retention_outcomes: tuple[
        Literal["succeeded", "exit_nonzero", "signalled"], ...
    ]
    builder_capabilities: tuple[Literal["CHOWN", "DAC_OVERRIDE", "FOWNER", "SYS_CHROOT"], ...]
    child_capabilities: tuple[()]
    child_network: Literal["none"]
    child_runs_as_non_root: Literal[True]
    limits: TrialResourceCeilings

    def __post_init__(self) -> None:
        if (
            self.schema_version != "workstream.trial_execution_profile.v1"
            or self.runtime != "runsc"
            or self.isolation_mode != "gvisor"
            or self.outer_host_uds != "open"
            or self.child_host_uds != "none"
            or self.child_network != "none"
            or self.child_runs_as_non_root is not True
            or self.child_capabilities != ()
            or self.builder_capabilities != ("CHOWN", "DAC_OVERRIDE", "FOWNER", "SYS_CHROOT")
            or self.permitted_operations != ("run",)
            or not self.permitted_state_retention_outcomes
            or len(set(self.permitted_state_retention_outcomes))
            != len(self.permitted_state_retention_outcomes)
            or not set(self.permitted_state_retention_outcomes) <= _RETAINABLE_OUTCOMES
            or type(self.platform) is not str
            or not re.fullmatch(r"linux/[a-z0-9_.-]{1,32}", self.platform)
        ):
            raise TrialProfileError("trial execution profile is invalid")
        digests = (
            self.outer_runtime_config_digest,
            self.child_runtime_config_digest,
            self.engine_identity_digest,
            self.platform_identity_digest,
            self.builder_image_digest,
            self.offline_cache_digest,
            *self.approved_base_digests,
        )
        if (
            not self.approved_base_digests
            or len(set(self.approved_base_digests)) != len(self.approved_base_digests)
            or any(type(value) is not str or _DIGEST.fullmatch(value) is None for value in digests)
            or not self.permitted_material_roles
            or not self.permitted_source_roles
            or len(set(self.permitted_source_roles)) != len(self.permitted_source_roles)
            or len(set(self.permitted_material_roles)) != len(self.permitted_material_roles)
            or any(
                type(value) is not str or _IDENTIFIER.fullmatch(value) is None
                for value in (*self.permitted_source_roles, *self.permitted_material_roles)
            )
            or profile_digest(self) != self.selector.profile_digest
        ):
            raise TrialProfileError("trial execution profile digest differs")


@dataclass(frozen=True, slots=True)
class TrialSlotProjection:
    """One ordered project-selected operation with an exact material view."""

    slot_kind: Identifier
    minimum_occurrences: int
    maximum_occurrences: int
    seed_roles: tuple[Identifier, ...]
    visible_roles: tuple[Identifier, ...]
    fresh_workspace: bool
    retain_state_after: tuple[Literal["succeeded", "exit_nonzero", "signalled"], ...]

    def __post_init__(self) -> None:
        if (
            type(self.slot_kind) is not str
            or _IDENTIFIER.fullmatch(self.slot_kind) is None
            or type(self.minimum_occurrences) is not int
            or type(self.maximum_occurrences) is not int
            or self.minimum_occurrences < 0
            or self.maximum_occurrences < max(1, self.minimum_occurrences)
            or len(set(self.seed_roles)) != len(self.seed_roles)
            or len(set(self.visible_roles)) != len(self.visible_roles)
            or any(
                type(value) is not str or _IDENTIFIER.fullmatch(value) is None
                for value in (*self.seed_roles, *self.visible_roles)
            )
            or type(self.fresh_workspace) is not bool
            or not self.retain_state_after
            or len(set(self.retain_state_after)) != len(self.retain_state_after)
            or not set(self.retain_state_after) <= _RETAINABLE_OUTCOMES
        ):
            raise TrialProfileError("trial slot projection is invalid")


@dataclass(frozen=True, slots=True)
class TrialMaterialProjection:
    """One private engine projection from an authorized source-material role."""

    role: Identifier
    source_role: Identifier
    projection_kind: Literal["build_context", "state_seed", "state_overlay"]
    source_relative: str
    destination_relative: str
    exclusions: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            type(self.role) is not str
            or _IDENTIFIER.fullmatch(self.role) is None
            or type(self.source_role) is not str
            or _IDENTIFIER.fullmatch(self.source_role) is None
            or self.projection_kind not in {"build_context", "state_seed", "state_overlay"}
            or not _safe_relative(self.source_relative, allow_dot=True)
            or not _safe_relative(self.destination_relative, allow_dot=True)
            or self.projection_kind == "state_overlay"
            and self.destination_relative == "."
            or tuple(sorted(set(self.exclusions))) != self.exclusions
            or any(not _safe_relative(value, allow_dot=False) for value in self.exclusions)
            or _paths_overlap(self.exclusions)
        ):
            raise TrialProfileError("trial material projection is invalid")


@dataclass(frozen=True, slots=True)
class TrialExecutionProjection:
    """Exact project-owned subset resolved from trusted immutable config."""

    selector: TrialProjectionSelector
    trial_kind: Identifier
    material_projections: tuple[TrialMaterialProjection, ...]
    allowed_material_roles: tuple[Identifier, ...]
    build_context_roles: tuple[Identifier, ...]
    slot_templates: tuple[TrialSlotProjection, ...]

    def __post_init__(self) -> None:
        allowed = set(self.allowed_material_roles)
        projected = {item.role for item in self.material_projections}
        if (
            type(self.trial_kind) is not str
            or _IDENTIFIER.fullmatch(self.trial_kind) is None
            or not allowed
            or not self.material_projections
            or len(projected) != len(self.material_projections)
            or projected != allowed
            or len(allowed) != len(self.allowed_material_roles)
            or any(
                type(value) is not str or _IDENTIFIER.fullmatch(value) is None
                for value in (*self.allowed_material_roles, *self.build_context_roles)
            )
            or not set(self.build_context_roles) <= allowed
            or not self.build_context_roles
            or not self.slot_templates
            or len({slot.slot_kind for slot in self.slot_templates}) != len(self.slot_templates)
            or any(not set(slot.visible_roles) <= allowed for slot in self.slot_templates)
            or any(not set(slot.seed_roles) <= allowed for slot in self.slot_templates)
            or any(
                _paths_overlap(
                    tuple(
                        item.destination_relative
                        for item in self.material_projections
                        if item.projection_kind == kind
                    )
                )
                for kind in ("build_context", "state_seed", "state_overlay")
            )
            or any(
                next(
                    item for item in self.material_projections if item.role == role
                ).projection_kind
                != "build_context"
                for role in self.build_context_roles
            )
            or any(
                next(
                    item for item in self.material_projections if item.role == role
                ).projection_kind
                != "state_seed"
                for slot in self.slot_templates
                for role in slot.seed_roles
            )
            or any(
                next(
                    item for item in self.material_projections if item.role == role
                ).projection_kind
                != "state_overlay"
                for slot in self.slot_templates
                for role in slot.visible_roles
            )
            or any(
                _paths_overlap(
                    tuple(
                        next(
                            item for item in self.material_projections if item.role == role
                        ).destination_relative
                        for role in (*slot.seed_roles, *slot.visible_roles)
                    )
                )
                for slot in self.slot_templates
            )
            or projection_digest(self) != self.selector.projection_digest
        ):
            raise TrialProfileError("trial execution projection is invalid")

    def validate_profile(self, profile: TrialExecutionProfile) -> None:
        """Require the project projection to be a subset of trusted authority."""
        if (
            not set(self.allowed_material_roles) <= set(profile.permitted_material_roles)
            or not {item.source_role for item in self.material_projections}
            <= set(profile.permitted_source_roles)
            or sum(slot.maximum_occurrences for slot in self.slot_templates)
            > profile.limits.maximum_steps
            or any(
                not set(slot.retain_state_after) <= set(profile.permitted_state_retention_outcomes)
                for slot in self.slot_templates
            )
        ):
            raise TrialProfileError("trial execution projection exceeds profile")


def _selector_value(selector: TrialProfileSelector, *, include_digest: bool) -> dict[str, object]:
    value = {
        "profile_id": str(selector.profile_id),
        "profile_version": selector.profile_version,
    }
    if include_digest:
        value["profile_digest"] = selector.profile_digest
    return value


def profile_digest(profile: TrialExecutionProfile) -> Sha256:
    """Hash the canonical immutable payload without its self-referential digest."""
    value = asdict(profile)
    value["selector"] = _selector_value(profile.selector, include_digest=False)
    return external_checker_json_hash(value)


def make_trial_execution_profile(**fields: object) -> TrialExecutionProfile:
    """Derive, then validate, the profile digest; callers cannot choose it."""
    selector = fields.get("selector")
    if not isinstance(selector, TrialProfileSelector):
        raise TrialProfileError("trial profile selector is invalid")
    placeholder = TrialProfileSelector(
        profile_id=selector.profile_id,
        profile_version=selector.profile_version,
        profile_digest="sha256:" + "0" * 64,
    )
    candidate = object.__new__(TrialExecutionProfile)
    for name in TrialExecutionProfile.__dataclass_fields__:
        object.__setattr__(candidate, name, placeholder if name == "selector" else fields[name])
    derived = profile_digest(candidate)
    exact = dict(fields)
    exact["selector"] = TrialProfileSelector(
        profile_id=selector.profile_id,
        profile_version=selector.profile_version,
        profile_digest=derived,
    )
    return TrialExecutionProfile(**exact)


def projection_digest(projection: TrialExecutionProjection) -> Sha256:
    """Hash the canonical immutable projection without its self digest."""
    value = asdict(projection)
    value["selector"] = {
        "projection_id": str(projection.selector.projection_id),
        "projection_version": projection.selector.projection_version,
    }
    return external_checker_json_hash(value)


def make_trial_execution_projection(**fields: object) -> TrialExecutionProjection:
    """Derive, then validate, a project projection digest."""
    selector = fields.get("selector")
    if not isinstance(selector, TrialProjectionSelector):
        raise TrialProfileError("trial projection selector is invalid")
    placeholder = TrialProjectionSelector(
        projection_id=selector.projection_id,
        projection_version=selector.projection_version,
        projection_digest="sha256:" + "0" * 64,
    )
    candidate = object.__new__(TrialExecutionProjection)
    for name in TrialExecutionProjection.__dataclass_fields__:
        object.__setattr__(candidate, name, placeholder if name == "selector" else fields[name])
    exact = dict(fields)
    exact["selector"] = TrialProjectionSelector(
        projection_id=selector.projection_id,
        projection_version=selector.projection_version,
        projection_digest=projection_digest(candidate),
    )
    return TrialExecutionProjection(**exact)


@dataclass(frozen=True, slots=True)
class TrialExecutionSelector:
    """Flat policy selection of one compatible profile/projection pair."""

    profile: TrialProfileSelector
    projection: TrialProjectionSelector


def trial_selector_from_configuration(
    configuration: Mapping[str, object],
) -> TrialExecutionSelector | None:
    """Parse only flat immutable selectors from locked checker configuration."""
    selector_keys = {
        "trial_profile_id",
        "trial_profile_version",
        "trial_profile_digest",
        "trial_projection_id",
        "trial_projection_version",
        "trial_projection_digest",
    }
    present = selector_keys & configuration.keys()
    if not present:
        return None
    if present != selector_keys or "trial_execution" in configuration:
        raise TrialProfileError("trial execution selector is incomplete")
    try:
        return TrialExecutionSelector(
            profile=TrialProfileSelector(
                profile_id=UUID(configuration["trial_profile_id"]),
                profile_version=configuration["trial_profile_version"],
                profile_digest=configuration["trial_profile_digest"],
            ),
            projection=TrialProjectionSelector(
                projection_id=UUID(configuration["trial_projection_id"]),
                projection_version=configuration["trial_projection_version"],
                projection_digest=configuration["trial_projection_digest"],
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, TrialProfileError):
            raise
        raise TrialProfileError("trial execution projection is invalid") from exc


def _string_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise TrialProfileError("trial execution projection is invalid")
    return tuple(value)


def _safe_relative(value: object, *, allow_dot: bool) -> bool:
    if type(value) is not str or not value or "\\" in value or "\x00" in value:
        return False
    if value == ".":
        return allow_dot
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and str(path) == value and tuple(raw_parts) == path.parts


def _paths_overlap(values: tuple[str, ...]) -> bool:
    normalized = [() if value == "." else PurePosixPath(value).parts for value in values]
    for index, left in enumerate(normalized):
        for right in normalized[index + 1 :]:
            if left == right or left == right[: len(left)] or right == left[: len(right)]:
                return True
    return False


class PinnedTrialProfileCatalog:
    """Read-only exact-match catalog populated only from trusted service config."""

    def __init__(self, profiles: tuple[TrialExecutionProfile, ...]) -> None:
        values: dict[tuple[UUID, int, str], TrialExecutionProfile] = {}
        versions: set[tuple[UUID, int]] = set()
        for profile in profiles:
            key = (
                profile.selector.profile_id,
                profile.selector.profile_version,
                profile.selector.profile_digest,
            )
            version = key[:2]
            if key in values or version in versions:
                raise TrialProfileError("trial profile version is duplicated")
            values[key] = profile
            versions.add(version)
        self._profiles = MappingProxyType(values)

    def read(self, selector: TrialProfileSelector) -> TrialExecutionProfile | None:
        """Return only one exact id/version/digest match."""
        return self._profiles.get(
            (selector.profile_id, selector.profile_version, selector.profile_digest)
        )


class PinnedTrialExecutionCatalog:
    """Exact profile/projection bundles provisioned by trusted service config."""

    def __init__(
        self,
        entries: tuple[tuple[TrialExecutionProfile, TrialExecutionProjection], ...],
    ) -> None:
        values: dict[
            tuple[UUID, int, str, UUID, int, str],
            tuple[TrialExecutionProfile, TrialExecutionProjection],
        ] = {}
        for profile, projection in entries:
            projection.validate_profile(profile)
            key = (
                profile.selector.profile_id,
                profile.selector.profile_version,
                profile.selector.profile_digest,
                projection.selector.projection_id,
                projection.selector.projection_version,
                projection.selector.projection_digest,
            )
            if key in values:
                raise TrialProfileError("trial execution bundle is duplicated")
            values[key] = (profile, projection)
        self._entries = MappingProxyType(values)

    def read(
        self, selector: TrialExecutionSelector
    ) -> tuple[TrialExecutionProfile, TrialExecutionProjection] | None:
        """Resolve only one exact trusted profile/projection pair."""
        return self._entries.get(
            (
                selector.profile.profile_id,
                selector.profile.profile_version,
                selector.profile.profile_digest,
                selector.projection.projection_id,
                selector.projection.projection_version,
                selector.projection.projection_digest,
            )
        )


__all__ = (
    "PinnedTrialProfileCatalog",
    "PinnedTrialExecutionCatalog",
    "TrialExecutionProfile",
    "TrialExecutionProjection",
    "TrialExecutionSelector",
    "TrialMaterialProjection",
    "TrialProfileError",
    "TrialProfileSelector",
    "TrialProjectionSelector",
    "TrialResourceCeilings",
    "TrialSlotProjection",
    "make_trial_execution_profile",
    "make_trial_execution_projection",
    "profile_digest",
    "projection_digest",
    "trial_selector_from_configuration",
)
