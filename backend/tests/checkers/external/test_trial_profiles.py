from dataclasses import replace
from uuid import UUID

import pytest

from app.modules.checkers.api.trial_profiles import (
    PinnedTrialProfileCatalog,
    TrialExecutionProjection,
    TrialProfileError,
    TrialProfileSelector,
    TrialResourceCeilings,
    TrialSlotProjection,
    make_trial_execution_profile,
    trial_projection_from_configuration,
)


PROFILE_ID = UUID("018f6f49-66b8-7d2a-bf4d-0e2eeaa00001")


def digest(character: str) -> str:
    return "sha256:" + character * 64


def profile():
    return make_trial_execution_profile(
        schema_version="workstream.trial_execution_profile.v1",
        selector=TrialProfileSelector(PROFILE_ID, 1, digest("0")),
        runtime="runsc",
        isolation_mode="gvisor",
        outer_host_uds="open",
        child_host_uds="none",
        outer_runtime_config_digest=digest("1"),
        child_runtime_config_digest=digest("2"),
        engine_identity_digest=digest("3"),
        platform="linux/amd64",
        platform_identity_digest=digest("4"),
        builder_image_digest=digest("5"),
        offline_cache_digest=digest("6"),
        approved_base_digests=(digest("7"),),
        permitted_material_roles=("candidate_source", "verification"),
        permitted_operations=("run",),
        builder_capabilities=("CHOWN", "DAC_OVERRIDE", "FOWNER", "SYS_CHROOT"),
        child_capabilities=(),
        child_network="none",
        child_runs_as_non_root=True,
        limits=TrialResourceCeilings(
            maximum_total_timeout_ms=30_000,
            maximum_build_timeout_ms=10_000,
            maximum_step_timeout_ms=5_000,
            maximum_steps=3,
            maximum_cpu_quota_millis=1_000,
            maximum_cpu_time_ms=20_000,
            maximum_wall_time_overrun_ms=100,
            maximum_cpu_time_overrun_ms=250,
            maximum_memory_bytes=128 * 1024 * 1024,
            maximum_swap_bytes=128 * 1024 * 1024,
            maximum_memory_overrun_bytes=1024 * 1024,
            maximum_pids=32,
            maximum_pids_overrun=2,
            maximum_disk_bytes=128 * 1024 * 1024,
            maximum_disk_overrun_bytes=1024 * 1024,
            maximum_entries=10_000,
            maximum_entries_overrun=16,
            maximum_step_output_bytes=64 * 1024,
            maximum_observation_bytes=256 * 1024,
            maximum_receipt_bytes=512 * 1024,
            maximum_frame_bytes=256 * 1024,
            maximum_response_bytes=16 * 1024,
        ),
    )


def configuration(selected=None) -> dict[str, object]:
    selected = selected or profile()
    return {
        "check": "check_a",
        "model_profile_id": "018f6f49-66b8-7d2a-bf4d-0e2eeaa00002",
        "model_profile_version": 1,
        "model_profile_digest": digest("8"),
        "trial_profile_id": str(selected.selector.profile_id),
        "trial_profile_version": selected.selector.profile_version,
        "trial_profile_digest": selected.selector.profile_digest,
        "trial_execution": {
            "trial_kind": "generic_build_run",
            "allowed_material_roles": ["candidate_source", "verification"],
            "build_context_roles": ["candidate_source"],
            "required_slots": [
                {
                    "slot_id": "slot_a",
                    "visible_roles": ["candidate_source"],
                    "fresh_workspace": True,
                }
            ],
        },
    }


def test_profile_digest_is_derived_and_catalog_requires_exact_selector():
    selected = profile()
    assert selected.selector.profile_digest != digest("0")
    assert profile() == selected
    catalog = PinnedTrialProfileCatalog((selected,))
    assert catalog.read(selected.selector) == selected
    substituted = replace(selected.selector, profile_digest=digest("f"))
    assert catalog.read(substituted) is None
    with pytest.raises(TrialProfileError, match="duplicated"):
        PinnedTrialProfileCatalog((selected, selected))


def test_runtime_split_and_no_swap_are_closed_trusted_profile_rules():
    selected = profile()
    with pytest.raises(TrialProfileError, match="invalid"):
        replace(selected, child_host_uds="open")
    with pytest.raises(TrialProfileError, match="swap"):
        replace(
            selected.limits,
            maximum_swap_bytes=selected.limits.maximum_memory_bytes * 2,
        )
    with pytest.raises(TrialProfileError, match="invalid"):
        replace(selected, child_capabilities=("SYS_ADMIN",))


def test_locked_configuration_parses_trial_and_model_selectors_independently():
    selected = profile()
    projection = trial_projection_from_configuration(configuration(selected))
    assert projection is not None
    assert projection.selector == selected.selector
    assert projection.required_slots[0].visible_roles == ("candidate_source",)
    projection.validate_profile(selected)

    without_trial = {
        key: value for key, value in configuration(selected).items() if not key.startswith("trial_")
    }
    assert trial_projection_from_configuration(without_trial) is None


@pytest.mark.parametrize(
    "mutation",
    (
        lambda value: value.pop("trial_profile_digest"),
        lambda value: value["trial_execution"].update(network_mode="host"),
        lambda value: value["trial_execution"]["required_slots"][0].update(
            visible_roles=["protected_role"]
        ),
        lambda value: value.update(trial_profile_version=True),
    ),
)
def test_partial_unknown_foreign_or_wrong_typed_projection_is_rejected(mutation):
    value = configuration()
    mutation(value)
    with pytest.raises(TrialProfileError):
        trial_projection_from_configuration(value)


def test_projection_cannot_exceed_trusted_roles_or_step_count():
    selected = profile()
    foreign_role = TrialExecutionProjection(
        selector=selected.selector,
        trial_kind="generic_build_run",
        allowed_material_roles=("protected_role",),
        build_context_roles=("protected_role",),
        required_slots=(TrialSlotProjection("slot_a", ("protected_role",), True),),
    )
    with pytest.raises(TrialProfileError, match="exceeds"):
        foreign_role.validate_profile(selected)

    too_many = replace(
        foreign_role,
        allowed_material_roles=("candidate_source",),
        build_context_roles=("candidate_source",),
        required_slots=tuple(
            TrialSlotProjection(f"slot_{index}", ("candidate_source",), True)
            for index in range(selected.limits.maximum_steps + 1)
        ),
    )
    with pytest.raises(TrialProfileError, match="exceeds"):
        too_many.validate_profile(selected)
