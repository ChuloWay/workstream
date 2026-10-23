"""AUTH-owned exact decision adapters for ART Operator operations."""

from pydantic import ValidationError

from app.modules.artifacts.api.operator_authority import (
    ArtifactOperatorAuthorityDenied,
    ArtifactOperatorAuthorityFacts,
    ArtifactOperatorAuthorityUnavailable,
    ArtifactOperatorAuthorizationEvidence,
    ArtifactRecoveryAuthorityFacts,
    ArtifactRecoveryAuthorizationEvidence,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.artifact_operator import (
    ArtifactOperatorReadResourceContext,
    ArtifactOperatorRetryResourceContext,
)
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.runtime import (
    AuthorizationDenied,
    AuthorizationEvidenceUnavailable,
    HumanAuthorizationContext,
    ServiceAuthorizationContext,
)


class _ExactArtifactOperatorAuthorization:
    def __init__(self, kernel: AuthorizationService) -> None:
        self._kernel = kernel
        self._denial: AuthorizationDenied | None = None

    async def _require(self, action: ActionId, resource):
        self._denial = None
        try:
            return await self._kernel.require(action, resource)
        except AuthorizationDenied as exc:
            self._denial = exc
            raise ArtifactOperatorAuthorityDenied("artifact Operator authority denied") from exc
        except (AuthorizationEvidenceUnavailable, ValidationError) as exc:
            raise ArtifactOperatorAuthorityUnavailable(
                "artifact Operator evidence unavailable"
            ) from exc

    async def restage_denial(self) -> bool:
        denial = self._denial
        self._denial = None
        if denial is None:
            return False
        await self._kernel.restage_denial(denial.decision)
        return True


class ArtifactOperatorReadAuthorization(_ExactArtifactOperatorAuthorization):
    """One system-scoped Operator decision over ART's server-owned lineage."""

    async def authorize(
        self, *, authorization_context: object, facts: ArtifactOperatorAuthorityFacts
    ) -> ArtifactOperatorAuthorizationEvidence:
        if type(facts) is not ArtifactOperatorAuthorityFacts or type(authorization_context) not in (
            HumanAuthorizationContext,
            ServiceAuthorizationContext,
        ):
            raise ArtifactOperatorAuthorityUnavailable("invalid artifact Operator facts")
        try:
            action = ActionId(facts.action_id)
            resource = ArtifactOperatorReadResourceContext(
                resource_type=facts.resource_type.value,
                resource_id=facts.record_id or "workstream:artifact_storage_readiness",
                selector=facts.resource_id,
                project_ids=facts.project_ids,
                action_id=action,
                identity_link_id=authorization_context.identity_link_id,
            )
        except (ValueError, ValidationError) as exc:
            raise ArtifactOperatorAuthorityUnavailable("invalid artifact Operator facts") from exc
        decision = await self._require(action, resource)
        return ArtifactOperatorAuthorizationEvidence(
            action_id=decision.action_id.value,
            permission_id=decision.permission_id.value,
            decision_id=decision.decision_id,
        )


class ArtifactOperatorRetryAuthorization(_ExactArtifactOperatorAuthorization):
    """Independent system-scoped retry decision within ART's transaction."""

    async def authorize(
        self, *, authorization_context: object, facts: ArtifactRecoveryAuthorityFacts
    ) -> ArtifactRecoveryAuthorizationEvidence:
        if (
            type(facts) is not ArtifactRecoveryAuthorityFacts
            or type(authorization_context) is not HumanAuthorizationContext
        ):
            raise ArtifactOperatorAuthorityUnavailable("invalid artifact recovery facts")
        try:
            resource = ArtifactOperatorRetryResourceContext(
                resource_id=facts.source_verification_job_id,
                project_id=facts.project_id,
                task_id=facts.task_id,
                submission_id=facts.submission_id,
                expected_source_job_cas_version=facts.expected_source_job_cas_version,
                identity_link_id=authorization_context.identity_link_id,
            )
        except ValidationError as exc:
            raise ArtifactOperatorAuthorityUnavailable("invalid artifact recovery facts") from exc
        decision = await self._require(ActionId.ARTIFACT_VERIFICATION_JOB_RETRY, resource)
        return ArtifactRecoveryAuthorizationEvidence(
            action_id=decision.action_id.value,
            permission_id=decision.permission_id.value,
            decision_id=decision.decision_id,
        )
