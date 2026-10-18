"""AUTH-owned system Operator decision and retained worker-cause verification."""

from __future__ import annotations

import json

from sqlalchemy import text

from app.modules.authorization.catalogue import ActionId, PermissionId
from app.modules.authorization.domain.post_submit_deliveries import (
    POST_SUBMIT_DELIVERY_RECONCILE_ACTION,
    PostSubmitDeliveryResourceContext,
)
from app.modules.authorization.runtime import (
    AuthorizationDenied,
    HumanAuthorizationContext,
    authorization_resource_digest,
)
from app.modules.checkers.api.delivery_reconciliation import (
    PostSubmitDeliveryAuthorityDenied,
    PostSubmitDeliveryAuthorityReceipt,
    PostSubmitDeliveryChildPayload,
    PostSubmitDeliveryOperationUnavailable,
    PostSubmitDeliveryPreparation,
)
from app.modules.outbox.api import OutboxEventEnvelope


class PostSubmitDeliveryAuthorization:
    """Create fresh Operator decisions and validate the retained decision as cause."""

    def __init__(self, session, context, kernel) -> None:
        self._session, self._context, self._kernel = session, context, kernel

    def _require_context(self, facts: PostSubmitDeliveryPreparation) -> None:
        if (
            not isinstance(self._context, HumanAuthorizationContext)
            or self._context.actor_profile_id != facts.command.actor_profile_id
            or self._context.request_id != facts.command.request_key
            or self._context.correlation_id != facts.command.request_key
        ):
            raise PostSubmitDeliveryOperationUnavailable(
                "post_submit_delivery_authority_unavailable"
            )

    @staticmethod
    def _resource(facts, identity_link_id):
        return PostSubmitDeliveryResourceContext(
            resource_id=facts.source.event_id,
            scope_project_id=facts.source.project_id,
            identity_link_id=identity_link_id,
            preparation=facts,
        )

    async def prepare(self, facts):
        facts = PostSubmitDeliveryPreparation.model_validate(facts)
        self._require_context(facts)
        return facts

    async def consume(self, handle, facts):
        facts = PostSubmitDeliveryPreparation.model_validate(facts)
        if handle != facts:
            raise PostSubmitDeliveryOperationUnavailable(
                "post_submit_delivery_authority_unavailable"
            )
        resource = self._resource(facts, self._context.identity_link_id)
        try:
            decision = await self._kernel.require(
                POST_SUBMIT_DELIVERY_RECONCILE_ACTION, resource
            )
        except AuthorizationDenied as exc:
            raise PostSubmitDeliveryAuthorityDenied(
                "post_submit_delivery_authority_unavailable"
            ) from exc
        digest = authorization_resource_digest(resource)
        if decision.resource_context_digest != digest:
            raise PostSubmitDeliveryOperationUnavailable(
                "post_submit_delivery_authority_unavailable"
            )
        return PostSubmitDeliveryAuthorityReceipt(
            actor_profile_id=facts.command.actor_profile_id,
            identity_link_id=self._context.identity_link_id,
            decision_id=decision.decision_id,
            resource_digest=digest,
            resource_json=json.dumps(
                {"resource_context": resource.model_dump(mode="json")},
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    async def validate_replay(
        self, handle, facts, original_link_id, decision_id,
    ) -> None:
        facts = PostSubmitDeliveryPreparation.model_validate(facts)
        if handle != facts:
            raise PostSubmitDeliveryOperationUnavailable(
                "post_submit_delivery_replay_unavailable"
            )
        self._require_context(facts)
        resource = self._resource(facts, original_link_id)
        try:
            await self._kernel.require(
                POST_SUBMIT_DELIVERY_RECONCILE_ACTION,
                self._resource(facts, self._context.identity_link_id),
            )
        except AuthorizationDenied as exc:
            raise PostSubmitDeliveryAuthorityDenied(
                "post_submit_delivery_replay_unavailable"
            ) from exc
        if not await self._decision_matches(
            decision_id=decision_id,
            actor_profile_id=facts.command.actor_profile_id,
            project_id=facts.command.project_id,
            event_id=facts.command.event_id,
            request_id=facts.command.request_key,
            resource_digest=authorization_resource_digest(resource),
        ):
            raise PostSubmitDeliveryOperationUnavailable(
                "post_submit_delivery_replay_unavailable"
            )

    def close(self, handle) -> None:
        return None

    async def restage_denial(self, error):
        if isinstance(error.__cause__, AuthorizationDenied):
            await self._kernel.restage_denial(error.__cause__.decision)
            return True
        return False

    async def validate_cause(
        self,
        payload: PostSubmitDeliveryChildPayload,
        original: OutboxEventEnvelope,
    ) -> None:
        if (
            payload.original_event_id != original.claim.event_id
            or not await self._decision_matches(
                decision_id=payload.authorization_decision_id,
                actor_profile_id=payload.operator_actor_profile_id,
                project_id=original.claim.project_id,
                event_id=original.claim.event_id,
                request_id=payload.reconciliation_request_id,
                resource_digest=payload.authorization_resource_digest,
            )
        ):
            raise PostSubmitDeliveryOperationUnavailable(
                "post_submit_delivery_cause_unavailable"
            )

    async def _decision_matches(
        self,
        *,
        decision_id,
        actor_profile_id,
        project_id,
        event_id,
        request_id,
        resource_digest,
    ) -> bool:
        event = (
            await self._session.execute(
                text(
                    "SELECT event_type, actor_id, action_id, permission_id, "
                    "project_id, resource_type, resource_id, request_id, "
                    "correlation_id, denial_code, after_facts "
                    "FROM public.audit_events WHERE id=:decision_id"
                ),
                {"decision_id": decision_id},
            )
        ).mappings().one_or_none()
        return bool(
            event is not None
            and event["event_type"] == "SensitiveAuthorizationAllowed"
            and event["actor_id"] == str(actor_profile_id)
            and event["action_id"] == ActionId.OPERATIONS_POST_SUBMIT_DELIVERY_RECONCILE.value
            and event["permission_id"] == PermissionId.OPERATIONS_RECONCILE_RUN.value
            and str(event["project_id"]) == str(project_id)
            and event["resource_type"] == "outbox_delivery"
            and event["resource_id"] == str(event_id)
            and str(event["request_id"]) == str(request_id)
            and str(event["correlation_id"]) == str(request_id)
            and event["denial_code"] is None
            and event["after_facts"] == {
                "allowed": True,
                "resource_context_digest": resource_digest,
            }
        )
