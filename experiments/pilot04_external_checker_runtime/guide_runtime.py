"""Explicit recorded inference for the isolated prefork worker, never production."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND / "scripts"))
from guide_compilation_e2e import E2EProjectGuideRuntime, runtime_factory  # noqa: E402
from app.interfaces.project_agents import (  # noqa: E402
    AtomicGuideRequirement, PreSubmissionBindingProposal, PostSubmissionBindingProposal,
    SubmissionArtifactPolicyProposal, ProjectGuideCompilationResult,
    canonical_project_guide_compilation_context_bytes,
)
from app.modules.projects.api.task_examples import task_examples_hash, validate_task_examples  # noqa: E402
from experiments.pilot04_external_checker_runtime.guide_inputs import (  # noqa: E402
    GUIDE_BYTES, TASK_EXAMPLES, CORRECTION_REASON,
)


class RecordedGuideRuntime(E2EProjectGuideRuntime):
    """Read real scoped documents and observe exact examples; return recorded rules."""

    async def compile_project_guide(self, context, capabilities):
        expected = validate_task_examples(TASK_EXAMPLES)
        if context.task_examples != expected:
            raise AssertionError("worker did not receive exact normalized task examples")
        if context.correction_feedback is not None:
            if context.correction_feedback.reason != CORRECTION_REASON:
                raise AssertionError("worker did not receive exact manager correction")
        digest = "sha256:" + hashlib.sha256(GUIDE_BYTES).hexdigest()
        if len(context.material.documents) != 1 or context.material.documents[0].sha256 != digest:
            raise AssertionError("worker did not receive the uploaded original")
        base = await super().compile_project_guide(context, capabilities)
        refs = base.findings[0].evidence_refs
        requirements, pre, post = [], [], []
        for stage, binding_type, target in (
            ("pre_submit", PreSubmissionBindingProposal, pre),
            ("post_submit", PostSubmissionBindingProposal, post),
        ):
            entries = [d for d in context.checker_capabilities.definitions
                       if d.selectable and d.phase == stage]
            if len(entries) != 1:
                raise AssertionError("recorded guide requires one registered image per stage")
            entry = entries[0]
            key = "project." + stage
            requirements.append(AtomicGuideRequirement(
                requirement_id=key, statement="Apply the registered project image rules.",
                disposition="supported_" + stage, evidence_refs=refs,
            ))
            target.append(binding_type(
                requirement_id=key, capability_id=entry.capability_id,
                capability_version=entry.capability_version, stage=stage,
            ))
        value = base.model_dump(mode="json")
        value.update(
            submission_artifact_policy=SubmissionArtifactPolicyProposal(
                maximum_file_size_bytes=1_000_000, maximum_package_size_bytes=5_000_000,
                required_artifacts=("task.toml",), required_evidence=("results",),
                attestation_terms=("rights_confirmed",),
            ).model_dump(mode="json"),
            requirements=[item.model_dump(mode="json") for item in requirements],
            pre_submit_bindings=[item.model_dump(mode="json") for item in pre],
            post_submit_bindings=[item.model_dump(mode="json") for item in post],
            setup_notes=[
                "Recorded provider observed examples " + task_examples_hash(expected),
                "Recorded provider observed input sha256:" + hashlib.sha256(
                    canonical_project_guide_compilation_context_bytes(context)
                ).hexdigest(),
            ],
        )
        return ProjectGuideCompilationResult.model_validate(value)



def create_recorded_runtime(configuration):
    """Use the same typed adapter factory at the worker's external runtime seam."""
    return runtime_factory(RecordedGuideRuntime(configuration))(configuration)
