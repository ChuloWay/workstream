"""AUTH-owned prepared system Operator authority for the checker registry."""

from __future__ import annotations

from uuid import UUID

from app.core.identifiers import new_record_id
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.checker_registry import (
    ExternalCheckerRegistryResourceContext,
)
from app.modules.authorization.kernel import (
    AuthorizationService,
    prelock_serialized_admin_read_actor,
)
from app.modules.authorization.prepared import (
    PreparedAuthorizationHandle,
    PreparedAuthorizationService,
)
from app.modules.authorization.runtime import (
    AuthorizationDenied,
    AuthorizationEvidenceUnavailable,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
)
from app.modules.checkers.api import (
    ExternalCheckerRegistrationAuthorityFacts,
    ExternalCheckerRegistrationAuthorityReceipt,
    ExternalCheckerRegistrationPreparation,
    ExternalCheckerRegistryAuthorizationDenied,
    ExternalCheckerRegistryUnavailable,
)


class ExternalCheckerRegistryAuthorizationAdapter:
    """Bind CHECKERS facts to current prepared system Operator authority."""

    def __init__(
        self,
        authorization: AuthorizationService,
        prepared: PreparedAuthorizationService,
    ) -> None:
        if (
            prepared._authorization is not authorization
            or prepared._context != authorization._context
        ):
            raise TypeError("checker registry authority requires one composition")
        self._authorization = authorization
        self._prepared = prepared

    @staticmethod
    def _caller_input(
        facts: ExternalCheckerRegistrationPreparation,
    ) -> PreparedAuthorizationInput:
        return PreparedAuthorizationInput(
            idempotency_key=facts.operation_id,
            request_value=facts.model_dump(mode="json"),
        )

    @staticmethod
    def _resource(
        facts: ExternalCheckerRegistrationAuthorityFacts,
    ) -> ExternalCheckerRegistryResourceContext:
        return ExternalCheckerRegistryResourceContext(
            resource_type="external_checker_registry_entry",
            resource_id=facts.registry_entry_id,
            operation_id=facts.operation_id,
            request_digest=facts.request_digest,
            entry_digest=facts.entry_digest,
        )

    def _require_actor(self, actor_profile_id: UUID) -> None:
        if self._authorization._context.actor_profile_id != actor_profile_id:
            raise ExternalCheckerRegistryAuthorizationDenied(
                "external_checker_registry_unavailable"
            )

    async def prepare_registration(
        self, facts: ExternalCheckerRegistrationPreparation,
    ) -> object:
        """Lock current principal and system Operator grant before registry locks."""
        facts = ExternalCheckerRegistrationPreparation.model_validate(facts)
        self._require_actor(facts.actor_profile_id)
        if self._authorization._context.correlation_id != facts.operation_id:
            raise ExternalCheckerRegistryAuthorizationDenied(
                "external_checker_registry_unavailable"
            )
        caller_input = self._caller_input(facts)
        try:
            return await self._prepared.prepare(
                ActionId.CHECKER_REGISTRY_REGISTER,
                caller_input,
                PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM),
            )
        except PreparedAuthorizationUnsupported as exc:
            denial_resource = ExternalCheckerRegistryResourceContext(
                resource_type="external_checker_registry_entry",
                resource_id=new_record_id(),
                operation_id=facts.operation_id,
                request_digest=facts.entry_digest,
                entry_digest=facts.entry_digest,
            )
            try:
                await self._prepared.deny_unsupported(
                    ActionId.CHECKER_REGISTRY_REGISTER,
                    caller_input,
                    denial_resource,
                    exc,
                )
            except AuthorizationDenied as denied:
                raise ExternalCheckerRegistryAuthorizationDenied(
                    "external_checker_registry_unavailable"
                ) from denied
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            ) from exc
        except AuthorizationEvidenceUnavailable as exc:
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            ) from exc

    async def consume_registration(
        self,
        prepared: object,
        preparation: ExternalCheckerRegistrationPreparation,
        facts: ExternalCheckerRegistrationAuthorityFacts,
    ) -> ExternalCheckerRegistrationAuthorityReceipt:
        """Finalize only the exact row selected while prepared locks are held."""
        preparation = ExternalCheckerRegistrationPreparation.model_validate(preparation)
        facts = ExternalCheckerRegistrationAuthorityFacts.model_validate(facts)
        self._require_actor(facts.actor_profile_id)
        if (
            type(prepared) is not PreparedAuthorizationHandle
            or facts.actor_profile_id != preparation.actor_profile_id
            or facts.operation_id != preparation.operation_id
            or facts.entry_digest != preparation.entry_digest
        ):
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            )
        try:
            decision = await self._prepared.consume(
                prepared,
                ActionId.CHECKER_REGISTRY_REGISTER,
                self._caller_input(preparation),
                self._resource(facts),
            )
        except AuthorizationDenied as exc:
            raise ExternalCheckerRegistryAuthorizationDenied(
                "external_checker_registry_unavailable"
            ) from exc
        except (
            PreparedAuthorizationHandleInvalid,
            PreparedAuthorizationUnsupported,
            AuthorizationEvidenceUnavailable,
        ) as exc:
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            ) from exc
        return ExternalCheckerRegistrationAuthorityReceipt(
            actor_profile_id=facts.actor_profile_id,
            authorization_decision_event_id=decision.decision_id,
        )

    def close_registration(self, prepared: object) -> None:
        """Invalidate the exact request-local registration capability."""
        if type(prepared) is not PreparedAuthorizationHandle:
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            )
        try:
            self._prepared.close_handle(prepared)
        except PreparedAuthorizationHandleInvalid as exc:
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            ) from exc

    async def prepare_read(self, actor_profile_id: UUID) -> None:
        """Lock and revalidate the request actor before reading registry facts."""
        self._require_actor(actor_profile_id)
        try:
            await prelock_serialized_admin_read_actor(
                self._authorization, ActionId.CHECKER_REGISTRY_READ
            )
        except (PreparedAuthorizationUnsupported, AuthorizationEvidenceUnavailable) as exc:
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            ) from exc

    async def authorize_read(
        self, facts: ExternalCheckerRegistrationAuthorityFacts,
    ) -> None:
        """Authorize disclosure of one validated immutable registry entry."""
        facts = ExternalCheckerRegistrationAuthorityFacts.model_validate(facts)
        self._require_actor(facts.actor_profile_id)
        try:
            await self._authorization.require(
                ActionId.CHECKER_REGISTRY_READ, self._resource(facts)
            )
        except AuthorizationDenied as exc:
            raise ExternalCheckerRegistryAuthorizationDenied(
                "external_checker_registry_unavailable"
            ) from exc
        except AuthorizationEvidenceUnavailable as exc:
            raise ExternalCheckerRegistryUnavailable(
                "external_checker_registry_unavailable"
            ) from exc
