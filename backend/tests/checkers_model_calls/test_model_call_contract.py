from __future__ import annotations

from uuid import uuid4

from pydantic import ValidationError
import pytest

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.model_usage.api import (
    ModelCallConflict,
    ModelCallUsage,
    ModelGenerationSettings,
    ModelProfileProvisioningFacts,
    ModelPaidSlotKey,
    ModelPricing,
    ProjectModelBudgetConfigurationSpec,
    ProjectModelProfileSpec,
    SetupModelUsageSlotKey,
    model_usage_cost,
)


def sha(label: str) -> str:
    return canonical_json_hash({"label": label})


def profile_spec() -> ProjectModelProfileSpec:
    return ProjectModelProfileSpec(
        project_id=new_record_id(),
        profile_version=3,
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
        maximum_calls=1,
        maximum_total_request_bytes=10_000,
        maximum_total_response_bytes=20_000,
        maximum_total_input_tokens=100,
        maximum_total_output_tokens=50,
        allowed_tools=(),
        maximum_tool_calls=0,
        maximum_tool_output_bytes=0,
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


def test_profile_requires_finite_canonical_run_and_tool_envelopes() -> None:
    multi = ProjectModelProfileSpec.model_validate(
        profile_spec().model_dump()
        | {
            "maximum_calls": 3,
            "maximum_total_request_bytes": 30_000,
            "maximum_total_response_bytes": 60_000,
            "maximum_total_input_tokens": 300,
            "maximum_total_output_tokens": 150,
            "allowed_tools": ("execution_receipt", "read_material"),
            "maximum_tool_calls": 8,
            "maximum_tool_output_bytes": 100_000,
        }
    )
    assert multi.maximum_reservation_nanodollars == 300 * 11 + 150 * 29
    with pytest.raises(ValidationError, match="canonical"):
        ProjectModelProfileSpec.model_validate(
            multi.model_dump() | {"allowed_tools": ("read_material", "execution_receipt")}
        )
    with pytest.raises(ValidationError, match="run totals"):
        ProjectModelProfileSpec.model_validate(
            multi.model_dump() | {"maximum_total_input_tokens": 301}
        )


def test_budget_requires_explicit_reconciled_remaining_allowance() -> None:
    with pytest.raises(ValidationError, match="reconciled authorization"):
        ProjectModelBudgetConfigurationSpec(
            project_id=new_record_id(),
            configuration_version=1,
            authorized_total_nanodollars=10_000_000_000,
            externally_reconciled_prior_spend_nanodollars=2_000_000_000,
            lifetime_limit_nanodollars=9_000_000_000,
        )


def test_profile_is_provider_neutral_but_rejects_unbounded_identifiers() -> None:
    for changes in (
        {"provider": "openai", "api": "responses"},
        {"provider": "openrouter", "api": "chat_completions"},
    ):
        assert ProjectModelProfileSpec.model_validate(
            profile_spec().model_dump() | changes
        ).provider == changes["provider"]
    with pytest.raises(ValidationError):
        ProjectModelProfileSpec.model_validate(
            profile_spec().model_dump() | {"provider": "https://bad host"}
        )


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
        registry_entry_digest=sha("registry"),
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


def test_setup_slot_binds_attempt_generation_runtime_profile_and_call_order() -> None:
    key = SetupModelUsageSlotKey(
        compilation_attempt_id=new_record_id(),
        project_id=new_record_id(),
        guide_id=new_record_id(),
        source_snapshot_id=new_record_id(),
        setup_run_id=new_record_id(),
        setup_generation=4,
        runtime_configuration_hash=sha("setup-runtime"),
        profile_id=new_record_id(),
        profile_version=2,
        profile_digest=sha("setup-profile"),
        phase="review",
        call_index=3,
    )

    assert key.digest == canonical_json_hash(key.model_dump(mode="json"))
    assert "checker_run_id" not in type(key).model_fields


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
