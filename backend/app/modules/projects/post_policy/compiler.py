"""Connect validated saved bindings to the sole canonical policy compiler."""

from uuid import UUID

from app.interfaces.project_agents import (
    ProjectGuideCompilationResult,
    validate_post_submission_bindings,
)
from app.modules.checkers.api.post_submit_catalogue import CompiledPostSubmitPolicy, PostSubmitCatalogue
from app.modules.projects.post_submit_policy import (
    build_project_post_submit_checker_spec,
    compile_project_post_submit_checker_spec,
)


def compile_saved_post_policy(
    *, project_id: UUID, guide_version: str,
    result: ProjectGuideCompilationResult, catalogue: PostSubmitCatalogue,
) -> CompiledPostSubmitPolicy:
    """Preserve every supported requirement while executing each shared member once."""
    validate_post_submission_bindings(result, catalogue)
    if result.status == "guide_blocked" or result.submission_artifact_policy is None:
        raise ValueError("blocked guide cannot project post-submit policy")
    selected = {binding.capability_id for binding in result.post_submit_bindings}
    compiled = compile_project_post_submit_checker_spec(
        project_id=str(project_id), guide_version=guide_version,
        spec=build_project_post_submit_checker_spec(
            project_id=str(project_id), guide_version=guide_version,
            required_checkers=sorted(selected),
        ),
    )
    compiled.validate_catalogue(catalogue)
    entries = {entry.checker_id: entry for entry in compiled.entries}
    for binding in result.post_submit_bindings:
        entry = entries.get(binding.capability_id)
        if (
            entry is None or entry.classification != "project_required"
            or entry.definition_version != binding.capability_version
            or entry.configuration.model_dump(mode="json")
            != {parameter.name: parameter.value for parameter in binding.parameters}
        ):
            raise ValueError("compiled post-submit policy omits or changes a required binding")
    return compiled
