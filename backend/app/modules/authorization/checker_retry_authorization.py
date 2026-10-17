"""AUTH-owned prepared system Operator authority for one checker retry."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.checker_retry import (
    CheckerRetryPrepareDenialResourceContext,
    CheckerRetryResourceContext,
    checker_retry_resource_json,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    AuthorizationContext, AuthorizationDenied, HumanAuthorizationContext,
    PreparedAuthorizationHandleInvalid, PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported, PreparedAuthorityScope, PreparedAuthorityScopeKind,
    authorization_resource_digest,
)
from app.modules.checkers.api.execution import (
    CheckerRetryAuthorityDenied, CheckerRetryAuthorityReceipt,
    CheckerRetryOperationUnavailable, CheckerRetryPreparation, CheckerRetrySuccessor,
)


class PreparedCheckerRetryAuthorization:
    """Bind original source and reason before CHECKERS allocates a successor."""

    def __init__(self, session: AsyncSession, context: AuthorizationContext) -> None:
        self._context = context
        repository = AdminAuthorizationRepository(session)
        kernel = AuthorizationService(session, context, admin_repository=repository)
        self._kernel = kernel
        self._service = PreparedAuthorizationService(session, context, kernel, repository)

    @staticmethod
    def _caller_input(facts: CheckerRetryPreparation) -> PreparedAuthorizationInput:
        return PreparedAuthorizationInput(
            idempotency_key=facts.request_key,
            request_value=facts.model_dump(mode="json"),
        )

    def _resource(
        self, facts: CheckerRetryPreparation, successor: CheckerRetrySuccessor,
        identity_link_id,
    ) -> CheckerRetryResourceContext:
        return CheckerRetryResourceContext(
            resource_id=facts.source.source_run_id,
            project_id=facts.source.project_id,
            identity_link_id=identity_link_id,
            preparation=facts,
            successor=successor,
        )

    async def prepare(self, facts: CheckerRetryPreparation) -> object:
        facts = CheckerRetryPreparation.model_validate(facts)
        if (
            not isinstance(self._context, HumanAuthorizationContext)
            or self._context.actor_profile_id != facts.actor_profile_id
            or self._context.request_id != facts.request_key
            or self._context.correlation_id != facts.request_key
        ):
            self._service.close()
            raise CheckerRetryOperationUnavailable("checker_retry_authority_unavailable")
        caller_input = self._caller_input(facts)
        try:
            return await self._service.prepare(
                ActionId.OPERATIONS_CHECKER_RETRY,
                caller_input,
                PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM),
            )
        except AuthorizationDenied as exc:
            self._service.close()
            raise CheckerRetryAuthorityDenied("checker_retry_authority_unavailable") from exc
        except PreparedAuthorizationUnsupported as exc:
            resource = CheckerRetryPrepareDenialResourceContext(
                resource_id=facts.source.source_run_id,
                project_id=facts.source.project_id,
                identity_link_id=self._context.identity_link_id,
                preparation=facts,
            )
            try:
                await self._service.deny_unsupported(
                    ActionId.OPERATIONS_CHECKER_RETRY,
                    caller_input,
                    resource,
                    exc,
                )
            except AuthorizationDenied as denial:
                self._service.close()
                raise CheckerRetryAuthorityDenied(
                    "checker_retry_authority_unavailable"
                ) from denial
            except BaseException:
                self._service.close()
                raise
            self._service.close()
            raise CheckerRetryOperationUnavailable(
                "checker_retry_authority_unavailable"
            ) from exc
        except PreparedAuthorizationHandleInvalid as exc:
            self._service.close()
            raise CheckerRetryOperationUnavailable(
                "checker_retry_authority_unavailable"
            ) from exc
        except BaseException:
            self._service.close()
            raise

    async def consume(
        self, handle: object, facts: CheckerRetryPreparation,
        successor: CheckerRetrySuccessor,
    ) -> CheckerRetryAuthorityReceipt:
        resource = self._resource(facts, successor, self._context.identity_link_id)
        try:
            decision = await self._service.consume(
                handle, ActionId.OPERATIONS_CHECKER_RETRY,
                self._caller_input(facts), resource,
            )
        except AuthorizationDenied as exc:
            raise CheckerRetryAuthorityDenied("checker_retry_authority_unavailable") from exc
        except (PreparedAuthorizationUnsupported, PreparedAuthorizationHandleInvalid) as exc:
            raise CheckerRetryOperationUnavailable(
                "checker_retry_authority_unavailable"
            ) from exc
        digest = authorization_resource_digest(resource)
        if decision.resource_context_digest != digest:
            raise CheckerRetryOperationUnavailable("checker_retry_authority_unavailable")
        return CheckerRetryAuthorityReceipt(
            actor_profile_id=facts.actor_profile_id,
            identity_link_id=self._context.identity_link_id,
            decision_id=decision.decision_id,
            resource_digest=digest,
            resource_json=checker_retry_resource_json(resource),
        )

    async def validate_replay(
        self, handle: object, facts: CheckerRetryPreparation,
        successor: CheckerRetrySuccessor, original_link_id,
        decision_id,
    ) -> None:
        try:
            await self._service.validate_replay(
                handle, ActionId.OPERATIONS_CHECKER_RETRY,
                self._caller_input(facts),
                self._resource(facts, successor, original_link_id), decision_id,
            )
        except AuthorizationDenied as exc:
            raise CheckerRetryAuthorityDenied("checker_retry_replay_unavailable") from exc
        except (PreparedAuthorizationUnsupported, PreparedAuthorizationHandleInvalid) as exc:
            raise CheckerRetryOperationUnavailable(
                "checker_retry_replay_unavailable"
            ) from exc

    def close(self, handle: object) -> None:
        self._service.close()

    async def restage_denial(self, error: CheckerRetryAuthorityDenied) -> bool:
        """Persist only the exact pending decision after caller-root rollback."""
        if isinstance(error.__cause__, AuthorizationDenied):
            await self._kernel.restage_denial(error.__cause__.decision)
            return True
        return False
