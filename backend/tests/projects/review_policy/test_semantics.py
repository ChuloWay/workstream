"""Strict configuration and exact historical/current policy hash contracts."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.hashing import canonical_json_hash
from app.modules.projects.policy_lineage import (
    ReviewPolicySemantics,
    policy_digest,
    require_complete_policy,
    validate_review_mode,
)
from app.modules.projects.schemas import ReviewPolicyInput
from test_project_policy_mutations import _review_payload


@pytest.mark.parametrize("value", ["true", "false", "", 0, 1, 2, 0.0, 1.0, None, [], {}])
def test_policy_input_rejects_non_boolean(value):
    values = _review_payload().model_dump()
    with pytest.raises(ValidationError, match="human_review_required"):
        ReviewPolicyInput.model_validate({**values, "human_review_required": value})


@pytest.mark.parametrize("value", [True, False])
def test_policy_input_retains_presence_and_boolean(value):
    omitted = _review_payload()
    assert omitted.human_review_required is True
    assert "human_review_required" not in omitted.model_fields_set
    explicit = ReviewPolicyInput.model_validate(
        {**omitted.model_dump(), "human_review_required": value}
    )
    assert explicit.human_review_required is value
    assert "human_review_required" in explicit.model_fields_set


def test_v1_exact_hash_and_v2_modes_are_distinct():
    values = _review_payload().model_dump(exclude={"human_review_required"})
    legacy_hash = canonical_json_hash(
        {"domain": "workstream.review_policy.v1", "semantics": values}
    )
    current = ReviewPolicySemantics.model_validate(values)
    assert policy_digest("review", current, review_semantics_format="v1") == legacy_hash
    require_complete_policy(
        kind="review",
        status="complete",
        policy_hash=legacy_hash,
        semantic_values=values,
        review_semantics_format="v1",
    )
    false = ReviewPolicySemantics.model_validate({**values, "human_review_required": False})
    assert len({legacy_hash, policy_digest("review", current), policy_digest("review", false)}) == 3
    for semantics in (current, false):
        require_complete_policy(
            kind="review",
            status="complete",
            policy_hash=policy_digest("review", semantics),
            semantic_values=semantics.model_dump(),
            review_semantics_format="v2",
        )


@pytest.mark.parametrize("format,value", [("v1", False), ("v3", True), ("v2", None), ("v2", 1)])
def test_mode_rejects_invalid_format_or_legacy_false(format, value):
    with pytest.raises(ValueError):
        validate_review_mode(value, format)


def test_new_hash_requires_explicit_mode_and_cannot_validate_legacy_digest():
    semantics = ReviewPolicySemantics.model_validate(_review_payload().model_dump())
    with pytest.raises(ValueError, match="incomplete"):
        require_complete_policy(
            kind="review",
            status="complete",
            policy_hash=policy_digest("review", semantics),
            semantic_values=semantics.model_dump(exclude={"human_review_required"}),
            review_semantics_format="v2",
        )
    with pytest.raises(ValueError, match="digest mismatch"):
        require_complete_policy(
            kind="review",
            status="complete",
            policy_hash=policy_digest("review", semantics, review_semantics_format="v1"),
            semantic_values=semantics.model_dump(),
            review_semantics_format="v2",
        )
    with pytest.raises(ValueError, match="incomplete"):
        require_complete_policy(
            kind="review",
            status="legacy_incomplete",
            policy_hash=policy_digest("review", semantics, review_semantics_format="v1"),
            semantic_values=semantics.model_dump(),
            review_semantics_format="v1",
        )


def test_future_activation_owners_preserve_unavailable_mode_contract():
    root = Path(__file__).resolve().parents[4]
    for path in (
        ".commitrail/initiatives/WS-ARCH-001/planning/chunks/WS-ARCH-001-CP07-project-guide-policy-binding.md",
        ".commitrail/initiatives/WS-AUTH-001/planning/chunks/WS-AUTH-001-12H-guide-activation.md",
    ):
        content = (root / path).read_text()
        assert "human_review_required=false" in content
        assert "FinalAcceptance/CON" in content
        assert "never silently" in content
