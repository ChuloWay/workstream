"""Prepared-binding helpers for checker model calls and their ART outputs."""

from uuid import UUID

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.domain.checker_models import (
    CHECKER_MODEL_ACTIONS,
    CheckerModelCallResourceContext,
    ProjectModelAdministrationResourceContext,
    checker_model_prepare_matches,
    parse_checker_model_prepare,
)
from app.modules.authorization.domain.checker_outputs import (
    CHECKER_OUTPUT_ACTIONS,
    CheckerOutputResourceContext,
    checker_output_prepare_matches,
    parse_checker_output_prepare,
)


def parse_checker_runtime_bindings(
    action: ActionId, value: object, invalid_error: type[Exception]
) -> dict[str, object | None]:
    """Parse the exact preliminary checker-runtime resource, when applicable."""
    return {
        "checker_model_context": parse_checker_model_prepare(action, value, invalid_error),
        "checker_output_context": parse_checker_output_prepare(action, value, invalid_error),
    }


def checker_runtime_binding_matches(
    action: ActionId,
    model_context: object,
    output_context: object,
    resource: object,
) -> bool | None:
    """Match a checker-runtime final resource or return None for another capability."""
    if action in CHECKER_MODEL_ACTIONS:
        return checker_model_prepare_matches(model_context, resource)
    if action in CHECKER_OUTPUT_ACTIONS:
        return checker_output_prepare_matches(output_context, resource)
    return None


def checker_runtime_project_id(action: ActionId, resource: object) -> UUID | None:
    """Extract project scope only from the exact checker-runtime resource type."""
    if action in CHECKER_MODEL_ACTIONS and isinstance(resource, CheckerModelCallResourceContext):
        return resource.scope_project_id
    # Project model administration deliberately consumes system-scoped Operator
    # authority.  The project identifier remains an exact guarded target inside
    # the resource; it is not the authority scope for this action family.
    if action in CHECKER_MODEL_ACTIONS and isinstance(
        resource, ProjectModelAdministrationResourceContext
    ):
        return None
    if action in CHECKER_OUTPUT_ACTIONS and isinstance(resource, CheckerOutputResourceContext):
        return resource.scope_project_id
    return None


__all__ = (
    "checker_runtime_binding_matches",
    "checker_runtime_project_id",
    "parse_checker_runtime_bindings",
)
