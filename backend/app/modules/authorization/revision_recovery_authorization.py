"""Fresh fixed-service authorization for one retained revision source."""

from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.revision_recovery import RevisionRecoveryResourceContext
from app.modules.authorization.prepared import fixed_service_prepared_authorization
from app.modules.authorization.runtime import PreparedAuthorizationInput, PreparedAuthorityScope, PreparedAuthorityScopeKind
from app.modules.tasks.api.authorization import TaskAuthorityDecision
from app.modules.tasks.api.revision_recovery import RECOVERY_REASON


class RevisionRecoveryAuthorizationAdapter:
    def __init__(self, session):
        self._session = session

    async def authorize(self, facts):
        async with fixed_service_prepared_authorization(
            self._session, service_identity=ServiceIdentity.TASK_REVISION_EXPIRER,
            request_id=facts.routing_manifest_id, correlation_id=facts.routing_manifest_id,
        ) as authority:
            resource = RevisionRecoveryResourceContext(
                resource_id=facts.task_id, scope_project_id=facts.project_id,
                actor_profile_id=authority.actor_profile_id,
                identity_link_id=authority.identity_link_id,
                task_status="needs_revision", assigned_to=facts.contributor_id,
                assignment_id=facts.assignment_id,
                assignment_contributor_id=facts.contributor_id,
                locked_context_hash=facts.locked_context_hash,
                reason=RECOVERY_REASON, idempotency_key=facts.routing_manifest_id,
                request_digest=facts.request_digest,
                revision_routing_manifest_id=facts.routing_manifest_id,
                revision_preparation_id=facts.preparation_id,
                revision_preparation_sha256=facts.preparation_sha256,
            )
            caller = PreparedAuthorizationInput(
                idempotency_key=facts.routing_manifest_id,
                request_value=resource.model_dump(mode="json"),
            )
            handle = await authority.service.prepare(
                ActionId.TASK_REVISION_RECOVER, caller,
                PreparedAuthorityScope(kind=PreparedAuthorityScopeKind.PROJECT,
                                       project_id=facts.project_id),
            )
            decision = await authority.service.consume(
                handle, ActionId.TASK_REVISION_RECOVER, caller, resource,
            )
            return authority.actor_profile_id, TaskAuthorityDecision(
                decision.decision_id, authority.identity_link_id,
                decision.resource_context_digest, resource.model_dump_json(),
            )
