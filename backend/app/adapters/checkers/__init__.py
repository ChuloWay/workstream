"""CHECKER-owned composition adapters."""

from app.adapters.checkers.external_service import (
    EXTERNAL_CHECKER_CAPABILITY_KEY,
    EXTERNAL_CHECKER_PROVIDER_KEY,
    UnixSocketExternalCheckerAdapter,
)
from app.interfaces.external_checker_execution import (
    ExternalCheckerExecutionAdapter,
    ExternalCheckerExecutionResponse,
    ExternalCheckerMaterialGrant,
    ExternalCheckerServiceHealth,
)
from app.interfaces.external_services import (
    ExternalServiceAdapterFactory,
    ExternalServiceAdapterIdentity,
    ExternalServiceUnavailableError,
)
from app.modules.tasks.api import TaskSubmissionContextFacts

from app.modules.checkers.api.external_policy import LockedExternalPostSubmitPolicy
from app.modules.checkers.api.selected_post_submit import (
    SelectedPostSubmissionContent,
    SelectedPostSubmitLockedContext,
)
from app.modules.checkers.api.history import CheckerHistoryReadPort
from app.modules.checkers.api.execution import EvaluationCoordinationPort
from typing import Any, Protocol
from pathlib import Path

from app.modules.checkers.api import PreSubmissionInfrastructureUnavailableError
from app.modules.checkers.api.external import (
    ExternalCheckerCapabilityDefinition,
    ExternalCheckerCapabilityProjection,
    ExternalCheckerExecutionRequest,
    PreSubmitExternalCheckerIdentity,
    PreSubmitExternalCheckerMaterial,
    external_checker_json_hash,
)
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_CHECKER_ID,
    WORKSTREAM_DEFAULT_CHECKER_VERSION,
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


class _ConfiguredExternalCheckerExecution:
    """Resolve the fixed Rust provider only when a locked image is invoked."""

    def __init__(self, settings) -> None:
        self._settings = settings
        self._identity = ExternalServiceAdapterIdentity(
            EXTERNAL_CHECKER_CAPABILITY_KEY,
            EXTERNAL_CHECKER_PROVIDER_KEY,
        )

    @property
    def identity(self) -> ExternalServiceAdapterIdentity:
        """Expose the sole provider identity without constructing its transport."""
        return self._identity

    def _resolve(self) -> ExternalCheckerExecutionAdapter:
        """Create the fixed provider or report absent runtime configuration."""
        if (
            self._settings.external_checker_service_socket is None
            and self._settings.external_checker_material_root is None
        ):
            raise ExternalServiceUnavailableError(self._identity)
        return configured_external_checker_execution_factory(self._settings).create(
            EXTERNAL_CHECKER_PROVIDER_KEY
        )

    async def execute(
        self,
        request: ExternalCheckerExecutionRequest,
        grant: ExternalCheckerMaterialGrant,
    ) -> ExternalCheckerExecutionResponse:
        """Resolve and invoke the sole provider for one selected binding."""
        return await self._resolve().execute(request, grant)

    async def health(self) -> ExternalCheckerServiceHealth:
        """Resolve the sole provider before checking runtime readiness."""
        return await self._resolve().health()


def configured_external_checker_execution(settings) -> ExternalCheckerExecutionAdapter:
    """Create the lazy fixed-provider adapter for selected execution."""
    return _ConfiguredExternalCheckerExecution(settings)


def selected_pre_submit_checker_execution(*, settings, archive_inspector):
    """Compose the sole selected PRE runtime from the configured Rust service."""
    return SelectedPreSubmitCheckerExecutionAdapter(
        archive_inspector=archive_inspector,
        external_execution=configured_external_checker_execution(settings),
    )


def external_checker_registry_reader(session):
    """Resolve immutable metadata for trusted approval and execution owners."""
    from app.modules.checkers.external_registry import ExternalCheckerRegistryReader

    return ExternalCheckerRegistryReader(session)


async def external_checker_capability_projection(
    session,
) -> ExternalCheckerCapabilityProjection:
    """Snapshot one default plus every immutable external registry identity."""
    entries = await external_checker_registry_reader(session).list_entries()
    definitions = tuple(
        sorted(
            (
                ExternalCheckerCapabilityDefinition(
                    capability_id=WORKSTREAM_DEFAULT_CHECKER_ID,
                    capability_version=WORKSTREAM_DEFAULT_CHECKER_VERSION,
                    phase="pre_submit",
                    selectable=False,
                    registry_entry=None,
                ),
                *(
                    ExternalCheckerCapabilityDefinition(
                        capability_id=entry.capability_id,
                        capability_version=entry.capability_version,
                        phase=entry.phase,
                        selectable=True,
                        registry_entry=entry,
                    )
                    for entry in entries
                ),
            ),
            key=lambda item: (
                item.phase,
                item.capability_id,
                item.capability_version,
            ),
        )
    )
    body = {
        "schema_version": "external_checker_capabilities.v1",
        "definitions": [item.model_dump(mode="json") for item in definitions],
    }
    return ExternalCheckerCapabilityProjection(
        definitions=definitions,
        manifest_sha256=external_checker_json_hash(body),
    )


def selected_pre_submit_coordinator(session):
    """Compose selected PRE custody through CHECKERS' public adapter root."""
    from app.adapters.tasks import selected_pre_submit_task_guard
    from app.modules.checkers.selected_pre_submit_coordination import (
        SelectedPreSubmitCoordinator,
    )

    return SelectedPreSubmitCoordinator(
        session,
        tasks=selected_pre_submit_task_guard(session),
    )


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


def checker_history_repository(session) -> CheckerHistoryReadPort:
    """Compose retained CHECKERS reads through TASK's public ownership port."""
    from app.modules.checkers.history import CheckerHistoryRepository

    return CheckerHistoryRepository(session)


def evaluation_coordinator(session) -> EvaluationCoordinationPort:
    """Compose required TASK locking before CHECKERS reservation custody."""
    from app.modules.checkers.execution_coordination import EvaluationCoordinator
    from app.adapters.tasks import evaluation_task_guard

    return EvaluationCoordinator(session, tasks=evaluation_task_guard(session))


def checker_retry_service(session, context):
    """Compose hidden Operator retry from existing owner operations only."""
    from app.adapters.audit import checker_retry_audit
    from app.adapters.auth import checker_retry_authorization
    from app.adapters.outbox import outbox_append
    from app.adapters.tasks import evaluation_task_guard
    from app.modules.checkers.checker_retry import CheckerRetryService
    from app.modules.checkers.execution_coordination import EvaluationCoordinator

    tasks = evaluation_task_guard(session)
    return CheckerRetryService(
        session, actor_profile_id=context.actor_profile_id,
        tasks=tasks, evaluations=EvaluationCoordinator(session, tasks=tasks),
        authorization=checker_retry_authorization(session, context),
        events=outbox_append(session), audit=checker_retry_audit(session),
    )


def post_submission_executor(*, sessions, materialization):
    """Compose the sole executor with exact fixed-service AUTH at both phases."""
    from app.adapters.outbox import outbox_append
    from app.modules.checkers.execution import PostSubmissionExecutor
    from app.adapters.auth import post_submit_execution_authority

    return PostSubmissionExecutor(
        sessions=sessions,
        materialization=materialization,
        execute_authority=post_submit_execution_authority,
        finalize_authority=post_submit_execution_authority,
        outbox=outbox_append,
    )


def checker_output_reservations(session):
    """Resolve exact active run/lease custody for artifact output reservations."""
    from app.modules.checkers.execution_coordination import CheckerOutputReservations

    return CheckerOutputReservations(session)


def current_post_submit_execution(session):
    """Keep ART currentness checks behind the CHECKERS owner port."""
    from app.modules.checkers.execution_coordination import CurrentExecution

    return CurrentExecution(session)


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
            effective_policy_id=(locked.locked_effective_project_submission_artifact_policy_id),
            effective_policy_hash=(locked.locked_effective_project_submission_artifact_policy_hash),
            pre_policy_id=locked.locked_pre_submit_checker_policy_id,
            pre_policy_hash=locked.locked_pre_submit_checker_bundle_hash,
            retained_catalogue_policy_id=(locked.locked_post_submit_checker_policy_id),
            retained_catalogue_policy_version=(locked.locked_post_submit_checker_policy_version),
            retained_catalogue_policy_hash=(locked.locked_post_submit_checker_policy_hash),
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


def delivery_bound_post_submission_executor(
    *, sessions, materialization, envelope, request, selected_execution=None
):
    """Add invocation custody to the existing executor without registering delivery."""
    from app.adapters.auth import post_submit_execution_authority
    from app.adapters.outbox import outbox_append, outbox_invocation_fence
    from app.adapters.tasks import evaluation_task_guard
    from app.modules.checkers.delivery_authority import DeliveryExecutionAuthority
    from app.modules.checkers.execution import PostSubmissionExecutor

    def authority(session):
        return DeliveryExecutionAuthority(
            authority=post_submit_execution_authority(session),
            tasks=evaluation_task_guard(session),
            fence=outbox_invocation_fence(session),
            envelope=envelope,
            request=request,
        )

    return PostSubmissionExecutor(
        sessions=sessions,
        execute_authority=authority,
        finalize_authority=authority,
        materialization=materialization,
        selected_execution=selected_execution,
        outbox=outbox_append,
    )
