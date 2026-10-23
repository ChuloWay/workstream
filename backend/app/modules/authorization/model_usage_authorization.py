"""Prepared AUTH adapter for project-owned checker model calls."""

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.model_usage import (
    BUDGET_CONFIGURE,
    COMPLETE,
    DISPATCH,
    GRANT,
    OBSERVE,
    PREPARE,
    PROFILE_PROVISION,
    RECOVER,
    RECOVERY_CHILD_AUTHORIZE,
    SETUP_COMPLETE,
    SETUP_DISPATCH,
    SETUP_MODEL_USAGE_ACTIONS,
    SETUP_OBSERVE,
    SETUP_PREPARE,
    CHECKER_MODEL_CALL_ACTIONS,
    MODEL_ADMIN_ACTIONS,
    ModelCallCompleteAuthorityFacts,
    ModelCallDispatchAuthorityFacts,
    ModelCallGrantAuthorityFacts,
    ModelCallObserveAuthorityFacts,
    ModelCallPrepareAuthorityFacts,
    ModelCallRecoverAuthorityFacts,
    ModelCallRecoveryChildAuthorityFacts,
    SetupModelCompleteAuthorityFacts,
    SetupModelDispatchAuthorityFacts,
    SetupModelObserveAuthorityFacts,
    SetupModelPrepareAuthorityFacts,
    checker_model_call_resource,
    project_model_admin_resource,
    setup_model_usage_resource,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.runtime import (
    AuthorizationDenied,
    AuthorizationEvidenceUnavailable,
    HumanAuthorizationContext,
    PreparedAuthorizationHandleInvalid,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
    PreparedAuthorityScope,
    PreparedAuthorityScopeKind,
    ServiceAuthorizationContext,
)
from app.modules.model_usage.api import (
    ModelActionEvidence,
    ModelBudgetProvisioningFacts,
    ModelCallEffectAuthorityFacts,
    ModelCallEvidence,
    ModelCallExecutionFacts,
    ModelCallUnavailable,
    ModelPaidSlotKey,
    ModelProfileProvisioningFacts,
    PreparedModelCallAttempt,
    PreparedSetupModelUsageEffect,
    SetupModelEffectAuthorityFacts,
    SetupModelUsageSlotKey,
    model_action_digest,
)


class CheckerModelAuthorization:
    """Bind exact model-call facts to current human or fixed-service authority."""

    __slots__ = ("_authorization", "_prepared")

    def __init__(
        self,
        authorization: AuthorizationService,
        prepared: PreparedAuthorizationService,
    ) -> None:
        if (
            prepared._authorization is not authorization
            or prepared._context != authorization._context
        ):
            raise TypeError("checker model authority requires one composition")
        self._authorization = authorization
        self._prepared = prepared

    async def authorize_profile(self, facts: ModelProfileProvisioningFacts) -> ModelActionEvidence:
        """Require a current system Operator for one exact project profile."""
        facts = ModelProfileProvisioningFacts.model_validate(facts)
        self._require_human(facts.actor_profile_id)
        resource = project_model_admin_resource(
            PROFILE_PROVISION,
            facts,
            actor_profile_id=facts.actor_profile_id,
        )
        return await self._authorize(
            PROFILE_PROVISION,
            resource,
            facts.operation_id,
            model_action_digest("profile", facts),
        )

    async def authorize_budget(self, facts: ModelBudgetProvisioningFacts) -> ModelActionEvidence:
        """Require a current system Operator for one exact project budget."""
        facts = ModelBudgetProvisioningFacts.model_validate(facts)
        self._require_human(facts.actor_profile_id)
        resource = project_model_admin_resource(
            BUDGET_CONFIGURE,
            facts,
            actor_profile_id=facts.actor_profile_id,
        )
        return await self._authorize(
            BUDGET_CONFIGURE,
            resource,
            facts.operation_id,
            model_action_digest("budget", facts),
        )

    async def authorize_prepare(
        self,
        execution: ModelCallExecutionFacts,
        slot: ModelPaidSlotKey,
        request_sha256: str,
    ) -> ModelActionEvidence:
        """Authorize one exact stable-slot preparation before CHECKERS locks."""
        facts = ModelCallPrepareAuthorityFacts(
            execution=execution,
            slot=slot,
            request_sha256=request_sha256,
        )
        return await self._authorize_runtime(
            PREPARE,
            facts,
            execution.evaluation_request_id,
            "prepare",
        )

    async def authorize_dispatch(
        self,
        execution: ModelCallExecutionFacts,
        attempt: PreparedModelCallAttempt,
        request_evidence: ModelCallEvidence,
    ) -> ModelActionEvidence:
        """Authorize reservation and one dispatch for exact verified evidence."""
        facts = ModelCallDispatchAuthorityFacts(
            execution=execution,
            attempt=attempt,
            request_evidence=request_evidence,
        )
        return await self._authorize_runtime(
            DISPATCH,
            facts,
            attempt.internal_call_request_id,
            "dispatch",
        )

    async def authorize_recover(
        self,
        execution: ModelCallExecutionFacts,
        effect: ModelCallEffectAuthorityFacts,
    ) -> ModelActionEvidence:
        """Authorize current-run attachment to one existing paid effect."""
        facts = ModelCallRecoverAuthorityFacts(
            execution=execution,
            effect=effect,
        )
        return await self._authorize_runtime(
            RECOVER,
            facts,
            execution.evaluation_request_id,
            "recover",
        )

    async def authorize_grant(
        self,
        execution: ModelCallExecutionFacts,
        slot: ModelPaidSlotKey,
        external_request_digest: str,
        token_hash: str,
    ) -> ModelActionEvidence:
        """Authorize one opaque invocation grant for the exact current call slot."""
        facts = ModelCallGrantAuthorityFacts(
            execution=execution,
            slot=slot,
            external_request_digest=external_request_digest,
            token_hash=token_hash,
        )
        return await self._authorize_runtime(
            GRANT,
            facts,
            execution.evaluation_request_id,
            "grant",
        )

    async def authorize_observe(
        self,
        effect: ModelCallEffectAuthorityFacts,
        provider_response_id: str | None,
        observation_digest: str,
    ) -> ModelActionEvidence:
        """Authorize a lease-independent observation of one dispatched effect."""
        facts = ModelCallObserveAuthorityFacts(
            effect=effect,
            provider_response_id=provider_response_id,
            observation_digest=observation_digest,
        )
        return await self._authorize_runtime(
            OBSERVE,
            facts,
            effect.internal_call_request_id,
            "observe",
        )

    async def authorize_child(
        self,
        project_id: UUID,
        parent_attempt_id: UUID,
        terminal_digest: str,
    ) -> ModelActionEvidence:
        """Require explicit system Operator authority for one recovery child."""
        actor_profile_id = self._require_human()
        facts = ModelCallRecoveryChildAuthorityFacts(
            project_id=project_id,
            parent_attempt_id=parent_attempt_id,
            terminal_digest=terminal_digest,
        )
        resource = project_model_admin_resource(
            RECOVERY_CHILD_AUTHORIZE,
            facts,
            actor_profile_id=actor_profile_id,
        )
        return await self._authorize(
            RECOVERY_CHILD_AUTHORIZE,
            resource,
            parent_attempt_id,
            model_action_digest("child", facts),
        )

    async def authorize_complete(
        self,
        effect: ModelCallEffectAuthorityFacts,
        response_evidence: ModelCallEvidence | None,
        terminal_digest: str,
    ) -> ModelActionEvidence:
        """Authorize terminalization of one exact lease-independent effect."""
        facts = ModelCallCompleteAuthorityFacts(
            effect=effect,
            response_evidence=response_evidence,
            terminal_digest=terminal_digest,
        )
        return await self._authorize_runtime(
            COMPLETE,
            facts,
            effect.internal_call_request_id,
            "complete",
        )

    async def authorize_setup_prepare(
        self, slot: SetupModelUsageSlotKey, request_sha256: str
    ) -> ModelActionEvidence:
        """Authorize one stable setup phase/call slot before MODEL locks."""
        facts = SetupModelPrepareAuthorityFacts(
            slot=slot,
            request_sha256=request_sha256,
        )
        return await self._authorize_setup(
            SETUP_PREPARE,
            facts,
            uuid5(NAMESPACE_URL, "workstream:setup-model:" + slot.digest),
            "setup_prepare",
        )

    async def authorize_setup_dispatch(
        self,
        prepared: PreparedSetupModelUsageEffect,
        request_evidence: ModelCallEvidence,
    ) -> ModelActionEvidence:
        """Authorize one verified setup provider dispatch."""
        facts = SetupModelDispatchAuthorityFacts(
            prepared=prepared,
            request_evidence=request_evidence,
        )
        return await self._authorize_setup(
            SETUP_DISPATCH,
            facts,
            prepared.internal_call_request_id,
            "setup_dispatch",
        )

    async def authorize_setup_observe(
        self,
        effect: SetupModelEffectAuthorityFacts,
        provider_response_id: str | None,
        observation_digest: str,
    ) -> ModelActionEvidence:
        """Authorize retention of an ambiguous setup provider effect."""
        facts = SetupModelObserveAuthorityFacts(
            effect=effect,
            provider_response_id=provider_response_id,
            observation_digest=observation_digest,
        )
        return await self._authorize_setup(
            SETUP_OBSERVE,
            facts,
            effect.internal_call_request_id,
            "setup_observe",
        )

    async def authorize_setup_complete(
        self,
        effect: SetupModelEffectAuthorityFacts,
        response_evidence: ModelCallEvidence | None,
        terminal_digest: str,
    ) -> ModelActionEvidence:
        """Authorize exact terminal setup accounting or proven no-effect release."""
        facts = SetupModelCompleteAuthorityFacts(
            effect=effect,
            response_evidence=response_evidence,
            terminal_digest=terminal_digest,
        )
        return await self._authorize_setup(
            SETUP_COMPLETE,
            facts,
            effect.internal_call_request_id,
            "setup_complete",
        )

    async def _authorize_setup(
        self,
        action: ActionId,
        facts: (
            SetupModelPrepareAuthorityFacts
            | SetupModelDispatchAuthorityFacts
            | SetupModelObserveAuthorityFacts
            | SetupModelCompleteAuthorityFacts
        ),
        idempotency_key: UUID,
        service_action: str,
    ) -> ModelActionEvidence:
        self._require_setup_service()
        return await self._authorize(
            action,
            setup_model_usage_resource(action, facts),
            idempotency_key,
            model_action_digest(service_action, facts),
        )

    async def _authorize_runtime(
        self,
        action: ActionId,
        facts: (
            ModelCallPrepareAuthorityFacts
            | ModelCallDispatchAuthorityFacts
            | ModelCallRecoverAuthorityFacts
            | ModelCallObserveAuthorityFacts
            | ModelCallCompleteAuthorityFacts
            | ModelCallGrantAuthorityFacts
        ),
        idempotency_key: UUID,
        service_action: str,
    ) -> ModelActionEvidence:
        self._require_post_submit_service()
        resource = checker_model_call_resource(action, facts)
        return await self._authorize(
            action,
            resource,
            idempotency_key,
            model_action_digest(service_action, facts),
        )

    async def _authorize(
        self,
        action: ActionId,
        resource,
        idempotency_key: UUID,
        service_facts_digest: str,
    ) -> ModelActionEvidence:
        if action in CHECKER_MODEL_CALL_ACTIONS:
            scope = PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT,
                project_id=resource.scope_project_id,
            )
        elif action in SETUP_MODEL_USAGE_ACTIONS:
            scope = PreparedAuthorityScope(
                kind=PreparedAuthorityScopeKind.PROJECT,
                project_id=resource.scope_project_id,
            )
        elif action in MODEL_ADMIN_ACTIONS:
            scope = PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.SYSTEM)
        else:
            raise ModelCallUnavailable("model_call_authority_unavailable")
        caller_input = PreparedAuthorizationInput(
            idempotency_key=idempotency_key,
            request_value=resource.model_dump(mode="json"),
        )
        handle = None
        try:
            handle = await self._prepared.prepare(action, caller_input, scope)
            decision = await self._prepared.consume(
                handle,
                action,
                caller_input,
                resource,
            )
        except PreparedAuthorizationUnsupported as error:
            try:
                await self._prepared.deny_unsupported(
                    action,
                    caller_input,
                    resource,
                    error,
                )
            except AuthorizationEvidenceUnavailable as evidence_error:
                raise ModelCallUnavailable(
                    "model_call_authority_evidence_unavailable"
                ) from evidence_error
            except (
                AuthorizationDenied,
                PreparedAuthorizationHandleInvalid,
                PreparedAuthorizationUnsupported,
            ):
                pass
            raise ModelCallUnavailable("model_call_authority_unavailable") from error
        except AuthorizationDenied as error:
            if handle is not None:
                try:
                    self._prepared.close_handle(handle)
                except PreparedAuthorizationHandleInvalid:
                    pass
            raise ModelCallUnavailable("model_call_authority_unavailable") from error
        except (AuthorizationEvidenceUnavailable, PreparedAuthorizationHandleInvalid) as error:
            if handle is not None:
                try:
                    self._prepared.close_handle(handle)
                except PreparedAuthorizationHandleInvalid:
                    pass
            raise ModelCallUnavailable("model_call_authority_evidence_unavailable") from error
        return ModelActionEvidence(
            evidence_id=decision.decision_id,
            facts_digest=service_facts_digest,
        )

    def _require_human(self, actor_profile_id: UUID | None = None) -> UUID:
        context = self._authorization._context
        if not isinstance(context, HumanAuthorizationContext) or (
            actor_profile_id is not None and context.actor_profile_id != actor_profile_id
        ):
            raise ModelCallUnavailable("model_call_authority_unavailable")
        return context.actor_profile_id

    def _require_post_submit_service(self) -> None:
        context = self._authorization._context
        if (
            not isinstance(context, ServiceAuthorizationContext)
            or context.service_identity is not ServiceIdentity.CHECKER_POST_SUBMIT
        ):
            raise ModelCallUnavailable("model_call_authority_unavailable")

    def _require_setup_service(self) -> None:
        context = self._authorization._context
        if (
            not isinstance(context, ServiceAuthorizationContext)
            or context.service_identity is not ServiceIdentity.PROJECT_SETUP
        ):
            raise ModelCallUnavailable("model_call_authority_unavailable")


__all__ = ("CheckerModelAuthorization",)
