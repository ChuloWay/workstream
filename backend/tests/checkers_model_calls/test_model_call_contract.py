from __future__ import annotations

from uuid import uuid4

from pydantic import ValidationError
import pytest

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.checkers.api.model_calls import (
    ModelCallConflict,
    ModelCallUsage,
    ModelGenerationSettings,
    ModelProfileProvisioningFacts,
    ModelPaidSlotKey,
    ModelPricing,
    ProjectModelProfileSpec,
    model_usage_cost,
)


def sha(label: str) -> str:
    return canonical_json_hash({"label": label})


def profile_spec() -> ProjectModelProfileSpec:
    return ProjectModelProfileSpec(
        project_id=new_record_id(),
        profile_version=3,
        registry_entry_id=new_record_id(),
        registry_entry_digest=sha("registry"),
        provider="openai_responses",
        api="responses.v1",
        model_snapshot="gpt-example-2026-10-01",
        settings=ModelGenerationSettings(
            reasoning_effort="medium",
            text_verbosity="low",
        ),
        maximum_request_bytes=10_000,
        maximum_output_bytes=2_000,
        maximum_response_bytes=20_000,
        maximum_input_tokens=100,
        maximum_output_tokens=50,
        deadline_ms=60_000,
        pricing=ModelPricing(
            pricing_policy_id=new_record_id(),
            pricing_policy_version=7,
            pricing_policy_digest=sha("pricing"),
            uncached_input_nanodollars_per_token=11,
            cached_input_nanodollars_per_token=2,
            output_nanodollars_per_token=29,
        ),
    )


def test_reservation_uses_worst_input_rate_and_single_output_rate() -> None:
    spec = profile_spec()

    assert spec.maximum_reservation_nanodollars == 100 * 11 + 50 * 29


def test_profile_requires_room_for_canonical_response_evidence() -> None:
    with pytest.raises(ValidationError, match="cannot preserve"):
        ProjectModelProfileSpec.model_validate(
            profile_spec().model_dump()
            | {"maximum_output_bytes": 15_000, "maximum_response_bytes": 20_000}
        )


def test_profile_rejects_unregistered_provider_or_api_aliases() -> None:
    for changes in ({"provider": "openai"}, {"api": "responses"}):
        with pytest.raises(ValidationError, match="provider and API are unsupported"):
            ProjectModelProfileSpec.model_validate(profile_spec().model_dump() | changes)


def test_settlement_prices_cached_input_separately_and_reasoning_once() -> None:
    spec = profile_spec()
    usage = ModelCallUsage(
        input_tokens=80,
        cached_input_tokens=30,
        output_tokens=20,
        reasoning_tokens=17,
    )

    assert model_usage_cost(spec, usage) == 50 * 11 + 30 * 2 + 20 * 29


@pytest.mark.parametrize(
    "usage",
    [
        ModelCallUsage(
            input_tokens=101,
            cached_input_tokens=0,
            output_tokens=1,
            reasoning_tokens=0,
        ),
        ModelCallUsage(
            input_tokens=1,
            cached_input_tokens=0,
            output_tokens=51,
            reasoning_tokens=0,
        ),
    ],
)
def test_settlement_rejects_usage_above_locked_profile(
    usage: ModelCallUsage,
) -> None:
    with pytest.raises(ModelCallConflict, match="exceeds the approved profile"):
        model_usage_cost(profile_spec(), usage)


def test_usage_requires_nested_cached_and_reasoning_classes() -> None:
    with pytest.raises(ValidationError):
        ModelCallUsage(
            input_tokens=1,
            cached_input_tokens=2,
            output_tokens=1,
            reasoning_tokens=0,
        )
    with pytest.raises(ValidationError):
        ModelCallUsage(
            input_tokens=1,
            cached_input_tokens=0,
            output_tokens=1,
            reasoning_tokens=2,
        )


def test_stable_slot_identity_has_no_lease_or_evaluation_generation() -> None:
    spec = profile_spec()
    slot = ModelPaidSlotKey(
        project_id=spec.project_id,
        assignment_id=new_record_id(),
        submission_id=new_record_id(),
        submission_version=2,
        requirement_id="model_output_quality",
        registry_entry_digest=spec.registry_entry_digest,
        configuration_sha256=sha("configuration"),
        profile_id=new_record_id(),
        profile_version=spec.profile_version,
        profile_digest=sha("profile"),
    )

    assert set(type(slot).model_fields) == {
        "project_id",
        "assignment_id",
        "submission_id",
        "submission_version",
        "requirement_id",
        "registry_entry_digest",
        "configuration_sha256",
        "profile_id",
        "profile_version",
        "profile_digest",
        "slot_index",
    }


def test_profile_settings_reject_prompt_or_unapproved_provider_parameters() -> None:
    with pytest.raises(ValidationError):
        ModelGenerationSettings.model_validate(
            {
                "temperature_millionths": 0,
                "reasoning_effort": "medium",
                "text_verbosity": "low",
                "prompt": "must not be retained in an operator profile",
            }
        )


def test_caller_operation_key_may_be_uuid4_and_record_id_is_server_output() -> None:
    spec = profile_spec()
    facts = ModelProfileProvisioningFacts(
        operation_id=uuid4(),
        actor_profile_id=new_record_id(),
        spec=spec,
        profile_digest=canonical_json_hash(spec.model_dump(mode="json")),
    )

    assert facts.operation_id.version == 4
    assert "profile_id" not in type(facts).model_fields
