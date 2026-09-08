"""Authorization application adapters and same-owner composition."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.auth.adapter_bindings import CompensationAdapterBindingAuthorization
from app.modules.authorization.adapter_binding_authorization import (
    AdapterBindingAuthorizationAdapter,
)
from app.modules.authorization.project_setup_finalization import SetupFinalizationAuthorization
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import AuthorizationContext
from app.modules.authorization.guide_compilation_projections import (
    ArtifactPolicyProjectionAuthorization,
    GuideSufficiencyProjectionAuthorization,
)


def setup_finalization_authorization(session: AsyncSession) -> SetupFinalizationAuthorization:
    """Compose explicit hidden finalization authority in the caller session."""
    return SetupFinalizationAuthorization(session)


def guide_sufficiency_projection_authorization(
    session: AsyncSession,
) -> GuideSufficiencyProjectionAuthorization:
    """Compose request-local fixed-service sufficiency projection authority."""
    return GuideSufficiencyProjectionAuthorization(session)


def artifact_policy_projection_authorization(
    session: AsyncSession,
) -> ArtifactPolicyProjectionAuthorization:
    """Compose request-local fixed-service artifact-policy projection authority."""
    return ArtifactPolicyProjectionAuthorization(session)


def compensation_adapter_binding_authorization(
    session: AsyncSession,
    context: AuthorizationContext,
) -> CompensationAdapterBindingAuthorization:
    """Compose one request-local AUTH adapter through the public CON port."""
    repository = AdminAuthorizationRepository(session)
    kernel = AuthorizationService(session, context, admin_repository=repository)
    prepared = PreparedAuthorizationService(session, context, kernel, repository)
    return CompensationAdapterBindingAuthorization(
        AdapterBindingAuthorizationAdapter(kernel, prepared)
    )


__all__ = (
    "CompensationAdapterBindingAuthorization",
    "compensation_adapter_binding_authorization",
    "artifact_policy_projection_authorization",
    "guide_sufficiency_projection_authorization",
    "setup_finalization_authorization",
)
