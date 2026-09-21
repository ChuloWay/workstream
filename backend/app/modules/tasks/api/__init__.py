"""Dependency-safe public API for the TASKS business module."""

from app.modules.tasks.api.transition_audit import TaskTransitionAuditPort, TaskTransitionFacts

from app.modules.tasks.api.authorization import (
    TaskAuthorizationPort,
    TaskAuthorityDenied,
    TaskAuthorityFacts,
    TaskAuthorityOperation,
)

from app.modules.tasks.api.submission_context import (
    SubmissionPredecessorFacts,
    TaskLockedProjectContextReferences,
    TaskSubmissionContextFacts,
    TaskSubmissionContextFailure,
    TaskSubmissionContextKind,
    TaskSubmissionContextPort,
    TaskSubmissionContextRequest,
    TaskSubmissionContextStatus,
    TaskSubmissionContextUnavailable,
)
from app.modules.tasks.api.submission_command import (
    SubmissionCreationAuthorizationPort,
    SubmissionCreationAuthorityFacts,
    SubmissionCreationPreparationFacts,
    SubmissionCreationCommand,
    SubmissionCreationRequest,
    SubmissionCreationResult,
    SubmissionCreationUnavailable,
    SubmissionArtifactAdmissionPort,
    SubmissionArtifactAdmissionRequest,
    SubmissionArtifactAdmissionResult,
)

from app.modules.tasks.api.ready_queue import (
    ReadyTaskCursor, ReadyTaskPage, ReadyTaskQueuePort, ReadyTaskQueueRequest, ReadyTaskSummary,
)

__all__ = (
    "ReadyTaskCursor", "ReadyTaskPage", "ReadyTaskQueuePort", "ReadyTaskQueueRequest", "ReadyTaskSummary",
    "TaskTransitionAuditPort",
    "TaskTransitionFacts",
    "TaskAuthorizationPort",
    "TaskAuthorityDenied",
    "TaskAuthorityFacts",
    "TaskAuthorityOperation",
    "SubmissionPredecessorFacts",
    "TaskLockedProjectContextReferences",
    "TaskSubmissionContextFacts",
    "TaskSubmissionContextFailure",
    "TaskSubmissionContextKind",
    "TaskSubmissionContextPort",
    "TaskSubmissionContextRequest",
    "TaskSubmissionContextStatus",
    "TaskSubmissionContextUnavailable",
    "SubmissionCreationAuthorizationPort",
    "SubmissionCreationAuthorityFacts",
    "SubmissionCreationPreparationFacts",
    "SubmissionCreationCommand",
    "SubmissionCreationRequest",
    "SubmissionCreationResult",
    "SubmissionCreationUnavailable",
    "SubmissionArtifactAdmissionPort",
    "SubmissionArtifactAdmissionRequest",
    "SubmissionArtifactAdmissionResult",
)
