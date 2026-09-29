"""Dependency-safe public API for the ARTIFACTS business module."""

from app.modules.artifacts.api.submission_preparation import (
    SubmissionBundlePreparationCommand,
    SubmissionBundlePreparationRejected,
    SubmissionBundlePreparationInfrastructureUnavailable,
    SubmissionBundlePreparationRequest,
    SubmissionBundlePreparationResult,
    SubmissionBundlePreparationStatus,
    SubmissionBundlePreparationUnavailable,
)
from app.modules.artifacts.api.submission_admission import (
    SubmissionAdmissionConsumptionError,
    SubmissionAdmissionConsumptionPort,
    SubmissionAdmissionConsumptionRequest,
    SubmissionAdmissionConsumptionResult,
    SubmissionAdmissionConsumptionStatus,
)

__all__ = (
    "SubmissionBundlePreparationCommand",
    "SubmissionBundlePreparationRejected",
    "SubmissionBundlePreparationInfrastructureUnavailable",
    "SubmissionBundlePreparationRequest",
    "SubmissionBundlePreparationResult",
    "SubmissionBundlePreparationStatus",
    "SubmissionBundlePreparationUnavailable",
    "SubmissionAdmissionConsumptionError",
    "SubmissionAdmissionConsumptionPort",
    "SubmissionAdmissionConsumptionRequest",
    "SubmissionAdmissionConsumptionResult",
    "SubmissionAdmissionConsumptionStatus",
)

from app.modules.artifacts.api.submission_materialization import (
    PostSubmissionMaterialConsumer, PostSubmissionMaterializationPort,
    PostSubmissionMaterializationResult, PostSubmissionMaterializationUnavailable,
    SubmissionMaterialEntry, SubmissionMaterialView,
)

__all__ += (
    "PostSubmissionMaterialConsumer", "PostSubmissionMaterializationPort",
    "PostSubmissionMaterializationResult", "PostSubmissionMaterializationUnavailable",
    "SubmissionMaterialEntry", "SubmissionMaterialView",
)
