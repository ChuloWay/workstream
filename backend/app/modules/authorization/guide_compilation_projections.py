"""Purpose-specific fixed-service adapters for compilation projections."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager, asynccontextmanager
from copy import Error as CopyError
from typing import NoReturn
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.api import (
    ArtifactPolicyProjectionFacts,
    AuthorizationDenied,
    AuthorizationUnavailable,
    GuideSufficiencyProjectionFacts,
    PreparedAuthorizationInvalid,
    PreparedArtifactPolicyProjection,
    PreparedGuideSufficiencyProjection,
    ProjectGuideProjectionAuthorityReceipt,
    ProjectGuideProjectionIdentity,
    ProjectGuideProjectionLocator,
    projection_preparation_identity,
)
from app.modules.authorization.domain.guide_compilation_projections import (
    ProjectionComponent,
    projection_action,
    projection_prepare_context,
    projection_resource_context,
    projection_resource_digest,
)
from app.modules.authorization.prepared import (
    FixedServicePreparedAuthorization,
    PreparedAuthorizationHandle,
    fixed_service_prepared_authorization,
)
from app.modules.authorization.runtime import (
    AuthorizationEvidenceUnavailable,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)

class _PreparedProjection:
    """Nominal non-serializable view over one existing PREP handle."""

    __slots__ = (
        "_component",
        "_custody",
        "_handle",
        "_input",
        "_actor_profile_id",
        "_identity_link_id",
        "_identity",
        "_locator",
    )

    def __init__(
        self,
        component: ProjectionComponent,
        custody: FixedServicePreparedAuthorization,
        handle: PreparedAuthorizationHandle,
        caller_input: PreparedAuthorizationInput,
        actor_profile_id: UUID,
        identity_link_id: UUID,
        locator: ProjectGuideProjectionLocator,
    ) -> None:
        """Bind one public projection view to its opaque PREP custody."""
        self._component = component
        self._custody = custody
        self._handle = handle
        self._input = caller_input
        self._actor_profile_id = actor_profile_id
        self._identity_link_id = identity_link_id
        self._identity: ProjectGuideProjectionIdentity | None = None
        self._locator = locator

    def identity(
        self, *, operation_id: UUID, correlation_id: UUID, output_id: UUID
    ) -> ProjectGuideProjectionIdentity:
        """Bind owner-selected UUIDv7 values to the prepared service principal."""
        identity = ProjectGuideProjectionIdentity(
            operation_id=operation_id,
            correlation_id=correlation_id,
            output_id=output_id,
            actor_profile_id=self._actor_profile_id,
            identity_link_id=self._identity_link_id,
        )
        if self._identity is not None and self._identity != identity:
            raise PreparedAuthorizationInvalid("prepared projection identity changed")
        self._identity = identity
        return identity

    def __copy__(self) -> NoReturn:
        """Reject copying of process-local projection authority."""
        raise CopyError("prepared projection authority cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        """Reject deep copying of process-local projection authority."""
        raise CopyError("prepared projection authority cannot be copied")

    def __reduce__(self) -> NoReturn:
        """Reject serialization of process-local projection authority."""
        raise TypeError("prepared projection authority cannot be serialized")

    def _resource(self, facts):
        """Build and validate the exact final projection resource."""
        try:
            if self._identity is None:
                raise ValueError("projection identity has not been bound")
            resource = projection_resource_context(self._component, self._identity, facts)
        except (TypeError, ValueError) as exc:
            raise PreparedAuthorizationInvalid("prepared projection authority is invalid") from exc
        if (
            resource.scope_project_id != self._locator.project_id
            or UUID(str(resource.projection_facts["attempt_id"])) != self._locator.attempt_id
        ):
            raise PreparedAuthorizationInvalid("prepared projection authority is invalid")
        return resource

    async def consume_new(
        self, facts: GuideSufficiencyProjectionFacts | ArtifactPolicyProjectionFacts
    ) -> ProjectGuideProjectionAuthorityReceipt:
        """Consume new projection authority once and return exact evidence custody."""
        resource = self._resource(facts)
        try:
            decision = await self._custody.service.consume(
                self._handle,
                projection_action(self._component),
                self._input,
                resource,
            )
        except PreparedAuthorizationHandleInvalid as exc:
            raise PreparedAuthorizationInvalid("prepared projection authority is invalid") from exc
        except PreparedAuthorizationUnsupported as exc:
            raise AuthorizationDenied("projection authority denied") from exc
        except AuthorizationEvidenceUnavailable as exc:
            raise AuthorizationUnavailable("projection authority unavailable") from exc
        return ProjectGuideProjectionAuthorityReceipt(
            decision_event_id=decision.decision_id,
            actor_profile_id=self._actor_profile_id,
            identity_link_id=self._identity_link_id,
            service_identity="workstream.project.setup",
            resource_context_digest=projection_resource_digest(resource),
        )

    async def validate_replay(
        self,
        facts: GuideSufficiencyProjectionFacts | ArtifactPolicyProjectionFacts,
        stored_decision_id: UUID,
    ) -> None:
        """Freshly validate the original stored decision for replay."""
        resource = self._resource(facts)
        try:
            await self._custody.service.validate_replay(
                self._handle,
                projection_action(self._component),
                self._input,
                resource,
                stored_decision_id,
            )
        except PreparedAuthorizationHandleInvalid as exc:
            raise PreparedAuthorizationInvalid("prepared projection authority is invalid") from exc
        except PreparedAuthorizationUnsupported as exc:
            raise AuthorizationDenied("projection authority denied") from exc
        except AuthorizationEvidenceUnavailable as exc:
            raise AuthorizationUnavailable("projection authority unavailable") from exc


class _ProjectionAuthorization:
    """Shared request-local preparation for the two closed projection ports."""

    def __init__(self, session: AsyncSession, component: ProjectionComponent) -> None:
        """Bind the adapter to its caller-owned session and component."""
        self._session = session
        self._component = component

    @asynccontextmanager
    async def _prepare(self, locator: ProjectGuideProjectionLocator):
        """Prepare and close one exact fixed-service capability."""
        request_id, correlation_id = projection_preparation_identity(
            attempt_id=locator.attempt_id, component=self._component
        )
        manager = fixed_service_prepared_authorization(
            self._session,
            service_identity=ServiceIdentity.PROJECT_SETUP,
            request_id=request_id,
            correlation_id=correlation_id,
        )
        try:
            custody = await manager.__aenter__()
        except PreparedAuthorizationHandleInvalid as exc:
            raise PreparedAuthorizationInvalid("prepared projection authority is invalid") from exc
        except PreparedAuthorizationUnsupported as exc:
            raise AuthorizationDenied("projection authority denied") from exc
        except AuthorizationEvidenceUnavailable as exc:
            raise AuthorizationUnavailable("projection authority unavailable") from exc
        try:
            try:
                prepare = projection_prepare_context(
                    self._component,
                    locator,
                    custody.actor_profile_id,
                    custody.identity_link_id,
                )
                caller_input = PreparedAuthorizationInput(
                    idempotency_key=request_id,
                    request_value=prepare.model_dump(mode="json"),
                )
                handle = await custody.service.prepare(
                    projection_action(self._component),
                    caller_input,
                    PreparedAuthorityScope(
                        kind=PreparedAuthorityScopeKind.PROJECT,
                        project_id=locator.project_id,
                    ),
                )
            except PreparedAuthorizationHandleInvalid as exc:
                raise PreparedAuthorizationInvalid(
                    "prepared projection authority is invalid"
                ) from exc
            except PreparedAuthorizationUnsupported as exc:
                raise AuthorizationDenied("projection authority denied") from exc
            except AuthorizationEvidenceUnavailable as exc:
                raise AuthorizationUnavailable("projection authority unavailable") from exc
            yield _PreparedProjection(
                self._component,
                custody,
                handle,
                caller_input,
                custody.actor_profile_id,
                custody.identity_link_id,
                locator,
            )
        finally:
            try:
                await manager.__aexit__(None, None, None)
            except PreparedAuthorizationHandleInvalid as exc:
                raise PreparedAuthorizationInvalid(
                    "prepared projection authority is invalid"
                ) from exc
            except PreparedAuthorizationUnsupported as exc:
                raise AuthorizationDenied("projection authority denied") from exc
            except AuthorizationEvidenceUnavailable as exc:
                raise AuthorizationUnavailable("projection authority unavailable") from exc


class GuideSufficiencyProjectionAuthorization(_ProjectionAuthorization):
    """Prepare only fixed-service guide-sufficiency projection authority."""

    def __init__(self, session: AsyncSession) -> None:
        """Create the guide-sufficiency projection adapter."""
        super().__init__(session, "guide_sufficiency")

    def prepare_sufficiency_projection(
        self, locator: ProjectGuideProjectionLocator
    ) -> AbstractAsyncContextManager[PreparedGuideSufficiencyProjection]:
        """Prepare guide-sufficiency projection authority."""
        return self._prepare(locator)


class ArtifactPolicyProjectionAuthorization(_ProjectionAuthorization):
    """Prepare only fixed-service artifact-policy projection authority."""

    def __init__(self, session: AsyncSession) -> None:
        """Create the artifact-policy projection adapter."""
        super().__init__(session, "submission_artifact_policy")

    def prepare_artifact_policy_projection(
        self, locator: ProjectGuideProjectionLocator
    ) -> AbstractAsyncContextManager[PreparedArtifactPolicyProjection]:
        """Prepare submission-artifact-policy projection authority."""
        return self._prepare(locator)
