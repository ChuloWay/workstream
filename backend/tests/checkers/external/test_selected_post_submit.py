"""Selected project POST images consume actual ART custody as evidence only."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.adapters.checkers import selected_submission_evaluation_content
from app.core.hashing import canonical_json_hash
from app.interfaces.external_checker_execution import (
    ExternalCheckerExecutionResponse,
    ExternalCheckerIsolationReceipt,
    ExternalCheckerMaterialGrant,
)
from app.modules.checkers.api.external import (
    POST_SUBMIT_INPUT_SCHEMA_ID,
    ExternalCheckerRegistryEntry,
    ExternalCheckerSchema,
    external_checker_json_hash,
    make_external_checker_execution_result,
)
from app.modules.checkers.api.external_policy import (
    LockedExternalCheckerBinding,
    LockedExternalPostSubmitPolicy,
)
from app.modules.checkers.api.materialization import SubmissionMaterialEntry
from app.modules.checkers.selected_post_submit_execution import (
    SelectedPostSubmitProcessor,
)
from app.modules.checkers.api.selected_post_submit import (
    SelectedPostSubmitLockedContext,
    make_selected_post_submit_request,
    make_selected_post_submit_result,
)
from app.core.identifiers import new_record_id
from tests.checkers.external.support import (
    SHA,
    execution_identity,
    execution_material,
    registry_entry,
)


def _policy() -> LockedExternalPostSubmitPolicy:
    values = registry_entry("post_submit").model_dump()
    document = {"type": "object"}
    values["input_schema"] = ExternalCheckerSchema(
        schema_id=POST_SUBMIT_INPUT_SCHEMA_ID,
        schema_version="v1",
        document=document,
        schema_sha256=external_checker_json_hash(document),
    )
    spec = {
        key: value
        for key, value in values.items()
        if key
        not in {
            "registry_entry_id",
            "entry_digest",
            "registration_operation_id",
            "registered_by_actor_profile_id",
            "authorization_decision_event_id",
            "created_at",
        }
    }
    spec["input_schema"] = values["input_schema"].model_dump(mode="json")
    values["entry_digest"] = external_checker_json_hash(spec)
    binding = LockedExternalCheckerBinding(
        requirement_id="project.post_evidence",
        stage="post_submit",
        registry=ExternalCheckerRegistryEntry.model_validate(values),
        configuration={},
        configuration_sha256=external_checker_json_hash({}),
    )
    body = {
        "schema_version": "external_post_submit_policy.v1",
        "entries": [binding.model_dump(mode="json")],
    }
    return LockedExternalPostSubmitPolicy(
        entries=(binding,),
        policy_sha256=canonical_json_hash(body),
    )


class _MaterialView:
    def __init__(self, material) -> None:
        self.external_checker_material = material
        self.entries = (
            SubmissionMaterialEntry("src/main.py", "file", 4, SHA, False),
        )
        self.requests = []

    @contextmanager
    def external_checker_grant(self, request):
        self.requests.append(request)
        yield ExternalCheckerMaterialGrant(
            grant_id="extract_" + "a" * 32,
            binding_digest="sha256:" + "b" * 64,
        )


class _Execution:
    def __init__(self, *, outcome="completed", verdict="passed") -> None:
        self.outcome, self.verdict = outcome, verdict
        self.requests = []

    async def execute(self, request, _grant):
        self.requests.append(request)
        infrastructure = self.outcome == "infrastructure_failed"
        findings = () if self.verdict == "passed" or infrastructure else ({
            "code": "post_evidence_failed",
            "level": "error",
            "message": "Post evidence failed.",
        },)
        result = make_external_checker_execution_result(
            request_digest=request.request_digest,
            registry_entry_id=request.registry.registry_entry_id,
            registry_entry_digest=request.registry.entry_digest,
            phase="post_submit",
            outcome=self.outcome,
            verdict=None if infrastructure else self.verdict,
            findings=findings,
            infrastructure_failure_code="deadline_exceeded" if infrastructure else None,
        )
        return ExternalCheckerExecutionResponse(
            result=result,
            isolation=None if infrastructure else ExternalCheckerIsolationReceipt(
                repository="registry.example/workstream/checker",
                platform_manifest_digest=request.registry.image_digest,
                platform_manifest_media_type="application/vnd.oci.image.manifest.v1+json",
                platform_manifest_byte_count=1024,
                operating_system="linux",
                architecture="amd64",
                config_image_id=SHA,
                runtime="runsc",
                isolation_mode="gvisor",
                sandbox_uid=65532,
                sandbox_gid=65532,
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", ["passed", "failed"])
async def test_selected_post_runs_every_locked_image_without_acceptance(verdict) -> None:
    identity = execution_identity("post_submit")
    material = execution_material(identity)
    view, execution, policy = _MaterialView(material), _Execution(verdict=verdict), _policy()
    result = await SelectedPostSubmitProcessor(
        policy=policy,
        identity=identity,
        execution=execution,
    ).evaluate(object(), view)

    assert len(result.external_members) == 1
    assert result.external_members[0].result.verdict == verdict
    assert result.result_digest == canonical_json_hash(result.canonical_body())
    assert len(view.requests) == len(execution.requests) == 1
    assert view.requests[0].identity.submission_id == identity.submission_id
    assert "routing" not in result.canonical_body()
    assert "accepted" not in result.canonical_body()


@pytest.mark.asyncio
async def test_selected_post_separates_infrastructure_from_work_findings() -> None:
    identity = execution_identity("post_submit")
    with pytest.raises(RuntimeError, match="deadline_exceeded"):
        await SelectedPostSubmitProcessor(
            policy=_policy(),
            identity=identity,
            execution=_Execution(outcome="infrastructure_failed"),
        ).evaluate(object(), _MaterialView(execution_material(identity)))


@pytest.mark.asyncio
async def test_selected_post_request_and_result_bind_exact_locked_policy() -> None:
    identity = execution_identity("post_submit")
    policy = _policy()
    context = SelectedPostSubmitLockedContext(
        guide_version="guide-v1",
        source_id=new_record_id(),
        source_hash=SHA,
        effective_policy_id=new_record_id(),
        effective_policy_hash=SHA,
        pre_policy_id=new_record_id(),
        pre_policy_hash=SHA,
        retained_catalogue_policy_id=new_record_id(),
        retained_catalogue_policy_version="guide-v1",
        retained_catalogue_policy_hash=SHA,
        selected_post_policy_hash=policy.policy_sha256,
        review_policy_id=new_record_id(),
        review_generation=1,
        review_hash=SHA,
        revision_policy_id=new_record_id(),
        revision_generation=1,
        revision_hash=SHA,
    )
    request = make_selected_post_submit_request(
        project_id=identity.project_id,
        expected_context=context,
        policy=policy,
        evaluation_request_id=identity.evaluation_request_id,
        evaluation_generation=identity.evaluation_generation,
        task_id=identity.task_id,
        assignment_id=identity.assignment_id,
        submission_id=identity.submission_id,
        submission_version=identity.submission_version,
        content_id=new_record_id(),
        binding_id=new_record_id(),
        content_sha256=SHA,
        byte_count=42,
    )
    execution = await SelectedPostSubmitProcessor(
        policy=policy,
        identity=identity,
        execution=_Execution(),
    ).evaluate(request, _MaterialView(execution_material(identity)))
    result = make_selected_post_submit_result(
        request_id=request.evaluation_request_id,
        request_digest=request.request_sha256,
        attempt_id=identity.attempt_id,
        evaluation_generation=request.evaluation_generation,
        result_id=identity.result_id,
        outcome="completed",
        execution=execution,
        infrastructure_failure_code=None,
    )

    result.validate_request(request)
    empty_policy = LockedExternalPostSubmitPolicy(
        entries=(),
        policy_sha256=canonical_json_hash(
            {
                "schema_version": "external_post_submit_policy.v1",
                "entries": [],
            }
        ),
    )
    with pytest.raises(ValueError, match="request mismatch"):
        result.validate_request(
            make_selected_post_submit_request(
                **request.model_dump(
                    exclude={"request_sha256", "policy", "expected_context"},
                ),
                policy=empty_policy,
                expected_context=context.model_copy(
                    update={
                        "selected_post_policy_hash": empty_policy.policy_sha256
                    }
                ),
            )
        )


def test_selected_post_content_uses_selected_digest_not_catalogue_hash() -> None:
    policy = _policy()
    locked = SimpleNamespace(
        locked_guide_version="guide-v1",
        locked_guide_source_snapshot_id=new_record_id(),
        locked_guide_source_snapshot_hash=SHA,
        locked_effective_project_submission_artifact_policy_id=new_record_id(),
        locked_effective_project_submission_artifact_policy_hash=SHA,
        locked_pre_submit_checker_policy_id=new_record_id(),
        locked_pre_submit_checker_bundle_hash=SHA,
        locked_post_submit_checker_policy_hash="sha256:" + "1" * 64,
        locked_post_submit_checker_policy_id=new_record_id(),
        locked_post_submit_checker_policy_version="guide-v1",
        locked_review_policy_id=new_record_id(),
        locked_review_policy_generation=1,
        locked_review_policy_hash=SHA,
        locked_revision_policy_id=new_record_id(),
        locked_revision_policy_generation=1,
        locked_revision_policy_hash=SHA,
    )
    task = SimpleNamespace(
        locked_policy=locked,
        locked_project_context=SimpleNamespace(project_id=new_record_id()),
    )

    content = selected_submission_evaluation_content(task, policy)

    assert content.expected_context.selected_post_policy_hash == policy.policy_sha256
    assert (
        content.expected_context.selected_post_policy_hash
        != locked.locked_post_submit_checker_policy_hash
    )
