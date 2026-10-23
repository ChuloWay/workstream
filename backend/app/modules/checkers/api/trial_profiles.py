"""Immutable authority for bounded external-checker trial execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from types import MappingProxyType
from typing import Literal, Mapping
from uuid import UUID

from app.modules.checkers.api.external import external_checker_json_hash


Sha256 = str
Identifier = str
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_.-]{0,99}")


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
    permitted_material_roles: tuple[Identifier, ...]
    permitted_operations: tuple[Literal["run"], ...]
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
            or len(set(self.permitted_material_roles)) != len(self.permitted_material_roles)
            or any(
                type(value) is not str or _IDENTIFIER.fullmatch(value) is None
                for value in self.permitted_material_roles
            )
            or profile_digest(self) != self.selector.profile_digest
        ):
            raise TrialProfileError("trial execution profile digest differs")


@dataclass(frozen=True, slots=True)
class TrialSlotProjection:
    """One ordered project-selected operation with an exact material view."""

    slot_id: Identifier
    visible_roles: tuple[Identifier, ...]
    fresh_workspace: bool

    def __post_init__(self) -> None:
        if (
            type(self.slot_id) is not str
            or _IDENTIFIER.fullmatch(self.slot_id) is None
            or not self.visible_roles
            or len(set(self.visible_roles)) != len(self.visible_roles)
            or any(
                type(value) is not str or _IDENTIFIER.fullmatch(value) is None
                for value in self.visible_roles
            )
            or type(self.fresh_workspace) is not bool
        ):
            raise TrialProfileError("trial slot projection is invalid")


@dataclass(frozen=True, slots=True)
class TrialExecutionProjection:
    """Exact project-owned subset carried by hashed checker configuration."""

    selector: TrialProfileSelector
    trial_kind: Identifier
    allowed_material_roles: tuple[Identifier, ...]
    build_context_roles: tuple[Identifier, ...]
    required_slots: tuple[TrialSlotProjection, ...]

    def __post_init__(self) -> None:
        allowed = set(self.allowed_material_roles)
        if (
            type(self.trial_kind) is not str
            or _IDENTIFIER.fullmatch(self.trial_kind) is None
            or not allowed
            or len(allowed) != len(self.allowed_material_roles)
            or any(
                type(value) is not str or _IDENTIFIER.fullmatch(value) is None
                for value in (*self.allowed_material_roles, *self.build_context_roles)
            )
            or not set(self.build_context_roles) <= allowed
            or not self.build_context_roles
            or not self.required_slots
            or len({slot.slot_id for slot in self.required_slots}) != len(self.required_slots)
            or any(not set(slot.visible_roles) <= allowed for slot in self.required_slots)
        ):
            raise TrialProfileError("trial execution projection is invalid")

    def validate_profile(self, profile: TrialExecutionProfile) -> None:
        """Require exact selector and a role/operation subset of trusted authority."""
        if (
            self.selector != profile.selector
            or not set(self.allowed_material_roles) <= set(profile.permitted_material_roles)
            or len(self.required_slots) > profile.limits.maximum_steps
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


def trial_projection_from_configuration(
    configuration: Mapping[str, object],
) -> TrialExecutionProjection | None:
    """Parse the closed trial subset while allowing sibling project/model fields."""
    selector_keys = {
        "trial_profile_id",
        "trial_profile_version",
        "trial_profile_digest",
    }
    present = selector_keys & configuration.keys()
    projection = configuration.get("trial_execution")
    if not present and projection is None:
        return None
    if present != selector_keys or type(projection) is not dict:
        raise TrialProfileError("trial profile selector is incomplete")
    try:
        if set(projection) != {
            "trial_kind",
            "allowed_material_roles",
            "build_context_roles",
            "required_slots",
        }:
            raise TrialProfileError("trial execution projection is invalid")
        slots = projection["required_slots"]
        if type(slots) is not list:
            raise TrialProfileError("trial execution projection is invalid")
        parsed_slots = []
        for slot in slots:
            if type(slot) is not dict or set(slot) != {
                "slot_id",
                "visible_roles",
                "fresh_workspace",
            }:
                raise TrialProfileError("trial slot projection is invalid")
            parsed_slots.append(
                TrialSlotProjection(
                    slot_id=slot["slot_id"],
                    visible_roles=_string_tuple(slot["visible_roles"]),
                    fresh_workspace=slot["fresh_workspace"],
                )
            )
        return TrialExecutionProjection(
            selector=TrialProfileSelector(
                profile_id=UUID(configuration["trial_profile_id"]),
                profile_version=configuration["trial_profile_version"],
                profile_digest=configuration["trial_profile_digest"],
            ),
            trial_kind=projection["trial_kind"],
            allowed_material_roles=_string_tuple(projection["allowed_material_roles"]),
            build_context_roles=_string_tuple(projection["build_context_roles"]),
            required_slots=tuple(parsed_slots),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, TrialProfileError):
            raise
        raise TrialProfileError("trial execution projection is invalid") from exc


def _string_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise TrialProfileError("trial execution projection is invalid")
    return tuple(value)


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


__all__ = (
    "PinnedTrialProfileCatalog",
    "TrialExecutionProfile",
    "TrialExecutionProjection",
    "TrialProfileError",
    "TrialProfileSelector",
    "TrialResourceCeilings",
    "TrialSlotProjection",
    "make_trial_execution_profile",
    "profile_digest",
    "trial_projection_from_configuration",
)
