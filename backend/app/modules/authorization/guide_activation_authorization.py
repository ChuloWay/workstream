"""Live manager authority for the existing PROJECTS activation operation."""

from contextlib import asynccontextmanager, contextmanager

from app.modules.authorization.api import (
    AuthorizationDenied as BoundaryDenied, AuthorizationUnavailable, PreparedAuthorizationInvalid,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.guide_activation import activation_resource, activation_selectors
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    AuthorizationDenied, AuthorizationEvidenceUnavailable, HumanAuthorizationContext,
    PreparedAuthorizationHandleInvalid, PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported, PreparedAuthorityScope, PreparedAuthorityScopeKind,
)
from app.modules.projects.api.guide_activation import (
    GuideActivationAuthorityReceipt, PreparedGuideActivation,
)


@contextmanager
def _authority_errors():
    """Sanitize AUTH failures while preserving product-owner exceptions."""
    try:
        yield
    except PreparedAuthorizationHandleInvalid as exc:
        raise PreparedAuthorizationInvalid("invalid activation authority") from exc
    except (PreparedAuthorizationUnsupported, AuthorizationDenied) as exc:
        raise BoundaryDenied("activation authority denied") from exc
    except AuthorizationEvidenceUnavailable as exc:
        raise AuthorizationUnavailable("activation authority unavailable") from exc


class _PreparedGuideActivation(PreparedGuideActivation):
    """The shared PREP owner retains one-use/session/root-transaction custody."""

    def __init__(self, service, handle, caller_input, locator):
        self._service, self._handle = service, handle
        self._input, self._locator = caller_input, locator

    def _resource(self, facts):
        """Revalidate complete facts against this prepared locator."""
        try:
            resource = activation_resource(facts)
            if facts.locator != self._locator:
                raise ValueError("locator changed")
            return resource
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreparedAuthorizationInvalid("invalid activation facts") from exc

    async def consume_new(self, facts):
        """Consume one exact authority and return its bounded audit receipt."""
        resource = self._resource(facts)
        with _authority_errors():
            decision = await self._service.consume(
                self._handle, ActionId.PROJECT_GUIDE_ACTIVATE, self._input, resource,
            )
        return GuideActivationAuthorityReceipt(
            actor_profile_id=self._locator.actor_profile_id,
            identity_link_id=self._locator.identity_link_id,
            admin_role_grant_id=decision.matched_grant_id,
            authorization_decision_event_id=decision.decision_id,
            action_id=ActionId.PROJECT_GUIDE_ACTIVATE.value,
            permission_id=decision.permission_id.value,
            scope_project_id=resource.scope_project_id,
            resource_context_digest=decision.resource_context_digest,
        )

    async def validate_replay(self, facts, decision_event_id):
        """Validate the retained allow using freshly acquired live authority."""
        resource = self._resource(facts)
        with _authority_errors():
            await self._service.validate_replay(
                self._handle, ActionId.PROJECT_GUIDE_ACTIVATE, self._input,
                resource, decision_event_id,
            )


class GuideActivationAuthorizationAdapter:
    """Explicit request-local composition; selectors cannot supply an identity."""

    def __init__(self, session, context):
        self._session, self._context = session, context

    @asynccontextmanager
    async def lock_activation_scope(self, locator):
        """Lock live human authority before PROJECTS enters product custody."""
        try:
            selectors = activation_selectors(locator)
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreparedAuthorizationInvalid("invalid activation locator") from exc
        context = self._context
        if (
            type(context) is not HumanAuthorizationContext
            or context.actor_profile_id != locator.actor_profile_id
            or context.identity_link_id != locator.identity_link_id
            or context.request_id != locator.request_id
        ):
            raise BoundaryDenied("activation identity denied")
        context = context.model_copy(update={"correlation_id": locator.operation_id})
        repository = AdminAuthorizationRepository(self._session)
        kernel = AuthorizationService(self._session, context, admin_repository=repository)
        service = PreparedAuthorizationService(self._session, context, kernel, repository)
        try:
            caller_input = PreparedAuthorizationInput(
                idempotency_key=locator.operation_id, request_value=selectors,
            )
            with _authority_errors():
                handle = await service.prepare(
                    ActionId.PROJECT_GUIDE_ACTIVATE, caller_input,
                    PreparedAuthorityScope(
                        kind=PreparedAuthorityScopeKind.PROJECT, project_id=locator.project_id,
                    ),
                )
            yield _PreparedGuideActivation(service, handle, caller_input, locator)
        finally:
            service.close()
