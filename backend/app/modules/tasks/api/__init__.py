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
    TaskQueueCursor, ReadyTaskPage, ReadyTaskQueuePort, TaskQueueRequest, ReadyTaskSummary,
)

from app.modules.tasks.api.management_queue import (
    ManagementTaskPage,
    ManagementTaskQueuePort,
    ManagementTaskSummary,
    OperationalTaskPage,
    OperationalTaskQueuePort,
    OperationalTaskSummary,
)

from app.modules.tasks.api.task_detail import (
    ContributorTaskDetail, ContributorTaskDetailRequest, ContributorTaskDetailPort,
    ManagementTaskDetail, ManagementTaskDetailRequest, ManagementTaskDetailPort,
)

from app.modules.tasks.api.work_context import (
    ContributorTaskLifecycle, ContributorTaskWorkContext, ManagementTaskWorkContext,
)

__all__ = (
    "ContributorTaskLifecycle", "ContributorTaskWorkContext", "ManagementTaskWorkContext",
    "ContributorTaskDetail",
    "ContributorTaskDetailRequest",
    "ContributorTaskDetailPort",
    "ManagementTaskDetail",
    "ManagementTaskDetailRequest",
    "ManagementTaskDetailPort",

    "ManagementTaskPage",
    "ManagementTaskQueuePort",
    "ManagementTaskSummary",
    "OperationalTaskPage",
    "OperationalTaskQueuePort",
    "OperationalTaskSummary",
    "TaskQueueCursor", "ReadyTaskPage", "ReadyTaskQueuePort", "TaskQueueRequest", "ReadyTaskSummary",
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
