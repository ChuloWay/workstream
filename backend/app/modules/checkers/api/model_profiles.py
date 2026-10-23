"""Reserved external-checker configuration for exact project model profiles."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from pydantic import JsonValue, ValidationError

from app.modules.checkers.api.external import (
    ExternalCheckerPhase,
    ExternalCheckerRegistryEntry,
)
from app.modules.model_usage.api import (
    ModelCallUnavailable,
    ModelProfileReaderPort,
    ModelProfileSelector,
)


MODEL_PROFILE_CONFIGURATION_KEYS = frozenset(
    {"model_profile_id", "model_profile_version", "model_profile_digest"}
)


class ModelProfileConfigurationError(ValueError):
    """Reject partial, phase-substituted or unavailable profile selection."""


def configured_model_profile_selector(
    configuration: Mapping[str, JsonValue],
    *,
    stage: ExternalCheckerPhase,
) -> ModelProfileSelector | None:
    """Decode the reserved all-or-none selector without affecting ordinary images."""
    present = MODEL_PROFILE_CONFIGURATION_KEYS.intersection(configuration)
    if not present:
        return None
    if present != MODEL_PROFILE_CONFIGURATION_KEYS or stage != "post_submit":
        raise ModelProfileConfigurationError("model profile configuration is invalid")
    profile_id = configuration["model_profile_id"]
    profile_version = configuration["model_profile_version"]
    profile_digest = configuration["model_profile_digest"]
    if (
        type(profile_id) is not str
        or type(profile_version) is not int
        or type(profile_digest) is not str
    ):
        raise ModelProfileConfigurationError("model profile configuration is invalid")
    try:
        canonical_profile_id = UUID(profile_id)
        if str(canonical_profile_id) != profile_id:
            raise ValueError("model profile ID is not canonical")
        return ModelProfileSelector(
            profile_id=canonical_profile_id,
            profile_version=profile_version,
            profile_digest=profile_digest,
        )
    except (ValueError, ValidationError) as exc:
        raise ModelProfileConfigurationError("model profile configuration is invalid") from exc


async def require_model_profile_configuration(
    configuration: Mapping[str, JsonValue],
    *,
    stage: ExternalCheckerPhase,
    project_id: UUID,
    registry: ExternalCheckerRegistryEntry,
    profiles: ModelProfileReaderPort | None,
) -> ModelProfileSelector | None:
    """Resolve a model-enabled binding to one exact immutable approved profile."""
    selector = configured_model_profile_selector(configuration, stage=stage)
    if selector is None:
        return None
    if profiles is None:
        raise ModelProfileConfigurationError("model profile reader is unavailable")
    try:
        profile = await profiles.read_exact(
            selector,
            project_id=project_id,
        )
    except ModelCallUnavailable as exc:
        # Registry/persistence details remain concealed at the policy boundary.
        raise ModelProfileConfigurationError("model profile is unavailable") from exc
    if (
        profile.selector != selector
        or profile.spec.project_id != project_id
    ):
        raise ModelProfileConfigurationError("model profile is unavailable")
    return selector


__all__ = (
    "MODEL_PROFILE_CONFIGURATION_KEYS",
    "ModelProfileConfigurationError",
    "configured_model_profile_selector",
    "require_model_profile_configuration",
)
