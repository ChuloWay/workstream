"""Bind selected PRE policy and default inputs to locked TASK/PROJECT custody."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.sources import ArtifactCommitment
from app.modules.artifacts.submission_manifest import (
    SubmissionCanonicalPredecessor,
    SubmissionChangeGateResult,
    SubmissionManifest,
    bind_submission_change,
)
from app.modules.checkers.api.default_checker import (
    WorkstreamDefaultCheckerInput,
    WorkstreamDefaultPredecessor,
)
from app.modules.checkers.api.external_policy import (
    LockedExternalCheckerPolicies,
    LockedExternalPreSubmitPolicy,
)
from app.modules.checkers.api.materialization import SubmissionMaterialEntry
from app.modules.checkers.api.pre_submit import SubmissionPacketView
from app.modules.projects.api import ProjectLockedPolicyContextFacts
from app.modules.tasks.api import TaskSubmissionContextFacts


@dataclass(frozen=True, slots=True)
class SelectedPreSubmitAdmissionContext:
    """Exact selected policy, default input and non-deciding change binding."""

    policy: LockedExternalPreSubmitPolicy
    default_input: WorkstreamDefaultCheckerInput
    change_gate: SubmissionChangeGateResult
    rules_sha256: str


def bind_selected_pre_submit_admission(
    *,
    task: TaskSubmissionContextFacts,
    project: ProjectLockedPolicyContextFacts,
    commitment: ArtifactCommitment,
    manifest: SubmissionManifest,
    predecessor: SubmissionCanonicalPredecessor | None,
    predecessor_rules_sha256: str | None,
    predecessor_exists: bool,
    packet: SubmissionPacketView,
) -> SelectedPreSubmitAdmissionContext:
    """Bind genuine locked policy and predecessor facts before CHECKER execution."""
    if project.project_id != task.locked_project_context.project_id:
        raise ValueError("selected PRE task and project contexts differ")
    policies = LockedExternalCheckerPolicies.model_validate_json(
        project.external_checker_policies.value
    )
    rules_sha256 = canonical_json_hash(
        {
            "schema_version": "workstream.task_checker_rules.v1",
            "task_policy": task.locked_policy.model_dump(mode="json"),
            "external_checker_policies_sha256": policies.policies_sha256,
        }
    )
    default_predecessor = (
        WorkstreamDefaultPredecessor(
            submission_id=predecessor.submission_id,
            submission_version=predecessor.submission_version,
            archive_sha256=predecessor.archive_sha256,
            semantic_manifest_sha256=predecessor.semantic_manifest_sha256,
        )
        if predecessor is not None
        else None
    )
    if (predecessor_rules_sha256 is None) != (predecessor is None):
        raise ValueError("selected PRE predecessor rules are incomplete")
    change_gate = bind_submission_change(
        commitment=commitment,
        manifest=manifest,
        predecessor=predecessor,
        predecessor_exists=predecessor_exists,
        current_predecessor=predecessor,
    )
    entries = tuple(
        SubmissionMaterialEntry(
            normalized_path=item.normalized_path,
            entry_type=item.entry_type.value,
            byte_count=item.byte_count,
            sha256=item.sha256,
            executable=item.executable,
        )
        for item in manifest.entries
    )
    return SelectedPreSubmitAdmissionContext(
        policy=policies.pre_submit,
        default_input=WorkstreamDefaultCheckerInput(
            archive_sha256=commitment.sha256,
            archive_byte_count=commitment.byte_count,
            archive_media_type=commitment.media_type,
            semantic_manifest_sha256=manifest.sha256,
            entries=entries,
            predecessor=default_predecessor,
            predecessor_exists=predecessor_exists,
            current_predecessor=default_predecessor,
            current_rules_sha256=rules_sha256,
            predecessor_rules_sha256=predecessor_rules_sha256,
            packet=packet,
        ),
        change_gate=change_gate,
        rules_sha256=rules_sha256,
    )


__all__ = ("SelectedPreSubmitAdmissionContext", "bind_selected_pre_submit_admission")
