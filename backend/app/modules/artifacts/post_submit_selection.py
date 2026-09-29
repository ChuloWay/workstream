"""ART-owned exact admitted-material selection, without provider I/O or locks."""

from dataclasses import asdict, dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interfaces.artifacts import ArtifactStore, artifact_provider_object_ref
from app.modules.checkers.api.materialization import PostSubmissionMaterializationUnavailable
from app.modules.artifacts.models import (
    ArtifactBinding, ArtifactContent, ArtifactReplica, ArtifactStorageNamespace,
    ArtifactVerificationJob, ArtifactVerificationReceipt, PreSubmitEvidenceSet,
    SubmissionBundleAdmission,
)
from app.modules.artifacts.service import (
    ArtifactStorageNamespaceSpec, validate_artifact_replica_execution_namespace,
)
from app.modules.artifacts.sources import ArtifactCommitment
from app.modules.artifacts.submission_bindings import SubmissionAdmissionConsumptionService
from app.modules.checkers.api import PostSubmissionEvaluationRequest
from app.modules.tasks.api.submitted_bundle import (
    SubmittedBundleFacts, SubmittedBundlePort, SubmittedBundleRequest,
)


@dataclass(frozen=True, slots=True)
class PostSubmissionMaterialSelection:
    """Private detached snapshot; storage coordinates never leave ART."""

    submission: SubmittedBundleFacts
    evidence_id: UUID
    replica_id: UUID
    verification_receipt_id: UUID
    verification_job_id: UUID
    verification_generation: int
    namespace_fingerprint: str
    adapter: str
    provider_profile: str
    provider_object_ref: str
    sha256: str
    byte_count: int
    media_type: str
    semantic_manifest_id: UUID
    semantic_manifest_sha256: str


async def select_post_submission_material(
    session: AsyncSession, *, tasks: SubmittedBundlePort,
    request: PostSubmissionEvaluationRequest, namespace: ArtifactStorageNamespaceSpec,
    store: ArtifactStore,
) -> PostSubmissionMaterialSelection:
    """Read fresh exact owner facts in one short caller-owned transaction."""
    facts = await tasks.read(SubmittedBundleRequest(
        project_id=request.project_id, task_id=request.task_id, submission_id=request.submission_id,
    ))
    if (
        facts.status != "submitted"
        or (facts.project_id, facts.task_id, facts.assignment_id, facts.submission_id,
            facts.submission_version, facts.binding_id, facts.content_id) != (
                request.project_id, request.task_id, request.assignment_id, request.submission_id,
                request.submission_version, request.binding_id, request.content_id)
        or asdict(facts.context) != request.expected_context.model_dump()
        or asdict(facts.context) != request.structural_input.observed_context.model_dump()
    ):
        raise PostSubmissionMaterializationUnavailable("post_submit_material_identity_mismatch")
    row = (await session.execute(
        select(SubmissionBundleAdmission, PreSubmitEvidenceSet, ArtifactBinding,
               ArtifactContent, ArtifactReplica, ArtifactVerificationReceipt,
               ArtifactVerificationJob, ArtifactStorageNamespace)
        .select_from(SubmissionBundleAdmission)
        .join(PreSubmitEvidenceSet, PreSubmitEvidenceSet.id == SubmissionBundleAdmission.pre_submit_evidence_set_id)
        .join(ArtifactBinding, ArtifactBinding.id == str(facts.binding_id))
        .join(ArtifactContent, ArtifactContent.id == SubmissionBundleAdmission.artifact_content_id)
        .join(ArtifactReplica, ArtifactReplica.id == SubmissionBundleAdmission.verified_replica_id)
        .join(ArtifactVerificationReceipt, ArtifactVerificationReceipt.id == SubmissionBundleAdmission.verification_receipt_id)
        .join(ArtifactVerificationJob, ArtifactVerificationJob.id == ArtifactVerificationReceipt.verification_job_id)
        .join(ArtifactStorageNamespace, ArtifactStorageNamespace.id == ArtifactReplica.storage_namespace_id)
        .where(SubmissionBundleAdmission.id == str(facts.admission_id),
               SubmissionBundleAdmission.project_id == str(request.project_id),
               SubmissionBundleAdmission.task_id == str(request.task_id))
        .execution_options(populate_existing=True)
    )).one_or_none()
    if row is None:
        raise PostSubmissionMaterializationUnavailable("post_submit_material_unavailable")
    admission, evidence, binding, content, replica, receipt, job, persisted = row
    context = facts.context
    if not (
        SubmissionAdmissionConsumptionService._art_lineage_is_intact(admission, evidence, content)
        and admission.status == "consumed"
        and admission.consumed_by_submission_id == str(facts.submission_id)
        and admission.consumed_by_submission_version == facts.submission_version
        and admission.assignment_id == str(facts.assignment_id)
        and admission.actor_profile_id == str(facts.contributor_id)
        and admission.predecessor_submission_id == (str(facts.predecessor_id) if facts.predecessor_id else None)
        and admission.predecessor_submission_version == facts.predecessor_version
        and binding.project_id == str(facts.project_id)
        and binding.resource_type == "submission"
        and binding.resource_id == str(facts.submission_id)
        and binding.logical_role == "submission_bundle_original"
        and binding.scope_version == 1
        and binding.content_id == content.id == str(facts.content_id)
        and content.media_type == "application/zip"
        and content.sha256 == request.content_sha256 == request.structural_input.package_hash
        and content.byte_count == request.byte_count
        and evidence.guide_version == context.guide_version
        and evidence.source_snapshot_id == str(context.source_id)
        and evidence.source_snapshot_sha256 == context.source_hash
        and evidence.effective_policy_id == str(context.effective_policy_id)
        and evidence.locked_artifact_policy_sha256 == context.effective_policy_hash
        and evidence.pre_submit_policy_id == str(context.pre_policy_id)
        and evidence.locked_checker_policy_sha256 == context.pre_policy_hash
        and replica.content_id == content.id
        and (replica.verification_state, replica.availability_state, replica.integrity_state)
        == ("verified", "available", "valid")
        and receipt.outcome == "verified"
        and receipt.observed_sha256 == content.sha256
        and receipt.observed_byte_count == content.byte_count
        and job.replica_id == replica.id
        and job.originating_put_attempt_id == admission.put_attempt_id
    ):
        raise PostSubmissionMaterializationUnavailable("post_submit_material_identity_mismatch")
    validate_artifact_replica_execution_namespace(
        replica=replica, persisted=persisted, namespace=namespace, store=store,
    )
    commitment = ArtifactCommitment(content.sha256, content.byte_count, content.media_type)
    if replica.provider_object_ref != artifact_provider_object_ref(commitment):
        raise PostSubmissionMaterializationUnavailable("post_submit_material_identity_mismatch")
    return PostSubmissionMaterialSelection(
        submission=facts, evidence_id=UUID(evidence.id), replica_id=UUID(replica.id),
        verification_receipt_id=UUID(receipt.id), verification_job_id=UUID(job.id),
        verification_generation=receipt.execution_generation,
        namespace_fingerprint=persisted.namespace_fingerprint, adapter=replica.adapter,
        provider_profile=replica.provider_profile, provider_object_ref=replica.provider_object_ref,
        sha256=content.sha256, byte_count=content.byte_count, media_type=content.media_type,
        semantic_manifest_id=UUID(admission.semantic_manifest_id),
        semantic_manifest_sha256=admission.semantic_manifest_sha256,
    )
