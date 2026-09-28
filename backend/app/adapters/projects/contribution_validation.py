"""Translate CON public validation facts without importing its composition root."""

from uuid import UUID
from app.modules.contributions.api.published_selection import PublishedContributionPolicyPort
from app.modules.projects.api.guide_activation_context import GuidePublishedContributionSelection

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


class GuideContributionPolicyDiscovery:
    """Translate only published CON identities into the manager context contract."""

    def __init__(self, discovery: PublishedContributionPolicyPort) -> None:
        self.discovery = discovery

    async def published_selection(self, project_id: UUID) -> GuidePublishedContributionSelection | None:
        try:
            value = await self.discovery.published_selection(project_id)
        except ContributionPolicyUnavailable:
            raise ValueError("contribution selector unavailable") from None
        if value is None:
            return None
        if value.project_id != project_id:
            raise ValueError("contribution selector project mismatch")
        return GuidePublishedContributionSelection(
            contribution_policy_id=value.contribution_policy_id,
            contribution_policy_version_id=value.contribution_policy_version_id,
        )
