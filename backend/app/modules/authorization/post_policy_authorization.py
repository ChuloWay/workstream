"""Post-policy service and project-manager authority over the canonical request-local kernel/PREP."""

from contextlib import asynccontextmanager, contextmanager

from app.modules.authorization.api import (
    AuthorizationDenied as BoundaryDenied,
    AuthorizationUnavailable,
    PreparedAuthorizationInvalid,
)
from app.modules.authorization.api.post_policy import (
    PostPolicyAuthorityReceipt,
    PreparedPostPolicyOperation,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.post_policy import post_policy_resource, post_policy_selectors
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    AuthorizationDenied,
    AuthorizationEvidenceUnavailable,
    HumanAuthorizationContext,
    ServiceAuthorizationContext,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)


@contextmanager
def _authority_errors():
    """Translate AUTH failures without swallowing product-owner exceptions."""
    try:
        yield
    except PreparedAuthorizationHandleInvalid as exc:
        raise PreparedAuthorizationInvalid("invalid post-policy authority") from exc
    except (PreparedAuthorizationUnsupported, AuthorizationDenied) as exc:
        raise BoundaryDenied("post-policy authority denied") from exc
    except AuthorizationEvidenceUnavailable as exc:
        raise AuthorizationUnavailable("post-policy authority unavailable") from exc


class _PreparedPostPolicy(PreparedPostPolicyOperation):
    """Nominal view; shared PREP alone owns one-use/session/transaction custody."""

    def __init__(self, service, handle, caller_input, locator, service_identity):
        self._service, self._handle = service, handle
        self._input, self._locator = caller_input, locator
        self._service_identity = service_identity

    def _resource(self, facts):
        try:
            resource = post_policy_resource(facts)
            if facts.locator != self._locator:
                raise ValueError("locator changed")
            return resource
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreparedAuthorizationInvalid("invalid post-policy facts") from exc

    async def authorize_read(self, facts):
        if self._locator.action_id != ActionId.PROJECT_GUIDE_COMPILATION_REVIEW_PACKAGE_READ.value:
            raise PreparedAuthorizationInvalid("post-policy read action required")
        resource = self._resource(facts)
        with _authority_errors():
            await self._service.consume(
                self._handle, ActionId(self._locator.action_id), self._input, resource
            )

    async def consume_new(self, facts):
        if self._locator.action_id == ActionId.PROJECT_GUIDE_COMPILATION_REVIEW_PACKAGE_READ.value:
            raise PreparedAuthorizationInvalid("post-policy mutation action required")
        resource = self._resource(facts)
        with _authority_errors():
            decision = await self._service.consume(
                self._handle,
                ActionId(self._locator.action_id),
                self._input,
                resource,
            )
        return PostPolicyAuthorityReceipt(
            actor_profile_id=self._locator.actor_profile_id,
            identity_link_id=self._locator.identity_link_id,
            admin_role_grant_id=decision.matched_grant_id,
            service_identity=self._service_identity,
            authorization_decision_event_id=decision.decision_id,
            action_id=self._locator.action_id,
            permission_id=decision.permission_id.value,
            scope_project_id=resource.scope_project_id,
            resource_context_digest=decision.resource_context_digest,
        )

    async def validate_replay(self, facts, decision_event_id):
        if self._locator.action_id == ActionId.PROJECT_GUIDE_COMPILATION_REVIEW_PACKAGE_READ.value:
            raise PreparedAuthorizationInvalid("post-policy mutation replay required")
        resource = self._resource(facts)
        with _authority_errors():
            await self._service.validate_replay(
                self._handle,
                ActionId(self._locator.action_id),
                self._input,
                resource,
                decision_event_id,
            )


class PostPolicyAuthorizationAdapter:
    """Compose shared AUTH from authenticated context; never resolve identity from selectors."""

    def __init__(self, session, context):
        self._session, self._context = session, context

    @asynccontextmanager
    async def prepare_post_policy_operation(self, locator):
        try:
            selectors = post_policy_selectors(locator)
        except (AttributeError, TypeError, ValueError) as exc:
            raise PreparedAuthorizationInvalid("invalid post-policy locator") from exc
        context = self._context
        if (
            type(context) not in (HumanAuthorizationContext, ServiceAuthorizationContext)
            or context.actor_profile_id != locator.actor_profile_id
            or context.identity_link_id != locator.identity_link_id
            or context.request_id != locator.request_id
        ):
            raise BoundaryDenied("post-policy identity denied")
        # POL supplies its stable business operation; transport request remains unchanged.
        context = context.model_copy(update={"correlation_id": locator.operation_id})
        repository = AdminAuthorizationRepository(self._session)
        kernel = AuthorizationService(self._session, context, admin_repository=repository)
        service = PreparedAuthorizationService(self._session, context, kernel, repository)
        try:
            caller_input = PreparedAuthorizationInput(
                idempotency_key=locator.operation_id, request_value=selectors
            )
            with _authority_errors():
                handle = await service.prepare(
                    ActionId(locator.action_id),
                    caller_input,
                    PreparedAuthorityScope(
                        kind=PreparedAuthorityScopeKind.PROJECT, project_id=locator.project_id
                    ),
                )
            yield _PreparedPostPolicy(
                service,
                handle,
                caller_input,
                locator,
                context.service_identity.value
                if type(context) is ServiceAuthorizationContext
                else None,
            )
        finally:
            service.close()
