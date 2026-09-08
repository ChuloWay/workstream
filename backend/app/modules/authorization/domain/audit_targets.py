"""Exact project resource audit selectors, without raw product facts."""


def project_authority_audit_target(resource: object) -> tuple[str, str, str, str, str] | None:
    """Project-scoped exact contexts share bounded audit selectors, never raw facts."""
    from app.modules.authorization.domain.adapter_bindings import (
        AdapterBindingReadResourceContext,
        AdapterBindingMutationResourceContext,
    )
    from app.modules.authorization.domain.guide_compilation import (
        ProjectGuideCompilationRequestResourceContext,
        ProjectGuideCompilationExecuteResourceContext,
    )
    from app.modules.authorization.domain.guide_compilation_projections import (
        ProjectGuideProjectionResourceContext,
    )
    from app.modules.authorization.domain.project_setup_finalization import (
        ProjectSetupFinalizationResourceContext,
    )
    from app.modules.authorization.runtime import PreSubmitCheckerInputResourceContext

    if not isinstance(
        resource,
        (
            PreSubmitCheckerInputResourceContext,
            ProjectGuideCompilationRequestResourceContext,
            ProjectGuideCompilationExecuteResourceContext,
            AdapterBindingReadResourceContext,
            AdapterBindingMutationResourceContext,
            ProjectGuideProjectionResourceContext,
            ProjectSetupFinalizationResourceContext,
        ),
    ):
        return None
    project_id = str(getattr(resource, "project_id", None) or resource.scope_project_id)
    return project_id, resource.resource_type, str(resource.resource_id), "project", project_id
