"""Reject incomplete or substituted activation commitments before owner access."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.adapters.projects.contribution_validation import GuideContributionPolicyValidation
from app.modules.contributions.api.validation import ContributionPolicyValidationPurpose
from app.modules.projects.api.guide_activation import (
    GuideActivationCommand,
    GuideActivationReceipt,
    GuideContributionPolicyFacts,
)
from app.modules.projects.api.guide_proposals import (
    GuideProposalTarget,
    GuideProposalApprovalReceipt,
)
from app.modules.projects.api.post_policy import PostPolicyTarget
from tests.projects.guide_compilation.proposals.contract_support import HASH, target_values


def command_values():
    proposal = GuideProposalTarget(**target_values())
    upstream = GuideProposalApprovalReceipt(
        operation_id=new_record_id(),
        target_digest=proposal.digest,
        artifact_policy_id=proposal.artifact_policy_id,
        effective_policy_id=new_record_id(),
        effective_policy_hash=HASH,
        pre_submit_policy_id=new_record_id(),
        pre_submit_bundle_hash=HASH,
        effective_pre_submit_plan_hash=HASH,
        acknowledged_warning_hashes=(),
    )
    target = PostPolicyTarget(
        proposal=proposal,
        upstream=upstream,
        upstream_output_digest=canonical_json_hash(upstream.model_dump(mode="json")),
        policy_id=new_record_id(),
        projection_operation_id=new_record_id(),
        policy_hash=HASH,
    )
    return dict(
        target=target,
        post_approval_operation_id=uuid4(),
        post_approval_output_digest=HASH,
        guide_mutation_generation=1,
        review=dict(policy_id=uuid4(), generation=1, policy_hash=HASH),
        revision=dict(policy_id=uuid4(), generation=1, policy_hash=HASH),
        contribution_policy_id=uuid4(),
        contribution_policy_version_id=uuid4(),
        expected_previous_active_guide_id=None,
        expected_previous_active_guide_generation=None,
        idempotency_key=uuid4(),
    )


@pytest.mark.parametrize("field", list(GuideActivationCommand.model_fields))
def test_every_activation_selector_must_be_explicit(field):
    values = command_values()
    del values[field]
    with pytest.raises(ValidationError):
        GuideActivationCommand(**values)


@pytest.mark.parametrize(
    "field,value",
    [
        ("guide_mutation_generation", 0),
        ("guide_mutation_generation", True),
        ("post_approval_output_digest", "bad"),
        ("expected_previous_active_guide_generation", 1),
        ("extra_field", "unsupported"),
    ],
)
def test_invalid_activation_values_reject(field, value):
    values = command_values()
    values[field] = value
    with pytest.raises(ValidationError):
        GuideActivationCommand(**values)


def test_cannot_supersede_self_but_can_name_retained_null_generation():
    values = command_values()
    values["expected_previous_active_guide_id"] = values["target"].proposal.guide_id
    with pytest.raises(ValidationError, match="own guide"):
        GuideActivationCommand(**values)
    values["expected_previous_active_guide_id"] = uuid4()
    assert GuideActivationCommand(**values).expected_previous_active_guide_generation is None


def receipt_values():
    command = GuideActivationCommand(**command_values())
    return dict(
        operation_id=new_record_id(),
        command=command,
        activation_generation=2,
        effective_at=datetime.now(UTC),
        prior_project_status="draft",
        contribution=GuideContributionPolicyFacts(
            project_id=command.target.proposal.project_id,
            contribution_policy_id=command.contribution_policy_id,
            contribution_policy_version_id=command.contribution_policy_version_id,
            purpose="guide_activation",
            version_number=1,
            rules_and_definitions_digest=HASH,
            adapter_binding_ids=(),
        ),
    )


@pytest.mark.parametrize(
    "field", ["project_id", "contribution_policy_id", "contribution_policy_version_id"]
)
def test_receipt_rejects_foreign_contribution_binding(field):
    values = receipt_values()
    values["contribution"] = values["contribution"].model_copy(update={field: uuid4()})
    with pytest.raises(ValidationError, match="binding mismatch"):
        GuideActivationReceipt(**values)


@pytest.mark.parametrize(
    "field,value", [("activation_generation", 3), ("effective_at", datetime(2026, 1, 1))]
)
def test_receipt_rejects_wrong_generation_or_naive_timestamp(field, value):
    values = receipt_values()
    values[field] = value
    with pytest.raises(ValidationError, match="binding mismatch"):
        GuideActivationReceipt(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mismatch",
    [None, "project_id", "contribution_policy_id", "contribution_policy_version_id", "purpose"],
)
async def test_con_bridge_requires_exact_new_binding_purpose(mismatch):
    values = receipt_values()["contribution"]
    facts = SimpleNamespace(**values.model_dump(), purpose_unused=None)
    facts.purpose = ContributionPolicyValidationPurpose.GUIDE_ACTIVATION
    if mismatch:
        setattr(
            facts,
            mismatch,
            ContributionPolicyValidationPurpose.REVISION_ADOPTION
            if mismatch == "purpose"
            else uuid4(),
        )
    port = SimpleNamespace(validate_contribution_policy=AsyncMock(return_value=facts))
    bridge = GuideContributionPolicyValidation(port)
    if mismatch:
        with pytest.raises(ValueError, match="identity mismatch"):
            await bridge.validate_for_activation(
                values.project_id,
                values.contribution_policy_id,
                values.contribution_policy_version_id,
            )
    else:
        assert (
            await bridge.validate_for_activation(
                values.project_id,
                values.contribution_policy_id,
                values.contribution_policy_version_id,
            )
            == values
        )
    request = port.validate_contribution_policy.await_args.args[0]
    assert request.purpose is ContributionPolicyValidationPurpose.GUIDE_ACTIVATION
    assert request.project_id == values.project_id
