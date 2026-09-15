"""Translate CON public validation facts without importing its composition root."""

from uuid import UUID

from app.modules.contributions.api.policies import ContributionPolicyUnavailable
from app.modules.contributions.api.validation import (
    ContributionPolicyValidationPort,
    ContributionPolicyValidationPurpose,
    ContributionPolicyValidationRequest,
)
from app.modules.projects.api.guide_activation import GuideContributionPolicyFacts


class GuideContributionPolicyValidation:
    """Keep new-binding purpose fixed and verify the exact returned identity."""

    def __init__(self, validation: ContributionPolicyValidationPort) -> None:
        self.validation = validation

    async def validate_for_activation(
        self,
        project_id: UUID,
        policy_id: UUID,
        version_id: UUID,
    ) -> GuideContributionPolicyFacts:
        try:
            facts = await self.validation.validate_contribution_policy(
                ContributionPolicyValidationRequest(
                    project_id=project_id,
                    contribution_policy_id=policy_id,
                    contribution_policy_version_id=version_id,
                    purpose=ContributionPolicyValidationPurpose.GUIDE_ACTIVATION,
                )
            )
        except ContributionPolicyUnavailable:
            raise ValueError("contribution policy unavailable") from None
        if (
            facts.project_id != project_id
            or facts.contribution_policy_id != policy_id
            or facts.contribution_policy_version_id != version_id
            or facts.purpose is not ContributionPolicyValidationPurpose.GUIDE_ACTIVATION
        ):
            raise ValueError("contribution policy validation identity mismatch")
        return GuideContributionPolicyFacts(
            project_id=facts.project_id,
            contribution_policy_id=facts.contribution_policy_id,
            contribution_policy_version_id=facts.contribution_policy_version_id,
            purpose="guide_activation",
            version_number=facts.version_number,
            rules_and_definitions_digest=facts.rules_and_definitions_digest,
            adapter_binding_ids=facts.adapter_binding_ids,
        )
