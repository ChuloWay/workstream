"""Controlled owner facts; no future database rows, authorization, or worker fixtures."""

from uuid import UUID
from app.core.identifiers import new_record_id

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api import (
    ExpectedPostSubmitContext,
    ObservedPostSubmitContext,
    PostSubmissionStructuralInput,
    PostSubmitEvidenceEntry,
    PostSubmitManifestEntry,
    PostSubmitPolicyInputs,
)
from app.modules.checkers.api.historical_post_submit import (
    CompiledPostSubmitPolicy,
    EmptyPostSubmitConfiguration,
    PostSubmitCatalogue,
    PostSubmitDefinition,
    PostSubmitPolicyEntry,
)
from app.modules.checkers.api.post_submit import make_post_submit_request
from tests.historical_checker_metadata import historical_post_submit_catalogue

HASH = "sha256:" + "a" * 64
OTHER_HASH = "sha256:" + "b" * 64
PROJECT = UUID("11111111-1111-4111-8111-111111111111")


def catalogue():
    """Return the frozen retained-history decoder, never an executable registry."""
    return historical_post_submit_catalogue()


def _policy(*, project_id: UUID, snapshot: PostSubmitCatalogue) -> CompiledPostSubmitPolicy:
    """Build a retained historical value without restoring its removed compiler."""
    selected = {
        "check_acceptance_criteria_present": "project_required",
    }
    entries = tuple(
        PostSubmitPolicyEntry(
            checker_id=item.capability_id,
            definition_version=item.capability_version,
            implementation_version=item.implementation_version,
            classification=(
                "platform_default"
                if item.platform_default
                else selected[item.capability_id]
            ),
            configuration=EmptyPostSubmitConfiguration(),
        )
        for item in snapshot.definitions
        if item.platform_default or item.capability_id in selected
    )
    return CompiledPostSubmitPolicy(
        project_id=project_id,
        guide_version="v1",
        catalogue_manifest_sha256=snapshot.manifest_sha256,
        entries=entries,
        blocking_severities=("critical", "high"),
    )


def altered_catalogue(original=None, *, index=8, **changes):
    source = original or catalogue()
    body = source.model_dump(mode="json", exclude={"manifest_sha256"})
    body["definitions"][index].update(changes)
    body["definitions"][index] = PostSubmitDefinition.model_validate(
        body["definitions"][index]
    ).model_dump(mode="json")
    return PostSubmitCatalogue(**body, manifest_sha256=canonical_json_hash(body))


def request(*, snapshot=None, project_id=PROJECT):
    snapshot = snapshot or catalogue()
    policy = _policy(project_id=project_id, snapshot=snapshot)
    policy.validate_catalogue(snapshot)
    fields = {}
    for name in ExpectedPostSubmitContext.model_fields:
        if name.endswith("_id"):
            fields[name] = new_record_id()
        elif "version" in name:
            fields[name] = "v1"
        elif name.endswith("generation"):
            fields[name] = 1
        else:
            fields[name] = HASH
    fields.update(post_policy_hash=policy.policy_hash)
    expected = ExpectedPostSubmitContext(**fields)
    data = PostSubmissionStructuralInput(
        summary="Delivered the documented result with supporting evidence.",
        worker_attestation="I confirm this submission contains no confidential data, credentials, secrets, or copied source or platform artifacts. Rights confirmed.",
        package_hash=HASH,
        criteria="Provide an accurate analysis with supporting evidence.",
        manifest=(PostSubmitManifestEntry(artifact="report.txt", hash=HASH, size_bytes=10),),
        evidence=(
            PostSubmitEvidenceEntry(label="proof", type="file", uri="report.txt", hash=HASH),
        ),
        policy_inputs=PostSubmitPolicyInputs(
            required_evidence_keys=("proof",),
            required_artifact_paths=("report.txt",),
            forbidden_artifact_patterns=("forbidden/**",),
            required_attestation_terms=("rights confirmed",),
        ),
        observed_context=ObservedPostSubmitContext(**expected.model_dump()),
    )
    return make_post_submit_request(
        evaluation_request_id=new_record_id(),
        evaluation_generation=1,
        project_id=project_id,
        task_id=new_record_id(),
        assignment_id=new_record_id(),
        submission_id=new_record_id(),
        submission_version=1,
        content_id=new_record_id(),
        binding_id=new_record_id(),
        content_sha256=HASH,
        byte_count=10,
        expected_context=expected,
        catalogue=snapshot,
        policy=policy,
        structural_input=data,
    )


def change_request(source, **changes):
    fields = source.model_dump(exclude={"request_sha256"})
    fields.update(changes)
    return make_post_submit_request(**fields)
