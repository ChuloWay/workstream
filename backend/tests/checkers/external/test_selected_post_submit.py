"""Selected project POST images consume actual ART custody as evidence only."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

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
