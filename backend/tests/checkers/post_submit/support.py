"""Controlled owner facts; no future database rows, authorization, or worker fixtures."""

from uuid import UUID, uuid4

from app.core.hashing import canonical_json_hash
from app.modules.checkers.api import (
    ExpectedPostSubmitContext,
    ObservedPostSubmitContext,
    PostSubmissionStructuralInput,
    PostSubmitEvidenceEntry,
    PostSubmitManifestEntry,
    PostSubmitPolicyInputs,
)
from app.modules.checkers.api.post_submit_catalogue import PostSubmitCatalogue, PostSubmitDefinition
from app.modules.checkers.post_submit_catalogue import build_post_submit_catalogue
from app.modules.checkers.post_submit_contracts import make_post_submit_request
from app.modules.checkers.runner import default_checker_registry
from app.modules.projects.post_submit_policy import compile_post_submit_policy_v2

HASH = "sha256:" + "a" * 64
OTHER_HASH = "sha256:" + "b" * 64
PROJECT = UUID("11111111-1111-4111-8111-111111111111")


def catalogue():
    return build_post_submit_catalogue(default_checker_registry())


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
    policy = compile_post_submit_policy_v2(
        project_id=project_id,
        guide_version="v1",
        catalogue=snapshot,
        required_checkers=("check_acceptance_criteria_present",),
    )
    fields = {}
    for name in ExpectedPostSubmitContext.model_fields:
        if name.endswith("_id"):
            fields[name] = uuid4()
        elif "version" in name:
            fields[name] = "v1"
        elif name.endswith("generation"):
            fields[name] = 1
        else:
            fields[name] = HASH
    fields.update(project_id=project_id, post_policy_hash=policy.policy_hash)
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
        evaluation_request_id=uuid4(),
        evaluation_generation=1,
        project_id=project_id,
        task_id=uuid4(),
        assignment_id=uuid4(),
        submission_id=uuid4(),
        submission_version=1,
        content_id=uuid4(),
        binding_id=uuid4(),
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
