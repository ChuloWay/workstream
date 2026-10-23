"""Verified ART metadata consumed by the model-call ledger, without transcript bytes."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.artifacts.models import (
    ArtifactBinding,
    ArtifactContent,
    ArtifactPutAttempt,
    ArtifactReplica,
    ArtifactVerificationJob,
    ArtifactVerificationReceipt,
)
from app.modules.checkers.api.model_calls import (
    ModelCallEvidence,
    ModelCallUnavailable,
    PreparedModelCallAttempt,
)


class CheckerModelEvidence:
    """Require immutable verified binding ancestry in the caller's transaction."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def require_request(
        self,
        attempt: PreparedModelCallAttempt,
        evidence: ModelCallEvidence,
    ) -> None:
        """Verify the immutable request under the owner's exact prepared attempt."""
        if evidence.content_sha256 != attempt.request_sha256:
            raise ModelCallUnavailable("model_call_evidence_unavailable")
        await self._require(attempt.attempt_id, "model_request", evidence)

    async def require_response(self, attempt_id: UUID, evidence: ModelCallEvidence) -> None:
        """Verify response custody for the effect already selected by CHECKERS."""
        await self._require(attempt_id, "model_response", evidence)

    async def _require(
        self,
        attempt_id: UUID,
        role: str,
        evidence: ModelCallEvidence,
    ) -> None:
        """Match all identities and integrity states without acquiring another owner lock."""
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise ModelCallUnavailable("model_call_evidence_unavailable")
        evidence = ModelCallEvidence.model_validate(evidence)
        binding = await self._session.scalar(
            select(ArtifactBinding.id)
            .join(ArtifactContent, ArtifactContent.id == ArtifactBinding.content_id)
            .join(ArtifactPutAttempt, ArtifactPutAttempt.id == ArtifactBinding.put_attempt_id)
            .join(
                ArtifactVerificationReceipt,
                ArtifactVerificationReceipt.id == ArtifactBinding.verification_receipt_id,
            )
            .join(
                ArtifactVerificationJob,
                ArtifactVerificationJob.id == ArtifactVerificationReceipt.verification_job_id,
            )
            .join(ArtifactReplica, ArtifactReplica.id == ArtifactVerificationJob.replica_id)
            .where(
                ArtifactBinding.id == str(evidence.binding_id),
                ArtifactBinding.resource_type == "checker_model_call",
                ArtifactBinding.resource_id == str(attempt_id),
                ArtifactBinding.logical_role == role,
                ArtifactBinding.scope_version == 1,
                ArtifactBinding.attribution_type == "service_identity",
                ArtifactBinding.actor_id == "workstream.artifact.checker_output",
                ArtifactBinding.project_id == ArtifactPutAttempt.project_id,
                ArtifactBinding.content_id == str(evidence.content_id),
                ArtifactBinding.put_attempt_id == str(evidence.put_attempt_id),
                ArtifactBinding.verification_receipt_id == str(evidence.verification_receipt_id),
                ArtifactBinding.supersedes_binding_id.is_(None),
                ArtifactContent.sha256 == evidence.content_sha256,
                ArtifactContent.byte_count == evidence.byte_count,
                ArtifactContent.media_type == evidence.media_type,
                ArtifactPutAttempt.model_call_attempt_id == str(attempt_id),
                ArtifactPutAttempt.checker_run_id.is_(None),
                ArtifactPutAttempt.producer_request_type == "checker_output",
                ArtifactPutAttempt.logical_role == role,
                ArtifactPutAttempt.sha256 == evidence.content_sha256,
                ArtifactPutAttempt.byte_count == evidence.byte_count,
                ArtifactPutAttempt.media_type == evidence.media_type,
                ArtifactPutAttempt.status == "object_confirmed",
                ArtifactPutAttempt.checker_output_custody_sealed.is_(True),
                ArtifactPutAttempt.replica_id == ArtifactReplica.id,
                ArtifactPutAttempt.storage_namespace_id == ArtifactReplica.storage_namespace_id,
                ArtifactPutAttempt.namespace_fingerprint == ArtifactReplica.namespace_fingerprint,
                ArtifactPutAttempt.canonical_target == ArtifactReplica.provider_object_ref,
                ArtifactVerificationJob.originating_put_attempt_id == ArtifactPutAttempt.id,
                ArtifactVerificationJob.status == "verified",
                ArtifactVerificationJob.terminal_result_code == "verified",
                ArtifactVerificationJob.terminal_at.is_not(None),
                ArtifactVerificationJob.checker_output_custody_sealed.is_(True),
                ArtifactVerificationReceipt.outcome == "verified",
                ArtifactVerificationReceipt.execution_generation
                == ArtifactVerificationJob.execution_generation,
                ArtifactVerificationReceipt.observed_sha256 == evidence.content_sha256,
                ArtifactVerificationReceipt.observed_byte_count == evidence.byte_count,
                ArtifactReplica.content_id == ArtifactContent.id,
                ArtifactReplica.checker_output_custody_sealed.is_(True),
                ArtifactReplica.verification_state == "verified",
                ArtifactReplica.availability_state == "available",
                ArtifactReplica.integrity_state == "valid",
            )
        )
        if binding is None:
            raise ModelCallUnavailable("model_call_evidence_unavailable")
