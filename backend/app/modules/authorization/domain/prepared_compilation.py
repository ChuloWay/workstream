"""Prepared-capability parsing and equality for guide compilation."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.guide_compilation import (
    CompilationResourceContext,
    ProjectGuideCompilationExecuteResourceContext,
    ProjectGuideCompilationRequestResourceContext,
)
from app.modules.authorization.runtime import authorization_resource_digest
from app.modules.authorization.runtime import PreparedAuthorizationHandleInvalid

_CONTEXT_BY_ACTION = {
    ActionId.PROJECT_GUIDE_COMPILATION_REQUEST: ProjectGuideCompilationRequestResourceContext,
    ActionId.PROJECT_GUIDE_COMPILATION_REQUEST_AUTOMATIC: ProjectGuideCompilationRequestResourceContext,
    ActionId.PROJECT_GUIDE_COMPILATION_EXECUTE: ProjectGuideCompilationExecuteResourceContext,
}
_UUID_FIELDS = (
    "resource_id",
    "scope_project_id",
    "guide_id",
    "source_snapshot_id",
    "setup_run_id",
    "operation_id",
    "request_id",
    "idempotency_key",
    "attempt_id",
    "provider_idempotency_key",
    "source_mutation_operation_id",
    "source_authorization_decision_event_id",
)


def parse_prepared_compilation(
    action_id: ActionId, request_value: Mapping[str, object]
) -> dict[str, object]:
    """Parse exact compilation facts when the action belongs to this capability."""
    context_type = _CONTEXT_BY_ACTION.get(action_id)
    if context_type is None:
        return {}
    try:
        value = dict(request_value)
        for field in _UUID_FIELDS:
            if field in value and value[field] is not None:
                value[field] = UUID(str(value[field]))
        resource = context_type.model_validate(value)
        if isinstance(resource, ProjectGuideCompilationRequestResourceContext):
            expected = ("automatic_source_ready" if action_id is ActionId.PROJECT_GUIDE_COMPILATION_REQUEST_AUTOMATIC else "project_manager")
            if resource.trigger != expected:
                raise ValueError("request trigger does not match action")
    except (TypeError, ValueError) as exc:
        raise PreparedAuthorizationHandleInvalid("invalid prepared authorization handle") from exc
    return {
        "guide_compilation_context": resource.model_dump(mode="json"),
        "guide_compilation_resource_digest": authorization_resource_digest(resource),
    }


def prepared_compilation_matches(
    context: dict | None,
    digest: str | None,
    resource: CompilationResourceContext,
) -> bool:
    """Require exact facts, allowing one owner-minted request row identity."""
    if isinstance(resource, ProjectGuideCompilationRequestResourceContext):
        if context is None or digest is None:
            return False
        if context == resource.model_dump(mode="json"):
            return digest == authorization_resource_digest(resource)
        prepared_value = dict(context)
        for field in _UUID_FIELDS:
            if field in prepared_value and prepared_value[field] is not None:
                prepared_value[field] = UUID(str(prepared_value[field]))
        prepared_context = ProjectGuideCompilationRequestResourceContext.model_validate(
            prepared_value
        )
        if digest != authorization_resource_digest(prepared_context):
            return False
        prepared = dict(context)
        final = resource.model_dump(mode="json")
        prepared_operation = UUID(str(prepared.pop("operation_id")))
        prepared_resource = UUID(str(prepared.pop("resource_id")))
        prepared.pop("request_facts_digest")
        final_operation = UUID(str(final.pop("operation_id")))
        final_resource = UUID(str(final.pop("resource_id")))
        final.pop("request_facts_digest")
        return (
            prepared_operation == prepared_resource
            and prepared_operation.version in {4, 5}
            and final_operation == final_resource
            and final_operation.version == 7
            and prepared == final
        )
    return context == resource.model_dump(mode="json") and (
        digest == authorization_resource_digest(resource)
    )
