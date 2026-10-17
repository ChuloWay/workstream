"""Dependency-safe public API for the CHECKERS business module."""

from app.modules.checkers.api.external import (
    EXTERNAL_CHECKER_REQUEST_SCHEMA_VERSION,
    EXTERNAL_CHECKER_RESULT_SCHEMA_VERSION,
    POST_SUBMIT_INPUT_SCHEMA_ID,
    PRE_SUBMIT_INPUT_SCHEMA_ID,
    RESULT_SCHEMA_ID,
    ExternalCheckerContractError,
    ExternalCheckerExecutionRequest,
    ExternalCheckerExecutionResult,
    ExternalCheckerFinding,
    ExternalCheckerMaterial,
    ExternalCheckerRegistrationCommand,
    ExternalCheckerRegistrationAuthorityFacts,
    ExternalCheckerRegistrationAuthorityPort,
    ExternalCheckerRegistrationAuthorityReceipt,
    ExternalCheckerRegistrationPreparation,
    ExternalCheckerRegistryAuthorizationDenied,
    ExternalCheckerRegistryConflict,
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistryNotFound,
    ExternalCheckerRegistryPort,
    ExternalCheckerRegistrySpec,
    ExternalCheckerRegistryUnavailable,
    ExternalCheckerResourceLimits,
    ExternalCheckerSchema,
    PostSubmitExternalCheckerIdentity,
    PreSubmitExternalCheckerIdentity,
    external_checker_registration_request_digest,
    make_external_checker_execution_request,
    make_external_checker_execution_result,
)
from app.modules.checkers.api.pre_submit_material import (
    ALLOWED_PRE_SUBMIT_STORAGE_SCHEMES,
    SubmissionPacketView,
)
from app.modules.checkers.api.selected_pre_submit import (
    ExternalPreSubmitIsolationFacts,
    ExternalPreSubmitMemberFacts,
    SelectedPreSubmitExecutionFacts,
    SelectedPreSubmitInfrastructureUnavailable,
)

__all__ = (
    "ALLOWED_PRE_SUBMIT_STORAGE_SCHEMES",
    "SubmissionPacketView",
    "ExternalPreSubmitIsolationFacts",
    "ExternalPreSubmitMemberFacts",
    "SelectedPreSubmitExecutionFacts",
    "SelectedPreSubmitInfrastructureUnavailable",
)

from app.modules.checkers.api.selected_post_submit import (
    SelectedPostSubmitCurrentResultReference,
    SelectedPostSubmissionContent,
    SelectedPostSubmissionEvaluationRequest,
    SelectedPostSubmissionEvaluationResult,
    SelectedPostSubmitExecutionFacts,
    SelectedPostSubmitLockedContext,
    make_selected_post_submit_request,
    make_selected_post_submit_result,
)

__all__ += (
    "SelectedPostSubmitCurrentResultReference",
    "SelectedPostSubmissionContent", "SelectedPostSubmissionEvaluationRequest",
    "SelectedPostSubmissionEvaluationResult", "SelectedPostSubmitExecutionFacts",
    "SelectedPostSubmitLockedContext", "make_selected_post_submit_request",
    "make_selected_post_submit_result",
)

__all__ += (
    "EXTERNAL_CHECKER_REQUEST_SCHEMA_VERSION",
    "EXTERNAL_CHECKER_RESULT_SCHEMA_VERSION",
    "POST_SUBMIT_INPUT_SCHEMA_ID",
    "PRE_SUBMIT_INPUT_SCHEMA_ID",
    "RESULT_SCHEMA_ID",
    "ExternalCheckerContractError",
    "ExternalCheckerExecutionRequest",
    "ExternalCheckerExecutionResult",
    "ExternalCheckerFinding",
    "ExternalCheckerMaterial",
    "ExternalCheckerRegistrationCommand",
    "ExternalCheckerRegistrationAuthorityFacts",
    "ExternalCheckerRegistrationAuthorityPort",
    "ExternalCheckerRegistrationAuthorityReceipt",
    "ExternalCheckerRegistrationPreparation",
    "ExternalCheckerRegistryAuthorizationDenied",
    "ExternalCheckerRegistryConflict",
    "ExternalCheckerRegistryEntry",
    "ExternalCheckerRegistryNotFound",
    "ExternalCheckerRegistryPort",
    "ExternalCheckerRegistrySpec",
    "ExternalCheckerRegistryUnavailable",
    "ExternalCheckerResourceLimits",
    "ExternalCheckerSchema",
    "PostSubmitExternalCheckerIdentity",
    "PreSubmitExternalCheckerIdentity",
    "external_checker_registration_request_digest",
    "make_external_checker_execution_request",
    "make_external_checker_execution_result",
)
