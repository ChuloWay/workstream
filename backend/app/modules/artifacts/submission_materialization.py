"""Hidden authorized materialization for one prepared contributor bundle."""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Protocol, final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.interfaces.external_checker_execution import (
    ExternalCheckerMaterialGrant,
)
from app.modules.artifacts.api import SubmissionBundlePreparationRequest
from app.modules.artifacts.schemas import ArtifactAuthorityDeniedError
from app.modules.artifacts.preparation import (
    ArtifactPreparationService,
    ExternalMaterialFile,
    ExternalMaterialGrantRequest,
)
from app.modules.artifacts.sources import PreparedArtifact
from app.modules.artifacts.pre_submit_evidence import (
    PreSubmitEvidenceInput,
    PreSubmitEvidenceContext,
    PreSubmitEvidenceConflict,
    PreSubmitExecutionCustody,
    PreSubmitExecutionResult,
    PreSubmitEvidencePersistenceRequest,
    PreSubmitEvidencePersistenceResult,
    PreSubmitEvidenceService,
)
from app.modules.artifacts.pre_submit_attempts import PreSubmitAttemptClaim, PreSubmitAttemptStore
from app.modules.artifacts.models import PreSubmitExecutionAttempt
from app.modules.artifacts.submission_archive import (
    SubmissionArchiveInspectionResult,
)
from app.modules.artifacts.submission_manifest import (
    SubmissionChangeGateResult,
    SubmissionManifest,
    build_submission_manifest,
)
from app.modules.artifacts.submission_authorization import (
    SubmissionBundlePreparationAuthorization,
)
from app.modules.checkers.api import (
    ALLOWED_PRE_SUBMIT_STORAGE_SCHEMES,
    EffectivePreSubmissionExecutionPlan,
    PreSubmissionExecutionFacts,
    PreSubmissionInfrastructureUnavailableError,
    SubmissionPacketView,
)
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
    WorkstreamDefaultCheckerInput,
    workstream_default_input_body,
)
from app.modules.checkers.api.external import (
    ExternalCheckerExecutionRequest,
    PreSubmitExternalCheckerIdentity,
    PreSubmitExternalCheckerMaterial,
)
from app.modules.checkers.api.external_policy import LockedExternalPreSubmitPolicy
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitExecutionAuthority,
    SelectedPreSubmitExecutionFacts,
    SelectedPreSubmitLeaseFacts,
    SelectedPreSubmitReservationFacts,
)
from app.modules.projects.api import ProjectLockedPolicyContextPort
from app.modules.projects.api import ProjectLockedPolicyContextFacts
from app.modules.tasks.api import TaskSubmissionContextFacts, TaskSubmissionContextPort


@dataclass(frozen=True, slots=True)
class PreparedBundleMaterializationRequest:
    """ART-private process-local prepared bytes and exact execution facts."""

    prepared_authorization: object
    task_id: UUID
    assignment_id: UUID
    submission_artifact_policy_id: UUID
    checker_policy_id: UUID
    predecessor_submission_version: int | None
    checker_remediation_manifest_id: UUID | None = field(default=None, kw_only=True)
    prepared_artifact: PreparedArtifact
    effective_plan: EffectivePreSubmissionExecutionPlan | None
    inspection: SubmissionArchiveInspectionResult
    manifest: SubmissionManifest
    change_gate: SubmissionChangeGateResult
    packet: SubmissionPacketView
    external_policy: LockedExternalPreSubmitPolicy | None = None
    default_checker_input: WorkstreamDefaultCheckerInput | None = None
    selected_reservation: SelectedPreSubmitReservationFacts | None = None


@dataclass(frozen=True, slots=True)
class PreSubmitCheckerExecutionRequest:
    """Exact process-local input supplied to the composition CHECKER adapter."""

    plan: EffectivePreSubmissionExecutionPlan | None
    project_id: UUID
    task_id: UUID
    assignment_id: UUID
    commitment: object
    inspection: SubmissionArchiveInspectionResult
    manifest: SubmissionManifest
    change_gate: SubmissionChangeGateResult
    packet: SubmissionPacketView
    prepared_generation_id: UUID
    storage_scheme: str
    external_policy: LockedExternalPreSubmitPolicy | None = None
    default_checker_input: WorkstreamDefaultCheckerInput | None = None
    attempt_id: UUID | None = None
    attempt_request_digest: str | None = None
    external_grants: "PreSubmitExternalGrantPort | None" = None


class PreSubmitExternalGrantPort(Protocol):
    """Issue one callback-scoped grant from genuine prepared ART custody."""

    def issue(
        self,
        request: ExternalCheckerExecutionRequest,
        workspace: Path,
    ) -> AbstractContextManager[ExternalCheckerMaterialGrant]: ...


@dataclass(frozen=True, slots=True)
class _SelectedGrantClaim:
    """Minimum genuine selected-run identity required by the ART grant issuer."""

    attempt_id: UUID
    request_digest: str


class _PreSubmitExternalGrantIssuer:
    """Keep private prepared-artifact authority behind a typed callback port."""

    def __init__(
        self,
        *,
        preparation: ArtifactPreparationService,
        prepared: PreparedArtifact,
        request: PreparedBundleMaterializationRequest,
        claim: PreSubmitAttemptClaim,
    ) -> None:
        self._preparation = preparation
        self._prepared = prepared
        self._request = request
        self._claim = claim

    @contextmanager
    def issue(
        self,
        request: ExternalCheckerExecutionRequest,
        workspace: Path,
    ):
        """Bind the service grant to exact claim, manifest and prepared bytes."""
        checked = ExternalCheckerExecutionRequest.model_validate(request)
        identity = checked.identity
        source = self._request
        project_id = (
            source.selected_reservation.project_id
            if source.selected_reservation is not None
            else source.effective_plan.lineage.project_id
            if source.effective_plan is not None
            else None
        )
        if (
            not isinstance(identity, PreSubmitExternalCheckerIdentity)
            or identity.project_id != project_id
            or identity.task_id != source.task_id
            or identity.assignment_id != source.assignment_id
            or identity.prepared_generation_id != source.prepared_artifact.generation_id
            or identity.attempt_id != self._claim.attempt_id
            or identity.attempt_request_digest != self._claim.request_digest
            or len(checked.materials) != 1
            or not isinstance(checked.materials[0], PreSubmitExternalCheckerMaterial)
        ):
            raise PreSubmitEvidenceConflict("pre_submit_external_request_invalid")
        material = checked.materials[0]
        commitment = source.prepared_artifact.commitment
        if (
            material.prepared_generation_id != source.prepared_artifact.generation_id
            or material.attempt_id != self._claim.attempt_id
            or material.attempt_request_digest != self._claim.request_digest
            or material.archive_sha256 != commitment.sha256
            or material.archive_byte_count != commitment.byte_count
            or material.semantic_manifest_sha256 != source.manifest.sha256
            or material.media_type != commitment.media_type
        ):
            raise PreSubmitEvidenceConflict("pre_submit_external_material_invalid")
        directories = tuple(
            item.normalized_path
            for item in source.manifest.entries
            if item.entry_type.value == "directory"
        )
        files = tuple(
            ExternalMaterialFile(
                normalized_path=item.normalized_path,
                byte_count=item.byte_count,
                sha256=item.sha256 or "",
                executable=bool(item.executable),
            )
            for item in source.manifest.entries
            if item.entry_type.value == "file"
        )
        grant_request = ExternalMaterialGrantRequest(
            request_digest=checked.request_digest,
            prepared_generation_id=str(identity.prepared_generation_id),
            attempt_id=str(identity.attempt_id),
            attempt_request_digest=identity.attempt_request_digest,
            archive_sha256=material.archive_sha256,
            archive_byte_count=material.archive_byte_count,
            semantic_manifest_sha256=material.semantic_manifest_sha256,
            directories=directories,
            files=files,
        )
        with self._preparation.external_material_grant(
            self._prepared, workspace, grant_request
        ) as grant:
            yield ExternalCheckerMaterialGrant(
                grant_id=grant.grant_id,
                binding_digest=grant.binding_digest,
            )


class PreSubmissionEvaluationPort(Protocol):
    """Finish ART's committed selection through the composed checker phase service."""

    async def evaluate_pre_submission(
        self,
        request: PreparedBundleMaterializationRequest,
        reservation: object,
        *,
        preparation_request: SubmissionBundlePreparationRequest,
    ) -> PreSubmitEvidencePersistenceResult: ...


class PreSubmitCheckerProcessor(Protocol):
    """Async processor built by the composition-root CHECKER adapter."""

    def abort(self) -> None: ...

    async def process(self, reader: object, workspace: object) -> PreSubmissionExecutionFacts: ...


class PreSubmitCheckerExecutionFactory(Protocol):
    """Build one process-local CHECKER processor without private imports in ART."""

    @property
    def catalogue_manifest_sha256(self) -> str: ...

    def build(self, request: PreSubmitCheckerExecutionRequest) -> PreSubmitCheckerProcessor: ...


@dataclass(frozen=True, slots=True)
class PreSubmitMaterializationPreparationFacts:
    """Exact scalar facts available before any ZIP inspection."""

    task_id: UUID
    assignment_id: UUID
    project_id: UUID
    guide_id: UUID
    guide_version: str
    source_snapshot_id: UUID
    source_snapshot_hash: str
    submission_artifact_policy_id: UUID
    submission_artifact_policy_hash: str
    checker_policy_id: UUID
    checker_policy_hash: str
    prepared_generation_id: UUID
    plan_sha256: str
    catalogue_manifest_sha256: str
    archive_sha256: str
    archive_byte_count: int
    storage_scheme: str


@final
@dataclass(frozen=True, slots=True)
class PreSubmitMaterializationAuthorityFacts(PreSubmitMaterializationPreparationFacts):
    """Exact inspected resource facts consumed before scratch exposure."""

    semantic_manifest_sha256: str

    @property
    def preparation(self) -> PreSubmitMaterializationPreparationFacts:
        """Return the exact pre-inspection projection of the final facts."""
        return PreSubmitMaterializationPreparationFacts(
            task_id=self.task_id,
            assignment_id=self.assignment_id,
            project_id=self.project_id,
            guide_id=self.guide_id,
            guide_version=self.guide_version,
            source_snapshot_id=self.source_snapshot_id,
            source_snapshot_hash=self.source_snapshot_hash,
            submission_artifact_policy_id=self.submission_artifact_policy_id,
            submission_artifact_policy_hash=self.submission_artifact_policy_hash,
            checker_policy_id=self.checker_policy_id,
            checker_policy_hash=self.checker_policy_hash,
            prepared_generation_id=self.prepared_generation_id,
            plan_sha256=self.plan_sha256,
            catalogue_manifest_sha256=self.catalogue_manifest_sha256,
            archive_sha256=self.archive_sha256,
            archive_byte_count=self.archive_byte_count,
            storage_scheme=self.storage_scheme,
        )


class PreSubmitMaterializationAuthorization(Protocol):
    """Adapter over AUTH's opaque transaction-bound prepared capability."""

    async def prepare(
        self,
        *,
        facts: PreSubmitMaterializationPreparationFacts,
        idempotency_key: UUID,
    ) -> object:
        """Prepare an opaque capability before any submitted byte is inspected."""
        ...

    async def consume(
        self,
        *,
        prepared_authorization: object,
        facts: PreSubmitMaterializationAuthorityFacts,
    ) -> None:
        """Consume the capability against the server-computed final facts."""
        ...


class DenyPreSubmitMaterializationAuthorization:
    """Keep production byte access unavailable until XINT-06A activation."""

    async def prepare(
        self,
        *,
        facts: PreSubmitMaterializationPreparationFacts,
        idempotency_key: UUID,
    ) -> object:
        """Deny capability preparation while the production adapter is absent."""
        del facts, idempotency_key
        raise ArtifactAuthorityDeniedError(
            "pre-submit checker input materialization is unavailable"
        )

    async def consume(
        self,
        *,
        prepared_authorization: object,
        facts: PreSubmitMaterializationAuthorityFacts,
    ) -> None:
        """Deny capability consumption while the production adapter is absent."""
        del prepared_authorization, facts
        raise ArtifactAuthorityDeniedError(
            "pre-submit checker input materialization is unavailable"
        )


class PreparedBundleMaterializationService:
    """Authorize, project, execute, and clean one process-local bundle."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        authorization: PreSubmitMaterializationAuthorization,
        preparation: ArtifactPreparationService,
        checker_execution: PreSubmitCheckerExecutionFactory,
        storage_scheme: str,
    ) -> None:
        """Compose the bounded materializer from its AUTH and ART dependencies."""
        self._session = session
        self._authorization = authorization
        self._preparation = preparation
        self._checker_execution = checker_execution
        if storage_scheme not in ALLOWED_PRE_SUBMIT_STORAGE_SCHEMES:
            raise ValueError("pre-submit materializer storage scheme is invalid")
        self._storage_scheme = storage_scheme

    async def authorize_prepared_bundle(
        self,
        request: PreparedBundleMaterializationRequest,
        *,
        claim: PreSubmitAttemptClaim,
    ) -> None:
        """Consume fixed-service authority and the durable claim in its short root."""
        if type(claim) is not PreSubmitAttemptClaim:
            raise PreSubmitEvidenceConflict("pre_submit_attempt_claim_invalid")
        facts = self._authority_facts(request)
        await self._authorization.consume(
            prepared_authorization=request.prepared_authorization,
            facts=facts,
        )
        await claim.consume(self._session, request)

    async def materialize_prepared_bundle(
        self,
        request: PreparedBundleMaterializationRequest,
        *,
        claim: PreSubmitAttemptClaim,
    ) -> PreSubmitExecutionResult:
        """Execute only after the authority root commits; no external work holds DB locks."""
        if type(claim) is not PreSubmitAttemptClaim:
            raise PreSubmitEvidenceConflict("pre_submit_attempt_claim_invalid")
        if request.effective_plan is None:
            raise PreSubmitEvidenceConflict("pre_submit_effective_plan_invalid")
        claim.require_execution(self._session, request)
        processor = self._checker_execution.build(
            PreSubmitCheckerExecutionRequest(
                plan=request.effective_plan,
                project_id=request.effective_plan.lineage.project_id,
                task_id=request.task_id,
                assignment_id=request.assignment_id,
                commitment=request.prepared_artifact.commitment,
                inspection=request.inspection,
                manifest=request.manifest,
                change_gate=request.change_gate,
                packet=request.packet,
                prepared_generation_id=request.prepared_artifact.generation_id,
                storage_scheme=self._storage_scheme,
                external_policy=request.external_policy,
                default_checker_input=request.default_checker_input,
                attempt_id=claim.attempt_id,
                attempt_request_digest=claim.request_digest,
                external_grants=_PreSubmitExternalGrantIssuer(
                    preparation=self._preparation,
                    prepared=request.prepared_artifact,
                    request=request,
                    claim=claim,
                ),
            ),
        )
        # Intentional friend call: this is the sole authority-gated caller, and
        # the preparation byte-access surface must remain private.
        checker_facts = await self._preparation._process_prepared_submission(
            request.prepared_artifact,
            processor,
            reserved_bytes=request.manifest.total_expanded_bytes,
            # ART's external grant nests the verified tree below one owned mount.
            maximum_entries=request.manifest.entry_count + 1,
        )
        execution = PreSubmitExecutionResult(
            custody=PreSubmitExecutionCustody(
                prepared_generation_id=request.prepared_artifact.generation_id,
                archive_sha256=request.prepared_artifact.commitment.sha256,
                archive_byte_count=request.prepared_artifact.commitment.byte_count,
                semantic_manifest_sha256=request.manifest.sha256,
                storage_scheme=self._storage_scheme,
            ),
            checker_facts=checker_facts,
        )
        claim.finish(execution)
        return execution

    async def materialize_selected_pre_submit(
        self,
        request: PreparedBundleMaterializationRequest,
        *,
        run_id: UUID,
        lease: SelectedPreSubmitLeaseFacts,
        execution_authority: SelectedPreSubmitExecutionAuthority,
    ) -> SelectedPreSubmitExecutionFacts:
        """Execute the committed selected lease without the legacy invocation store."""
        if self._session.in_transaction():
            raise RuntimeError("selected pre-submit execution requires no transaction")
        checked = execution_authority.consume(run_id=run_id, lease=lease)
        reservation = checked.reservation
        commitment = request.prepared_artifact.commitment
        if (
            run_id != reservation.attempt_id
            or request.task_id != reservation.task_id
            or request.assignment_id != reservation.assignment_id
            or request.selected_reservation != reservation
            or request.prepared_artifact.generation_id != reservation.prepared_generation_id
            or request.external_policy is None
            or request.external_policy.policy_sha256 != reservation.policy_sha256
            or request.default_checker_input is None
            or canonical_json_hash(workstream_default_input_body(request.default_checker_input))
            != reservation.default_input_sha256
            or commitment.sha256 != reservation.archive_sha256
            or commitment.byte_count != reservation.archive_byte_count
            or request.manifest.sha256 != reservation.semantic_manifest_sha256
        ):
            raise PreSubmitEvidenceConflict("selected_pre_submit_execution_invalid")
        processor = self._checker_execution.build(
            PreSubmitCheckerExecutionRequest(
                plan=request.effective_plan,
                project_id=reservation.project_id,
                task_id=request.task_id,
                assignment_id=request.assignment_id,
                commitment=commitment,
                inspection=request.inspection,
                manifest=request.manifest,
                change_gate=request.change_gate,
                packet=request.packet,
                prepared_generation_id=request.prepared_artifact.generation_id,
                storage_scheme=self._storage_scheme,
                external_policy=request.external_policy,
                default_checker_input=request.default_checker_input,
                attempt_id=run_id,
                attempt_request_digest=reservation.request_digest,
                external_grants=_PreSubmitExternalGrantIssuer(
                    preparation=self._preparation,
                    prepared=request.prepared_artifact,
                    request=request,
                    claim=_SelectedGrantClaim(
                        attempt_id=run_id,
                        request_digest=reservation.request_digest,
                    ),
                ),
            )
        )
        result = await self._preparation._process_prepared_submission(
            request.prepared_artifact,
            processor,
            reserved_bytes=request.manifest.total_expanded_bytes,
            maximum_entries=request.manifest.entry_count + 1,
        )
        if type(result) is not SelectedPreSubmitExecutionFacts:
            raise PreSubmitEvidenceConflict("selected_pre_submit_execution_invalid")
        return result

    async def authorize_inspected(self, request: PreparedBundleMaterializationRequest) -> None:
        """Authorize inspected custody for reservation without invoking checker members."""
        await self._authorization.consume(
            prepared_authorization=request.prepared_authorization,
            facts=self._authority_facts(request),
        )

    async def authorize_original_replay(
        self,
        request: PreparedBundleMaterializationRequest,
        *,
        generation_id: UUID,
        key: UUID,
    ) -> None:
        """Check original stored service facts; this grants no retry-byte capability."""
        facts = replace(self._authority_facts(request), prepared_generation_id=generation_id)
        handle = await self._authorization.prepare(facts=facts.preparation, idempotency_key=key)
        await self._authorization.consume(prepared_authorization=handle, facts=facts)

    async def prepare_authorization(
        self,
        *,
        task_id: UUID,
        assignment_id: UUID,
        submission_artifact_policy_id: UUID,
        checker_policy_id: UUID,
        prepared_artifact: PreparedArtifact,
        effective_plan: EffectivePreSubmissionExecutionPlan | None,
        idempotency_key: UUID,
        external_policy: LockedExternalPreSubmitPolicy | None = None,
        selected_reservation: SelectedPreSubmitReservationFacts | None = None,
    ) -> object:
        """Deny unavailable service authority before inspecting the ZIP."""
        facts = self._preparation_facts(
            task_id=task_id,
            assignment_id=assignment_id,
            submission_artifact_policy_id=submission_artifact_policy_id,
            checker_policy_id=checker_policy_id,
            prepared_artifact=prepared_artifact,
            effective_plan=effective_plan,
            external_policy=external_policy,
            selected_reservation=selected_reservation,
        )
        return await self._authorization.prepare(
            facts=facts,
            idempotency_key=idempotency_key,
        )

    async def prepare_selected_authorization(
        self,
        *,
        task: TaskSubmissionContextFacts,
        project: ProjectLockedPolicyContextFacts,
        prepared_artifact: PreparedArtifact,
        external_policy: LockedExternalPreSubmitPolicy,
        idempotency_key: UUID,
    ) -> object:
        """Prepare selected material authority before inspecting contributor bytes."""
        references = task.locked_project_context
        commitment = prepared_artifact.commitment
        if (
            task.task_id is None
            or task.assignment_id is None
            or references.project_id != project.project_id
            or references.guide_version != project.guide_version
            or references.source_snapshot_id != project.source_snapshot_id
            or references.source_snapshot_hash != project.source_snapshot_hash
            or references.effective_policy_id != project.effective_policy_id
            or references.effective_policy_hash != project.effective_policy_hash
            or references.pre_submit_policy_id != project.pre_submit_policy_id
            or references.pre_submit_policy_bundle_hash != project.pre_submit_policy_bundle_hash
            or external_policy.policy_sha256
            != canonical_json_hash(
                external_policy.model_dump(mode="json", exclude={"policy_sha256"})
            )
            or external_policy.workstream_default.behavior_sha256
            != WORKSTREAM_DEFAULT_BEHAVIOR_SHA256
        ):
            raise PreSubmissionInfrastructureUnavailableError(
                "selected_pre_submission_materialization_context_invalid"
            )
        facts = PreSubmitMaterializationPreparationFacts(
            task_id=task.task_id,
            assignment_id=task.assignment_id,
            project_id=project.project_id,
            guide_id=project.guide_id,
            guide_version=project.guide_version,
            source_snapshot_id=project.source_snapshot_id,
            source_snapshot_hash=project.source_snapshot_hash,
            submission_artifact_policy_id=project.effective_policy_id,
            submission_artifact_policy_hash=project.effective_policy_hash,
            checker_policy_id=project.pre_submit_policy_id,
            checker_policy_hash=project.pre_submit_policy_bundle_hash,
            prepared_generation_id=prepared_artifact.generation_id,
            plan_sha256=external_policy.policy_sha256,
            catalogue_manifest_sha256=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
            archive_sha256=commitment.sha256,
            archive_byte_count=commitment.byte_count,
            storage_scheme=self._storage_scheme,
        )
        return await self._authorization.prepare(
            facts=facts,
            idempotency_key=idempotency_key,
        )

    def _authority_facts(
        self,
        request: PreparedBundleMaterializationRequest,
    ) -> PreSubmitMaterializationAuthorityFacts:
        """Build final authority facts from the canonical inspected manifest."""
        plan = request.effective_plan
        preparation = self._preparation_facts(
            task_id=request.task_id,
            assignment_id=request.assignment_id,
            submission_artifact_policy_id=request.submission_artifact_policy_id,
            checker_policy_id=request.checker_policy_id,
            prepared_artifact=request.prepared_artifact,
            effective_plan=plan,
            external_policy=request.external_policy,
            selected_reservation=request.selected_reservation,
        )
        if (
            request.manifest != request.change_gate.manifest
            or build_submission_manifest(request.inspection) != request.manifest
            or request.prepared_artifact.commitment.sha256 != request.change_gate.archive_sha256
            or request.prepared_artifact.commitment.byte_count
            != request.change_gate.archive_byte_count
        ):
            raise PreSubmissionInfrastructureUnavailableError(
                "pre_submission_materialization_context_invalid"
            )
        return PreSubmitMaterializationAuthorityFacts(
            **asdict(preparation),
            semantic_manifest_sha256=request.manifest.sha256,
        )

    def _preparation_facts(
        self,
        *,
        task_id: UUID,
        assignment_id: UUID,
        submission_artifact_policy_id: UUID,
        checker_policy_id: UUID,
        prepared_artifact: PreparedArtifact,
        effective_plan: EffectivePreSubmissionExecutionPlan | None,
        external_policy: LockedExternalPreSubmitPolicy | None = None,
        selected_reservation: SelectedPreSubmitReservationFacts | None = None,
    ) -> PreSubmitMaterializationPreparationFacts:
        """Build pre-inspection facts from locked lineage and byte commitment."""
        plan = effective_plan
        if selected_reservation is not None:
            lineage = selected_reservation.admission_lineage
            commitment = prepared_artifact.commitment
            if (
                plan is not None
                or lineage is None
                or external_policy is None
                or task_id != selected_reservation.task_id
                or assignment_id != selected_reservation.assignment_id
                or prepared_artifact.generation_id != selected_reservation.prepared_generation_id
                or submission_artifact_policy_id != lineage.effective_policy_id
                or checker_policy_id != lineage.pre_submit_policy_id
                or external_policy.policy_sha256 != selected_reservation.policy_sha256
                or commitment.sha256 != selected_reservation.archive_sha256
                or commitment.byte_count != selected_reservation.archive_byte_count
            ):
                raise PreSubmissionInfrastructureUnavailableError(
                    "selected_pre_submission_materialization_context_invalid"
                )
            return PreSubmitMaterializationPreparationFacts(
                task_id=task_id,
                assignment_id=assignment_id,
                project_id=selected_reservation.project_id,
                guide_id=lineage.guide_id,
                guide_version=lineage.guide_version,
                source_snapshot_id=lineage.source_snapshot_id,
                source_snapshot_hash=lineage.source_snapshot_sha256,
                submission_artifact_policy_id=submission_artifact_policy_id,
                submission_artifact_policy_hash=lineage.effective_policy_sha256,
                checker_policy_id=checker_policy_id,
                checker_policy_hash=lineage.pre_submit_policy_sha256,
                prepared_generation_id=prepared_artifact.generation_id,
                plan_sha256=selected_reservation.policy_sha256,
                catalogue_manifest_sha256=(selected_reservation.default_behavior_sha256),
                archive_sha256=commitment.sha256,
                archive_byte_count=commitment.byte_count,
                storage_scheme=self._storage_scheme,
            )
        if plan is None:
            raise PreSubmissionInfrastructureUnavailableError(
                "pre_submission_materialization_context_invalid"
            )
        if plan.plan_sha256 != canonical_json_hash(plan.as_dict()):
            raise PreSubmissionInfrastructureUnavailableError(
                "pre_submission_plan_identity_invalid"
            )
        if (
            submission_artifact_policy_id != plan.lineage.effective_policy_id
            or checker_policy_id != plan.lineage.pre_submit_policy_id
            or (
                external_policy is None
                and plan.catalogue_manifest_sha256
                != self._checker_execution.catalogue_manifest_sha256
            )
        ):
            raise PreSubmissionInfrastructureUnavailableError(
                "pre_submission_materialization_context_invalid"
            )
        if external_policy is not None and (
            external_policy.policy_sha256
            != canonical_json_hash(
                external_policy.model_dump(mode="json", exclude={"policy_sha256"})
            )
            or external_policy.workstream_default.behavior_sha256
            != WORKSTREAM_DEFAULT_BEHAVIOR_SHA256
        ):
            raise PreSubmissionInfrastructureUnavailableError("external_pre_submit_policy_invalid")
        commitment = prepared_artifact.commitment
        return PreSubmitMaterializationPreparationFacts(
            task_id=task_id,
            assignment_id=assignment_id,
            project_id=plan.lineage.project_id,
            guide_id=plan.lineage.guide_id,
            guide_version=plan.lineage.guide_version,
            source_snapshot_id=plan.lineage.source_snapshot_id,
            source_snapshot_hash=plan.lineage.source_snapshot_hash,
            submission_artifact_policy_id=submission_artifact_policy_id,
            submission_artifact_policy_hash=plan.lineage.effective_policy_hash,
            checker_policy_id=checker_policy_id,
            checker_policy_hash=plan.lineage.pre_submit_policy_bundle_hash,
            prepared_generation_id=prepared_artifact.generation_id,
            plan_sha256=plan.plan_sha256,
            catalogue_manifest_sha256=plan.catalogue_manifest_sha256,
            archive_sha256=commitment.sha256,
            archive_byte_count=commitment.byte_count,
            storage_scheme=self._storage_scheme,
        )


class PreparedBundlePreSubmitEvidenceService:
    """Execute in scratch, then persist exact evidence in a fresh transaction."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        materialization: PreparedBundleMaterializationService,
        preparation_authorization: SubmissionBundlePreparationAuthorization,
        task_contexts: TaskSubmissionContextPort,
        project_contexts: ProjectLockedPolicyContextPort,
    ) -> None:
        """Bind execution to the transaction used for durable evidence."""
        self._session = session
        self._materialization = materialization
        self._preparation_authorization = preparation_authorization
        self._task_contexts = task_contexts
        self._project_contexts = project_contexts
        self._attempts = PreSubmitAttemptStore(session)

    def _evidence_service(self) -> PreSubmitEvidenceService:
        """Use the sole evidence owner for both lineage reads and completion."""
        return PreSubmitEvidenceService(
            self._session,
            task_contexts=self._task_contexts,
            project_contexts=self._project_contexts,
        )

    @staticmethod
    def _input(
        request: PreparedBundleMaterializationRequest,
        preparation_request: SubmissionBundlePreparationRequest,
    ) -> PreSubmitEvidenceInput:
        if (
            request.task_id != preparation_request.task_id
            or request.assignment_id != preparation_request.assignment_id
            or request.packet.summary != preparation_request.summary
            or request.packet.contributor_attestation != preparation_request.contributor_attestation
        ):
            raise PreSubmitEvidenceConflict("pre_submit_attempt_request_conflict")
        commitment = request.prepared_artifact.commitment
        return PreSubmitEvidenceInput(
            actor_profile_id=preparation_request.actor.actor_profile_id,
            identity_link_id=preparation_request.actor.identity_link_id,
            task_id=request.task_id,
            assignment_id=request.assignment_id,
            predecessor_submission_id=preparation_request.predecessor_submission_id,
            expected_predecessor_submission_version=request.predecessor_submission_version,
            expected_checker_remediation_manifest_id=(
                request.checker_remediation_manifest_id
            ),
            prepared_generation_id=request.prepared_artifact.generation_id,
            archive_sha256=commitment.sha256,
            archive_byte_count=commitment.byte_count,
            semantic_manifest_sha256=request.manifest.sha256,
            plan=request.effective_plan,
        )

    async def _lock_authorized_context(
        self,
        request: PreparedBundleMaterializationRequest,
        preparation_request: SubmissionBundlePreparationRequest,
    ) -> PreSubmitEvidenceContext:
        """Match TASK, AUTH role issuance and revocation without reversing their locks."""
        evidence = self._evidence_service()
        values = self._input(request, preparation_request)
        task_context = await evidence.lock_task_context(values)
        await self._preparation_authorization.lock_actor(request=preparation_request)
        context = await evidence.lock_project_context(
            values,
            task_context=task_context,
            storage_scheme=self._materialization._storage_scheme,
        )
        await self._preparation_authorization.revalidate(request=preparation_request)
        return context

    async def reserve(
        self,
        request: PreparedBundleMaterializationRequest,
        *,
        preparation_request: SubmissionBundlePreparationRequest,
    ) -> object:
        """Consume inspected authority and reserve; the caller must commit before execution."""
        context = await self._lock_authorized_context(request, preparation_request)
        await self._materialization.authorize_inspected(request)
        selected = await self._attempts.reserve(
            context=context,
            plan=request.effective_plan,
            packet=request.packet,
            idempotency_key=preparation_request.idempotency_key,
            request=request,
        )
        if isinstance(selected, PreSubmitExecutionAttempt):
            await self._materialization.authorize_original_replay(
                request,
                generation_id=UUID(selected.prepared_generation_id),
                key=preparation_request.idempotency_key,
            )
            return await self._attempts.read_completed(
                row=selected,
                context=context,
                plan=request.effective_plan,
            )
        return selected

    async def execute_reserved(
        self,
        request: PreparedBundleMaterializationRequest,
        reservation: object,
        *,
        preparation_request: SubmissionBundlePreparationRequest,
    ) -> PreSubmitEvidencePersistenceResult:
        """Run a committed winning claim, then atomically persist its canonical evidence."""
        if self._session.in_transaction():
            raise RuntimeError("pre-submit execution requires a transaction-free session")
        claim = await self._attempts.committed_claim(reservation)
        authorized_request = None
        async with self._session.begin():
            await self._lock_authorized_context(request, preparation_request)
            handle = await self._materialization.prepare_authorization(
                task_id=request.task_id,
                assignment_id=request.assignment_id,
                submission_artifact_policy_id=request.submission_artifact_policy_id,
                checker_policy_id=request.checker_policy_id,
                prepared_artifact=request.prepared_artifact,
                effective_plan=request.effective_plan,
                idempotency_key=preparation_request.idempotency_key,
                external_policy=request.external_policy,
            )
            authorized_request = replace(request, prepared_authorization=handle)
            await self._materialization.authorize_prepared_bundle(
                authorized_request,
                claim=claim,
            )
        assert authorized_request is not None
        execution = await self._materialization.materialize_prepared_bundle(
            replace(authorized_request, prepared_authorization=None),
            claim=claim,
        )
        async with self._session.begin():
            await self._session.execute(text("set transaction isolation level read committed"))
            values = self._input(request, preparation_request)
            await self._lock_authorized_context(request, preparation_request)
            return await self._evidence_service().persist(
                PreSubmitEvidencePersistenceRequest(
                    **{name: getattr(values, name) for name in values.__dataclass_fields__},
                    execution=execution,
                    attempt=claim,
                    manifest=request.manifest,
                )
            )
