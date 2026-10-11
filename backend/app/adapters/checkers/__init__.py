"""CHECKER-owned composition adapters."""

import asyncio
import json
from app.adapters.checkers.external_service import (
    EXTERNAL_CHECKER_CAPABILITY_KEY,
    EXTERNAL_CHECKER_PROVIDER_KEY,
    UnixSocketExternalCheckerAdapter,
)
from app.interfaces.external_services import ExternalServiceAdapterFactory
from app.modules.artifacts.api import SubmissionBundleFile
from app.modules.tasks.api import TaskSubmissionContextFacts
from app.modules.projects.api import ProjectLockedPolicyContextFacts
from app.modules.checkers.api import SubmissionPacketView
from app.modules.checkers.api.artifact_paths import required_evidence_path
from app.modules.checkers.api.post_submit_catalogue import CompiledPostSubmitPolicy
from app.modules.checkers.api.post_submit import (
    PostSubmissionEvaluationContent, ExpectedPostSubmitContext, ObservedPostSubmitContext,
    PostSubmitPolicyInputs, PostSubmissionStructuralInput, PostSubmitManifestEntry, PostSubmitEvidenceEntry,
)
from app.modules.checkers.api.external_policy import LockedExternalPostSubmitPolicy
from app.modules.checkers.api.selected_post_submit import (
    SelectedPostSubmissionContent,
    SelectedPostSubmitLockedContext,
)
from app.modules.checkers.api.history import CheckerHistoryReadPort
from app.modules.checkers.api.execution import EvaluationCoordinationPort
from typing import Any, BinaryIO, Protocol
from pathlib import Path

from app.modules.checkers.api.pre_submit_catalogue import PreSubmissionCapabilityProjection
from app.modules.checkers.api.post_submit_catalogue import PostSubmitCatalogue
from app.modules.checkers.api.policy_compilation import PreSubmissionPolicyCompilationPort

from app.modules.checkers.api import (
    PreSubmissionExecutionFacts,
    PreSubmissionInfrastructureUnavailableError,
)
from app.modules.checkers.catalogue import (
    PreSubmissionCheckerCatalogue,
    project_guide_pre_submission_capabilities,
    build_pre_submission_checker_catalogue,
    parse_disabled_pre_submission_checker_ids,
)
from app.modules.checkers.pre_submit_execution import (
    DefaultPreSubmissionExecutionError,
    DefaultPreSubmissionExecutionInput,
    EffectivePreSubmissionProcessor,
)
from app.modules.checkers.api.external import (
    PreSubmitExternalCheckerIdentity,
    PreSubmitExternalCheckerMaterial,
)
from app.modules.checkers.selected_pre_submit_execution import SelectedPreSubmitProcessor


def external_checker_execution_factory(
    *, socket_path: Path, timeout_seconds: float
) -> ExternalServiceAdapterFactory[UnixSocketExternalCheckerAdapter]:
    """Compose the unselected instance-local external checker adapter factory."""
    factory = ExternalServiceAdapterFactory[UnixSocketExternalCheckerAdapter](
        EXTERNAL_CHECKER_CAPABILITY_KEY
    )
    factory.register(
        EXTERNAL_CHECKER_PROVIDER_KEY,
        lambda: UnixSocketExternalCheckerAdapter(
            socket_path=socket_path,
            timeout_seconds=timeout_seconds,
        ),
    )
    return factory


def configured_external_checker_execution_factory(settings):
    """Map validated settings into the unselected explicit adapter factory."""
    if (
        settings.external_checker_service_socket is None
        or settings.external_checker_material_root is None
    ):
        raise ValueError("external checker service is not configured")
    return external_checker_execution_factory(
        socket_path=settings.external_checker_service_socket,
        timeout_seconds=float(settings.external_checker_service_timeout_seconds),
    )


def selected_pre_submit_checker_execution(*, settings, archive_inspector):
    """Compose the sole selected PRE runtime from the configured Rust service."""
    execution = configured_external_checker_execution_factory(settings).create(
        EXTERNAL_CHECKER_PROVIDER_KEY
    )
    return SelectedPreSubmitCheckerExecutionAdapter(
        archive_inspector=archive_inspector,
        external_execution=execution,
    )


def external_checker_registry_reader(session):
    """Resolve immutable metadata for trusted approval and execution owners."""
    from app.modules.checkers.external_registry import ExternalCheckerRegistryReader

    return ExternalCheckerRegistryReader(session)


class _ExecutionRequest(Protocol):
    plan: Any
    project_id: Any
    task_id: Any
    assignment_id: Any
    commitment: Any
    inspection: Any
    manifest: Any
    change_gate: Any
    packet: Any
    prepared_generation_id: Any
    storage_scheme: str


class _PublicFactsCheckerProcessor:
    """Project the private CHECKER processor result to public facts."""

    def __init__(self, processor: EffectivePreSubmissionProcessor) -> None:
        self._processor = processor

    def abort(self) -> None:
        self._processor.abort()

    async def process(self, reader: BinaryIO, workspace: Path) -> PreSubmissionExecutionFacts:
        try:
            result = await asyncio.to_thread(self._processor.process_blocking, reader, workspace)
            return result.bounded_facts()
        except DefaultPreSubmissionExecutionError as exc:
            raise PreSubmissionInfrastructureUnavailableError(str(exc)) from exc


class PreSubmitCheckerExecutionAdapter:
    """Build the private CHECKER processor behind dependency-safe facts."""

    def __init__(self, *, catalogue: PreSubmissionCheckerCatalogue, archive_inspector: Any):
        self._catalogue = catalogue
        self._archive_inspector = archive_inspector

    @property
    def catalogue_manifest_sha256(self) -> str:
        return self._catalogue.manifest_sha256

    def build(self, request: _ExecutionRequest) -> _PublicFactsCheckerProcessor:
        if request.plan is None:
            raise PreSubmissionInfrastructureUnavailableError(
                "pre_submission_plan_identity_invalid"
            )
        return _PublicFactsCheckerProcessor(
            EffectivePreSubmissionProcessor(
                archive_inspector=self._archive_inspector,
                catalogue=self._catalogue,
                execution_input=DefaultPreSubmissionExecutionInput(
                    plan=request.plan,
                    commitment=request.commitment,
                    inspection=request.inspection,
                    manifest=request.manifest,
                    change_gate=request.change_gate,
                    packet=request.packet,
                    prepared_generation_id=request.prepared_generation_id,
                    storage_scheme=request.storage_scheme,
                ),
            )
        )


class SelectedPreSubmitCheckerExecutionAdapter:
    """Build the selected default-plus-external PRE processor from exact ART facts."""

    def __init__(self, *, archive_inspector, external_execution) -> None:
        self._archive_inspector = archive_inspector
        self._external_execution = external_execution

    def build(self, request: _ExecutionRequest) -> SelectedPreSubmitProcessor:
        """Reject any incomplete pre-admission identity before projecting bytes."""
        policy = getattr(request, "external_policy", None)
        default_input = getattr(request, "default_checker_input", None)
        attempt_id = getattr(request, "attempt_id", None)
        attempt_request_digest = getattr(request, "attempt_request_digest", None)
        grants = getattr(request, "external_grants", None)
        if (
            policy is None
            or default_input is None
            or attempt_id is None
            or attempt_request_digest is None
            or grants is None
        ):
            raise PreSubmissionInfrastructureUnavailableError(
                "external_pre_submit_context_unavailable"
            )
        identity = PreSubmitExternalCheckerIdentity(
            project_id=request.project_id,
            task_id=request.task_id,
            assignment_id=request.assignment_id,
            prepared_generation_id=request.prepared_generation_id,
            attempt_id=attempt_id,
            attempt_request_digest=attempt_request_digest,
            effective_plan_sha256=policy.policy_sha256,
        )
        material = PreSubmitExternalCheckerMaterial(
            role="submission_archive",
            prepared_generation_id=request.prepared_generation_id,
            attempt_id=attempt_id,
            attempt_request_digest=attempt_request_digest,
            archive_sha256=request.commitment.sha256,
            archive_byte_count=request.commitment.byte_count,
            semantic_manifest_sha256=request.manifest.sha256,
            media_type="application/zip",
        )
        return SelectedPreSubmitProcessor(
            archive_inspector=self._archive_inspector,
            inspection=request.inspection,
            policy=policy,
            default_input=default_input,
            identity=identity,
            material=material,
            grants=grants,
            execution=self._external_execution,
        )


def project_guide_pre_submission_catalogue() -> PreSubmissionCapabilityProjection:
    """Compose the canonical immutable pre-submit capabilities for guide setup."""
    return project_guide_pre_submission_capabilities(build_pre_submission_checker_catalogue())


def project_guide_approval_compiler(*, disabled_checker_ids: str = "") -> tuple[
    PreSubmissionPolicyCompilationPort, PreSubmissionCapabilityProjection, PostSubmitCatalogue,
]:
    """Compose one canonical planner and its matching pre/post capabilities."""
    from app.modules.checkers.api.post_submit_catalogue import current_post_submit_catalogue

    planner = build_pre_submission_checker_catalogue(
        disabled_entry_ids=parse_disabled_pre_submission_checker_ids(disabled_checker_ids),
    )
    return planner, project_guide_pre_submission_capabilities(planner), current_post_submit_catalogue()


def installed_post_submit_catalogue() -> PostSubmitCatalogue:
    """Resolve catalogue facts only after checking the installed handler registry."""
    from app.modules.checkers.post_submit_catalogue import build_post_submit_catalogue
    from app.modules.checkers.runner import default_checker_registry

    return build_post_submit_catalogue(default_checker_registry())


def checker_history_repository(session) -> CheckerHistoryReadPort:
    """Compose retained CHECKERS reads through TASK's public ownership port."""
    from app.modules.checkers.history import CheckerHistoryRepository
    return CheckerHistoryRepository(session)


def evaluation_coordinator(session) -> EvaluationCoordinationPort:
    """Compose required TASK locking before CHECKERS reservation custody."""
    from app.modules.checkers.execution_coordination import EvaluationCoordinator
    from app.adapters.tasks import evaluation_task_guard

    return EvaluationCoordinator(session, tasks=evaluation_task_guard(session))


def post_submission_executor(*, sessions, materialization):
    """Compose the sole executor with exact fixed-service AUTH at both phases."""
    from app.adapters.outbox import outbox_append
    from app.modules.checkers.execution import PostSubmissionExecutor
    from app.adapters.auth import post_submit_execution_authority
    from app.modules.checkers.runner import default_checker_registry
    return PostSubmissionExecutor(sessions=sessions, materialization=materialization,
        execute_authority=post_submit_execution_authority,
        finalize_authority=post_submit_execution_authority,
        registry=default_checker_registry(), outbox=outbox_append)


def checker_output_reservations(session):
    """Resolve exact active run/lease custody; current catalogue has zero slots."""
    from app.modules.checkers.execution_coordination import CheckerOutputReservations
    return CheckerOutputReservations(session)


def current_post_submit_execution(session):
    """Keep ART currentness checks behind the CHECKERS owner port."""
    from app.modules.checkers.execution_coordination import CurrentExecution
    return CurrentExecution(session)


def submission_evaluation_content(
    task_context: TaskSubmissionContextFacts,
    project_context: ProjectLockedPolicyContextFacts,
    packet: SubmissionPacketView,
    files: tuple[SubmissionBundleFile, ...],
    archive_sha256: str,
) -> PostSubmissionEvaluationContent:
    """Project inspected files and locked policies without executing a checker.

    Before admission, observed context is the locked TASK context. A dispatcher
    must first verify stored Submission lineage against these same facts; this
    projection never proves stored ownership or replaces the evaluation guard.
    """
    from app.adapters.tasks import validate_submission_policy_context

    validate_submission_policy_context(task_context, project_context)
    stamps = task_context.locked_policy
    expected = ExpectedPostSubmitContext(
        guide_version=stamps.locked_guide_version,
        source_id=stamps.locked_guide_source_snapshot_id,
        source_hash=stamps.locked_guide_source_snapshot_hash,
        effective_policy_id=stamps.locked_effective_project_submission_artifact_policy_id,
        effective_policy_hash=stamps.locked_effective_project_submission_artifact_policy_hash,
        pre_policy_id=stamps.locked_pre_submit_checker_policy_id,
        pre_policy_hash=stamps.locked_pre_submit_checker_bundle_hash,
        post_policy_id=stamps.locked_post_submit_checker_policy_id,
        post_policy_version=stamps.locked_post_submit_checker_policy_version,
        post_policy_hash=stamps.locked_post_submit_checker_policy_hash,
        review_policy_id=stamps.locked_review_policy_id,
        review_generation=stamps.locked_review_policy_generation,
        review_hash=stamps.locked_review_policy_hash,
        revision_policy_id=stamps.locked_revision_policy_id,
        revision_generation=stamps.locked_revision_policy_generation,
        revision_hash=stamps.locked_revision_policy_hash,
    )
    effective = json.loads(project_context.effective_policy.value)
    policy_inputs = PostSubmitPolicyInputs(
        required_evidence_keys=tuple(item["key"] for item in effective.get("required_evidence", [])
                                     if item.get("required", True)),
        required_artifact_paths=tuple(item["path"] for item in effective.get("required_artifacts", [])
                                      if item.get("required", True)),
        forbidden_artifact_patterns=tuple(item["pattern"] for item in effective.get("forbidden_artifacts", [])
                                         if item.get("pattern")),
        required_attestation_terms=tuple(term for term in effective.get("attestation_terms", []) if term),
    )
    by_path = {item.normalized_path: item for item in files}
    return PostSubmissionEvaluationContent(
        project_id=project_context.project_id,
        expected_context=expected,
        catalogue=installed_post_submit_catalogue(),
        policy=CompiledPostSubmitPolicy.model_validate_json(project_context.compiled_post_submit_policy.value),
        structural_input=PostSubmissionStructuralInput(
            summary=packet.summary, worker_attestation=packet.contributor_attestation,
            package_hash=archive_sha256, criteria=task_context.acceptance_criteria or "",
            manifest=tuple(PostSubmitManifestEntry(
                artifact=item.normalized_path, hash=item.sha256, size_bytes=item.byte_count,
            ) for item in files),
            evidence=tuple(PostSubmitEvidenceEntry(
                label=key, type="file", key=key, uri=item.normalized_path, hash=item.sha256,
            ) for key in policy_inputs.required_evidence_keys
              for item in (by_path.get(required_evidence_path(key)),) if item is not None),
            policy_inputs=policy_inputs,
            observed_context=ObservedPostSubmitContext(**expected.model_dump()),
        ),
    )


def selected_submission_evaluation_content(
    task_context: TaskSubmissionContextFacts,
    policy: LockedExternalPostSubmitPolicy,
) -> SelectedPostSubmissionContent:
    """Bind selected POST policy to exact TASK lineage without a catalogue hash."""
    locked = task_context.locked_policy
    references = task_context.locked_project_context
    return SelectedPostSubmissionContent(
        project_id=references.project_id,
        expected_context=SelectedPostSubmitLockedContext(
            guide_version=locked.locked_guide_version,
            source_id=locked.locked_guide_source_snapshot_id,
            source_hash=locked.locked_guide_source_snapshot_hash,
            effective_policy_id=(
                locked.locked_effective_project_submission_artifact_policy_id
            ),
            effective_policy_hash=(
                locked.locked_effective_project_submission_artifact_policy_hash
            ),
            pre_policy_id=locked.locked_pre_submit_checker_policy_id,
            pre_policy_hash=locked.locked_pre_submit_checker_bundle_hash,
            retained_catalogue_policy_id=(
                locked.locked_post_submit_checker_policy_id
            ),
            retained_catalogue_policy_version=(
                locked.locked_post_submit_checker_policy_version
            ),
            retained_catalogue_policy_hash=(
                locked.locked_post_submit_checker_policy_hash
            ),
            selected_post_policy_hash=policy.policy_sha256,
            review_policy_id=locked.locked_review_policy_id,
            review_generation=locked.locked_review_policy_generation,
            review_hash=locked.locked_review_policy_hash,
            revision_policy_id=locked.locked_revision_policy_id,
            revision_generation=locked.locked_revision_policy_generation,
            revision_hash=locked.locked_revision_policy_hash,
        ),
        policy=policy,
    )


def delivery_bound_post_submission_executor(*, sessions, materialization, envelope, request):
    """Add invocation custody to the existing executor without registering delivery."""
    from app.adapters.auth import post_submit_execution_authority
    from app.adapters.outbox import outbox_append, outbox_invocation_fence
    from app.adapters.tasks import evaluation_task_guard
    from app.modules.checkers.delivery_authority import DeliveryExecutionAuthority
    from app.modules.checkers.execution import PostSubmissionExecutor
    from app.modules.checkers.runner import default_checker_registry

    def authority(session):
        return DeliveryExecutionAuthority(
            authority=post_submit_execution_authority(session), tasks=evaluation_task_guard(session),
            fence=outbox_invocation_fence(session), envelope=envelope, request=request,
        )

    return PostSubmissionExecutor(
        sessions=sessions, execute_authority=authority, finalize_authority=authority,
        materialization=materialization, registry=default_checker_registry(), outbox=outbox_append,
    )
