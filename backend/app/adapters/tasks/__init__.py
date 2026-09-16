"""TASK-owned composition adapters and transaction roots."""

from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import Settings
from uuid import UUID

from app.modules.artifacts.api import (
    SubmissionAdmissionConsumptionPort,
    SubmissionAdmissionConsumptionRequest,
)
from app.modules.tasks.api import (
    SubmissionArtifactAdmissionRequest,
    SubmissionArtifactAdmissionResult,
    SubmissionCreationAuthorizationPort,
    SubmissionCreationAuthorityFacts,
    SubmissionCreationPreparationFacts,
    SubmissionCreationRequest,
    SubmissionCreationResult,
    SubmissionCreationUnavailable,
    TaskSubmissionContextPort,
)
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.service import TaskService
from app.modules.tasks.authorized_commands import AuthorizedTaskCommands
from app.modules.tasks.api import TaskAuthorizationPort, TaskTransitionAuditPort
from app.modules.tasks.submission_composition import TaskSubmissionCreationService

__all__ = (
    "task_commands",
    "task_service",
    "DenySubmissionCreationAuthorization",
    "TransactionalSubmissionCreationCommand",
    "task_submission_context_port",
)


def task_service(session: AsyncSession, *, settings: Settings) -> TaskService:
    """Compose exact PROJECTS custody and installed CHECKERS at the existing TASK root."""
    from app.adapters.projects import project_locked_policy_context_port
    from app.adapters.checkers import project_guide_approval_compiler, installed_post_submit_catalogue

    planner, _, _ = project_guide_approval_compiler(
        disabled_checker_ids=settings.artifact_pre_submission_checker_disabled_ids,
    )
    return TaskService(
        session, project_contexts=project_locked_policy_context_port(session),
        pre_submit_planner=planner, post_submit_catalogue=installed_post_submit_catalogue,
    )


def task_commands(
    session: AsyncSession, *, authorization: TaskAuthorizationPort,
    audit: TaskTransitionAuditPort, actor_profile_id: UUID, settings: Settings,
) -> AuthorizedTaskCommands:
    """Compose TASK commands without exposing private product imports to delivery."""
    return AuthorizedTaskCommands(
        session, authorization=authorization, audit=audit, actor_profile_id=actor_profile_id,
        contexts=task_service(session, settings=settings),
    )


def task_submission_context_port(session: AsyncSession) -> TaskSubmissionContextPort:
    """Bind the public TASK submission-context port to its repository."""
    return TaskRepository(session)


class DenySubmissionCreationAuthorization:
    """Keep the hidden human action unavailable until AUTH activation."""

    async def authorize(self, facts: SubmissionCreationPreparationFacts) -> None:
        del facts
        raise SubmissionCreationUnavailable("submission creation is unavailable")

    async def prepare(self, facts: SubmissionCreationAuthorityFacts) -> object:
        del facts
        raise SubmissionCreationUnavailable("submission creation is unavailable")

    async def consume(
        self, prepared_authorization: object, facts: SubmissionCreationAuthorityFacts
    ) -> None:
        del prepared_authorization, facts
        raise SubmissionCreationUnavailable("submission creation is unavailable")

    def close(self, prepared_authorization: object) -> None:
        del prepared_authorization


class _ArtifactAdmissionAdapter:
    def __init__(self, admissions: SubmissionAdmissionConsumptionPort) -> None:
        self._admissions = admissions

    async def consume(
        self, request: SubmissionArtifactAdmissionRequest
    ) -> SubmissionArtifactAdmissionResult:
        result = await self._admissions.consume(
            SubmissionAdmissionConsumptionRequest(
                admission_id=request.admission_id,
                submission_id=request.submission_id,
                submission_version=request.submission_version,
                task_context=request.task_context,
            )
        )
        if result.binding_id is None or result.status != "consumed":
            raise RuntimeError("admission did not produce a binding")
        return SubmissionArtifactAdmissionResult(
            binding_id=result.binding_id, content_id=result.content_id
        )


class TransactionalSubmissionCreationCommand:
    """Open the sole root transaction and delegate sequencing to TASK."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        authorization: SubmissionCreationAuthorizationPort,
        admissions: SubmissionAdmissionConsumptionPort,
        settings: Settings,
    ) -> None:
        self._session = session
        self._settings = settings
        self._authorization = authorization
        self._admissions = admissions

    async def create(self, request: SubmissionCreationRequest) -> SubmissionCreationResult:
        if self._session.in_transaction():
            raise RuntimeError("submission composition requires a transaction-free session")
        async with self._session.begin():
            return await TaskSubmissionCreationService(
                self._session,
                contexts=task_service(self._session, settings=self._settings),
                authorization=self._authorization,
                admissions=_ArtifactAdmissionAdapter(self._admissions),
            ).create(request)
