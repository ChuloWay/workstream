"""PROJECT-owned composition adapters."""

from collections.abc import Callable
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.interfaces.artifact_operations import GuideSufficiencyMaterialPort
from app.interfaces.project_agents import ProjectGuideAgentRuntime
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.modules.checkers.api.pre_submit_catalogue import PreSubmissionCapabilityProjection
from app.modules.checkers.api.post_submit_catalogue import PostSubmitCatalogue
from app.modules.authorization.api import (
    GuideSufficiencyProjectionAuthorizationPort,
    ArtifactPolicyProjectionAuthorizationPort,
    SetupFinalizationAuthorizationPort,
)
from app.modules.projects.guide_compilation.live import RequestAuthority
from app.modules.projects.guide_compilation.orchestrator import GuideCompilationAuthorizationContext
from app.modules.projects.api.guide_compilation import ProjectGuideCompilationDeliveryPort
from app.modules.projects.guide_compilation.live import LiveGuideCompilationCoordinator
from app.modules.projects.guide_compilation.orchestrator import (
    project_guide_compilation_execution_port,
)
from app.modules.projects.guide_compilation.projections import GuideCompilationProjectionService

from app.modules.projects.api import (
    ProjectContributionPolicyEligibilityPort,
    ProjectLockedPolicyContextPort,
)
from app.modules.projects.contribution_policy import ProjectContributionPolicyEligibility
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository


def project_locked_policy_context_port(
    session: AsyncSession,
) -> ProjectLockedPolicyContextPort:
    """Bind the public PROJECT locked-policy port to its repository."""
    return ProjectLockedPolicyRepository(session)


def project_contribution_policy_eligibility_port(
    session: AsyncSession,
) -> ProjectContributionPolicyEligibilityPort:
    """Construct the PROJECTS-owned policy eligibility port."""
    return ProjectContributionPolicyEligibility(session)


def project_guide_compilation_delivery_port(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    material_factory: Callable[[AsyncSession], GuideSufficiencyMaterialPort],
    pre_capabilities: PreSubmissionCapabilityProjection,
    post_capabilities: PostSubmitCatalogue,
    request_authority: RequestAuthority,
    execution_authority: GuideCompilationAuthorizationContext,
    configuration_factory: Callable[[], ProjectGuideRuntimeConfiguration],
    runtime_factory: Callable[[ProjectGuideRuntimeConfiguration], ProjectGuideAgentRuntime],
    sufficiency_authorization_factory: Callable[
        [AsyncSession], GuideSufficiencyProjectionAuthorizationPort
    ],
    policy_authorization_factory: Callable[
        [AsyncSession], ArtifactPolicyProjectionAuthorizationPort
    ],
    finalization_authorization_factory: Callable[
        [AsyncSession], SetupFinalizationAuthorizationPort
    ],
) -> ProjectGuideCompilationDeliveryPort:
    """Compose the existing PROJECTS owners from explicit external capability ports."""
    return LiveGuideCompilationCoordinator(
        session_factory,
        material_factory=material_factory,
        pre_capabilities=pre_capabilities,
        post_capabilities=post_capabilities,
        request_authority=request_authority,
        configuration_factory=configuration_factory,
        execution=project_guide_compilation_execution_port(
            session_factory,
            material_factory=material_factory,
            pre_submission_capabilities=pre_capabilities,
            post_submission_capabilities=post_capabilities,
            authorization_context=execution_authority,
            runtime_factory=runtime_factory,
        ),
        projections=GuideCompilationProjectionService(
            session_factory,
            material_factory=material_factory,
            sufficiency_authorization_factory=sufficiency_authorization_factory,
            policy_authorization_factory=policy_authorization_factory,
        ),
        finalization_authorization_factory=finalization_authorization_factory,
    )
