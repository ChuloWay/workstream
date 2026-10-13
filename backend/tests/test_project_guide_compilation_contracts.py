from __future__ import annotations

from app.core.config import get_settings

from app.adapters.tasks import task_service

from tests.projects.guide_compilation.helpers import runtime_configuration
from tests.checkers.external.support import registry_spec

from datetime import UTC, datetime
import json
from uuid import uuid4

from app.core.identifiers import new_record_id

import pytest
from pydantic import ValidationError

from app.interfaces.project_agents import (
    AtomicGuideRequirement,
    PreSubmissionBindingProposal,
    PostSubmissionBindingProposal,
    CapabilityParameter,
    CapabilitySuggestion,
    CompilationFinding,
    GuideEvidenceRef,
    PlatformCoverageRef,
    ProjectGuideCompilationContext,
    ProjectGuideCompilationResult,
    SubmissionArtifactPolicyProposal,
    validate_project_guide_compilation_result,
)
from app.modules.projects.api.guide_documents import GuideDocumentManifest, GuideDocumentVersion
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_CHECKER_ID,
    WORKSTREAM_DEFAULT_CHECKER_VERSION,
)
from app.modules.checkers.api.external import (
    ExternalCheckerCapabilityDefinition,
    ExternalCheckerCapabilityProjection,
    ExternalCheckerRegistryEntry,
    external_checker_json_hash,
)


SHA256 = "sha256:" + "a" * 64


@pytest.mark.parametrize(
    "project_limit, default_limit, expected",
    [
        (100, None, 100),
        (None, 50, 50),
        (100, 50, 50),
        (20, 50, 20),
        (None, None, None),
    ],
)
@pytest.mark.parametrize("field", ["maximum_archive_entries", "maximum_archive_size_bytes"])
def test_archive_limit_projection_and_default_floor(
    monkeypatch, project_limit, default_limit, expected, field
):
    from app.modules.projects import service
    from app.modules.projects.guide_compilation.projection_payloads import policy_body

    proposal = SubmissionArtifactPolicyProposal(
        maximum_file_size_bytes=1000,
        maximum_package_size_bytes=2000,
        **{field: project_limit},
    )
    monkeypatch.setitem(service.WORKSTREAM_DEFAULT_SUBMISSION_ARTIFACT_POLICY, field, default_limit)
    body = policy_body(None, proposal)
    assert body[field] == project_limit
    effective = service.ProjectService(None)._merge_effective_submission_artifact_policy(body)
    assert effective[field] == expected
    assert effective["project_policy"][field] == project_limit
    assert effective["workstream_default_policy"][field] == default_limit


@pytest.mark.parametrize("field", ["required_evidence", "attestation_terms"])
@pytest.mark.parametrize(
    "value, valid",
    [
        ("results", True),
        ("a" + "b" * 99, True),
        ("results.v0_1-ok", True),
        ("", False),
        ("a" + "b" * 100, False),
        ("Provide results", False),
        ("evidence/results", False),
        ("9results", False),
        ("Results", False),
    ],
)
def test_policy_identifier_schema_matches_existing_validator(field, value, valid):
    import re
    from app.interfaces.project_agents import _SAFE_IDENTIFIER

    schema = SubmissionArtifactPolicyProposal.model_json_schema()["properties"][field]["items"]
    assert schema["pattern"] == _SAFE_IDENTIFIER.pattern
    assert (schema["minLength"], schema["maxLength"]) == (1, 100)
    assert "machine identifier" in schema["description"]
    assert (re.fullmatch(schema["pattern"], value) is not None) is valid
    arguments = dict(maximum_file_size_bytes=100, maximum_package_size_bytes=1000)
    arguments[field] = (value,)
    if valid:
        assert getattr(SubmissionArtifactPolicyProposal(**arguments), field) == (value,)
    else:
        with pytest.raises(ValidationError, match="identifier is invalid"):
            SubmissionArtifactPolicyProposal(**arguments)


def test_model_schema_describes_existing_expanded_byte_limit():
    properties = SubmissionArtifactPolicyProposal.model_json_schema()["properties"]
    assert "expanded bytes" in properties["maximum_package_size_bytes"]["description"]
    assert "not compressed upload bytes" in properties["maximum_package_size_bytes"]["description"]
    assert (
        "entire submitted compressed ZIP" in properties["maximum_archive_size_bytes"]["description"]
    )
    assert "directory entries" in properties["maximum_archive_entries"]["description"]
    assert "ZIP root" in properties["required_artifacts"]["description"]


@pytest.mark.parametrize("default_limit", [None, 50])
@pytest.mark.parametrize("field", ["maximum_archive_entries", "maximum_archive_size_bytes"])
def test_omitted_optional_archive_limit_preserves_default_floor(monkeypatch, default_limit, field):
    from app.modules.projects import service
    from app.modules.projects.schemas import SubmissionArtifactPolicyInput

    owner = service.ProjectService(None)
    policy = owner._canonical_policy_body(SubmissionArtifactPolicyInput().model_dump())
    del policy[field]
    monkeypatch.setitem(service.WORKSTREAM_DEFAULT_SUBMISSION_ARTIFACT_POLICY, field, default_limit)
    effective = owner._merge_effective_submission_artifact_policy(policy)
    assert effective[field] == default_limit
    assert field not in policy


@pytest.mark.parametrize("limit", [2, None, 0, True])
@pytest.mark.parametrize("field", ["maximum_archive_entries", "maximum_archive_size_bytes"])
def test_task_requirements_response_carries_valid_locked_archive_limit(limit, field):
    from types import SimpleNamespace
    from app.modules.projects.service import ProjectService
    from app.modules.projects.schemas import SubmissionArtifactPolicyInput
    from app.modules.tasks.service import TaskLockedContextInvalid

    owner = ProjectService(None)
    policy = owner._merge_effective_submission_artifact_policy(
        owner._canonical_policy_body(SubmissionArtifactPolicyInput().model_dump())
    )
    policy[field] = limit
    from app.modules.projects.api.locked_policy import CanonicalJsonObject

    context = SimpleNamespace(
        facts=SimpleNamespace(effective_policy=CanonicalJsonObject.from_mapping(policy))
    )
    task = SimpleNamespace(id=str(uuid4()), project_id=str(uuid4()), locked_guide_version="v0.1")
    if limit is not None and (type(limit) is not int or limit <= 0):
        with pytest.raises(TaskLockedContextInvalid):
            task_service(
                None, settings=get_settings()
            )._contributor_submission_requirements_response(task, context)
    else:
        response = task_service(
            None, settings=get_settings()
        )._contributor_submission_requirements_response(task, context)
        assert response.model_dump(mode="json")[field] == limit


SOURCE_ITEM_ID = new_record_id()
DOCUMENT_VERSION_ID = new_record_id()


def _registered_capability(capability_id: str, phase: str, capability_version: str = "v1.2.3"):
    spec = registry_spec(phase).model_copy(
        update={
            "capability_id": capability_id,
            "capability_version": capability_version,
        }
    )
    spec = type(spec).model_validate(spec.model_dump())
    entry = ExternalCheckerRegistryEntry(
        **spec.model_dump(),
        registry_entry_id=new_record_id(),
        entry_digest=spec.spec_digest,
        registration_operation_id=uuid4(),
        registered_by_actor_profile_id=uuid4(),
        authorization_decision_event_id=uuid4(),
        created_at=datetime.now(UTC),
    )
    return ExternalCheckerCapabilityDefinition(
        capability_id=capability_id,
        capability_version=spec.capability_version,
        phase=phase,
        selectable=True,
        registry_entry=entry,
    )


def _capabilities() -> ExternalCheckerCapabilityProjection:
    definitions = tuple(
        sorted(
            (
                ExternalCheckerCapabilityDefinition(
                    capability_id=WORKSTREAM_DEFAULT_CHECKER_ID,
                    capability_version=WORKSTREAM_DEFAULT_CHECKER_VERSION,
                    phase="pre_submit",
                    selectable=False,
                ),
                _registered_capability("acme.pre", "pre_submit"),
                _registered_capability("acme.post", "post_submit"),
            ),
            key=lambda item: (item.phase, item.capability_id, item.capability_version),
        )
    )
    body = {
        "schema_version": "external_checker_capabilities.v1",
        "definitions": [item.model_dump(mode="json") for item in definitions],
    }
    return ExternalCheckerCapabilityProjection(
        definitions=definitions,
        manifest_sha256=external_checker_json_hash(body),
    )


def _context() -> ProjectGuideCompilationContext:
    setup_id = new_record_id()
    material = GuideDocumentManifest(
        project_id=new_record_id(),
        guide_id=new_record_id(),
        guide_version="v1",
        source_snapshot_id=new_record_id(),
        source_snapshot_hash=SHA256,
        setup_run_id=setup_id,
        setup_generation=1,
        documents=(
            GuideDocumentVersion(
                source_item_id=SOURCE_ITEM_ID,
                ingest_id=DOCUMENT_VERSION_ID,
                item_order=0,
                put_attempt_id=new_record_id(),
                content_id=new_record_id(),
                replica_id=new_record_id(),
                storage_namespace_id="primary",
                namespace_fingerprint=SHA256,
                sha256=SHA256,
                byte_count=100,
                media_type="application/pdf",
            ),
        ),
    )
    return ProjectGuideCompilationContext(
        task_examples=({"content": "Review a claim using the project guide."},),
        material=material,
        setup_run_id=setup_id,
        setup_generation=1,
        instruction_version="v1",
        agent_identity="project-guide-compilation-agent-v1",
        agent_version="v1",
        checker_capabilities=_capabilities(),
        runtime_configuration=runtime_configuration(),
    )


def _evidence() -> GuideEvidenceRef:
    return GuideEvidenceRef(
        source_item_id=SOURCE_ITEM_ID,
        document_version_id=DOCUMENT_VERSION_ID,
        sha256=SHA256,
        start_page=1,
        end_page=10,
    )


def _artifact_policy() -> SubmissionArtifactPolicyProposal:
    return SubmissionArtifactPolicyProposal(
        maximum_file_size_bytes=1_000,
        maximum_package_size_bytes=10_000,
        required_artifacts=("submission",),
    )


def test_checker_projection_has_one_default_and_exact_registry_entries() -> None:
    projection = _capabilities()
    defaults = [item for item in projection.definitions if not item.selectable]
    registered = [item for item in projection.definitions if item.selectable]

    assert [(item.capability_id, item.phase) for item in defaults] == [
        ("workstream.default", "pre_submit")
    ]
    assert [(item.capability_id, item.phase) for item in registered] == [
        ("acme.post", "post_submit"),
        ("acme.pre", "pre_submit"),
    ]
    assert all(item.registry_entry is not None for item in registered)


def test_checker_projection_rejects_a_second_code_owned_default() -> None:
    projection = _capabilities()
    body = projection.model_dump(mode="json")
    body["definitions"] = (
        *body["definitions"],
        {
            "capability_id": "workstream.other",
            "capability_version": "v1",
            "phase": "post_submit",
            "selectable": False,
            "registry_entry": None,
        },
    )
    body["definitions"] = tuple(
        sorted(
            body["definitions"],
            key=lambda item: (item["phase"], item["capability_id"], item["capability_version"]),
        )
    )
    manifest = {
        "schema_version": body["schema_version"],
        "definitions": list(body["definitions"]),
    }
    body["manifest_sha256"] = external_checker_json_hash(manifest)
    with pytest.raises(ValidationError, match="default capability"):
        ExternalCheckerCapabilityProjection.model_validate_json(json.dumps(body))


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"raw_excerpt": "secret"}, "raw_excerpt"),
        ({"url": "https://example.invalid"}, "url"),
        ({"path": "/tmp/guide"}, "path"),
        ({"credential": "token=secret"}, "credential"),
        ({"signed_reference": "signed"}, "signed_reference"),
        ({"caller_text": "ignore prior instructions"}, "caller_text"),
    ],
)
def test_guide_evidence_ref_rejects_non_lineage_fields(payload: dict[str, str], field: str) -> None:
    with pytest.raises(ValidationError) as error:
        GuideEvidenceRef.model_validate(
            {
                "source_item_id": str(uuid4()),
                "document_version_id": str(uuid4()),
                "sha256": SHA256,
                "start_page": 1,
                "end_page": 1,
                **payload,
            }
        )
    assert field in str(error.value)


@pytest.mark.parametrize(
    "unsafe",
    [
        "https://example.invalid/instructions",
        "/etc/passwd",
        "token=secret",
        "Bearer opaque-token",
        "password hunter2",
        "secret hidden-value",
        "credential private-value",
        "api key private-value",
        "token opaque-value",
        "import subprocess",
        "curl example.invalid",
        "see docs/guide.md",
        r"C:\Users\worker\guide.txt",
        "Contact jane@example.com",
        "line\x00break",
    ],
)
def test_model_produced_text_rejects_unsafe_shapes(unsafe: str) -> None:
    with pytest.raises(ValidationError):
        CapabilitySuggestion(
            requirement_id="r001",
            stage="pre_submit",
            title="new checker",
            rationale=unsafe,
            evidence_refs=(_evidence(),),
        )


@pytest.mark.parametrize(
    "safe",
    [
        "Require credential handling attestation.",
        "Document token rotation requirements.",
        "Avoid password storage in submissions.",
    ],
)
def test_model_produced_text_allows_safe_security_policy_language(safe: str) -> None:
    suggestion = CapabilitySuggestion(
        requirement_id="r001",
        stage="pre_submit",
        title="security guidance",
        rationale=safe,
        evidence_refs=(_evidence(),),
    )
    assert suggestion.rationale == safe


def test_compilation_context_requires_task_examples_and_preserves_all_input() -> None:
    from app.interfaces.project_agents import project_guide_compilation_prompt_bytes
    import json

    payload = _context().model_dump(mode="json")
    examples = [
        {"content": "A starting idea."},
        {"content": "  修復 worker\n", "title": "Second", "labels": ["research", "repair"]},
    ]
    context = ProjectGuideCompilationContext.model_validate_json(
        json.dumps(payload | {"task_examples": examples})
    )
    sent = json.loads(project_guide_compilation_prompt_bytes(context))
    assert sent["task_examples"] == [item.model_dump(mode="json") for item in context.task_examples]
    del payload["task_examples"]
    with pytest.raises(ValidationError, match="task_examples"):
        ProjectGuideCompilationContext.model_validate(payload)
    with pytest.raises(ValidationError, match="task_examples"):
        ProjectGuideCompilationContext.model_validate(payload | {"task_examples": []})


def test_maximum_examples_and_documents_fit_default_runtime_input_budgets() -> None:
    """Admission's largest text list fits real catalogue and maximum file metadata."""
    import json
    from app.interfaces.project_agents import (
        MAXIMUM_PROJECT_GUIDE_COMPILATION_PROMPT_BYTES,
        canonical_project_guide_compilation_context_bytes,
        project_guide_compilation_prompt_bytes,
    )
    from app.modules.projects.api.task_examples import MAXIMUM_TASK_EXAMPLE_BYTES

    context = _context()
    examples = [
        {"content": "x" * 65_536, "title": None, "labels": []},
        {"content": "", "title": None, "labels": []},
    ]
    overhead = len(json.dumps(examples, sort_keys=True, separators=(",", ":")).encode())
    examples[1]["content"] = "y" * (MAXIMUM_TASK_EXAMPLE_BYTES - overhead)
    assert (
        len(json.dumps(examples, sort_keys=True, separators=(",", ":")).encode())
        == MAXIMUM_TASK_EXAMPLE_BYTES
    )
    prototype = context.material.documents[0].model_dump(mode="json")
    documents = [
        prototype
        | {
            "source_item_id": str(uuid4()),
            "ingest_id": str(uuid4()),
            "put_attempt_id": str(uuid4()),
            "item_order": index,
        }
        for index in range(100)
    ]
    material = context.material.model_dump(mode="json") | {
        "documents": documents,
        "guide_version": "g" * 50,
    }
    largest = ProjectGuideCompilationContext.model_validate_json(
        json.dumps(
            context.model_dump(mode="json") | {"task_examples": examples, "material": material}
        ),
    )
    assert len(largest.task_examples) == 2
    assert len(largest.material.documents) == 100
    assert (
        len(project_guide_compilation_prompt_bytes(largest))
        <= largest.runtime_configuration.maximum_manifest_bytes
    )
    assert (
        len(canonical_project_guide_compilation_context_bytes(largest))
        <= MAXIMUM_PROJECT_GUIDE_COMPILATION_PROMPT_BYTES
    )


def test_unified_result_accepts_exact_stage_capability_and_closed_parameters() -> None:
    context = _context()
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        findings=(
            CompilationFinding(severity="info", code="guide.ready", message="Guide is complete."),
        ),
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.packet",
                statement="Validate the submission packet.",
                disposition="supported_pre_submit",
                evidence_refs=(_evidence(),),
            ),
            AtomicGuideRequirement(
                requirement_id="requirement.acceptance",
                statement="Check acceptance criteria coverage.",
                disposition="supported_post_submit",
            ),
        ),
        pre_submit_bindings=(
            PreSubmissionBindingProposal(
                requirement_id="requirement.packet",
                capability_id="acme.pre",
                capability_version="v1.2.3",
                stage="pre_submit",
            ),
        ),
        post_submit_bindings=(
            PostSubmissionBindingProposal(
                requirement_id="requirement.acceptance",
                capability_id="acme.post",
                capability_version="v1.2.3",
                stage="post_submit",
            ),
        ),
        agent_version="v1",
    )
    validate_project_guide_compilation_result(context, result)


def test_unified_result_selects_each_exact_registered_capability_version() -> None:
    definitions = tuple(
        sorted(
            (
                ExternalCheckerCapabilityDefinition(
                    capability_id=WORKSTREAM_DEFAULT_CHECKER_ID,
                    capability_version=WORKSTREAM_DEFAULT_CHECKER_VERSION,
                    phase="pre_submit",
                    selectable=False,
                ),
                _registered_capability("acme.pre", "pre_submit", "v1.0.0"),
                _registered_capability("acme.pre", "pre_submit", "v2.0.0"),
                _registered_capability("acme.post", "post_submit"),
            ),
            key=lambda item: (item.phase, item.capability_id, item.capability_version),
        )
    )
    body = {
        "schema_version": "external_checker_capabilities.v1",
        "definitions": [item.model_dump(mode="json") for item in definitions],
    }
    capabilities = ExternalCheckerCapabilityProjection(
        definitions=definitions,
        manifest_sha256=external_checker_json_hash(body),
    )
    context = _context().model_copy(update={"checker_capabilities": capabilities})

    for version in ("v1.0.0", "v2.0.0"):
        result = ProjectGuideCompilationResult(
            status="draft_ready",
            submission_artifact_policy=_artifact_policy(),
            requirements=(
                AtomicGuideRequirement(
                    requirement_id="requirement.packet",
                    statement="Validate the submission packet.",
                    disposition="supported_pre_submit",
                ),
            ),
            pre_submit_bindings=(
                PreSubmissionBindingProposal(
                    requirement_id="requirement.packet",
                    capability_id="acme.pre",
                    capability_version=version,
                    stage="pre_submit",
                ),
            ),
            agent_version="v1",
        )
        validate_project_guide_compilation_result(context, result)

    wrong_version = result.model_copy(
        update={
            "pre_submit_bindings": (
                result.pre_submit_bindings[0].model_copy(update={"capability_version": "v1.5.0"}),
            )
        }
    )
    with pytest.raises(ValueError, match="version is stale"):
        validate_project_guide_compilation_result(context, wrong_version)


@pytest.mark.parametrize(
    ("capability_id", "version", "stage", "expected_error"),
    [
        ("workstream.default", "v1", "pre_submit", "binding is invalid"),
        ("acme.pre", "stale", "pre_submit", "version is stale"),
        ("unknown.capability", "v1", "pre_submit", "binding is invalid"),
        (
            "acme.pre",
            "v1.2.3",
            "post_submit",
            "binding is invalid",
        ),
        (
            "acme.post",
            "v1.2.3",
            "pre_submit",
            "binding is invalid",
        ),
    ],
)
def test_unified_result_rejects_default_unknown_stale_and_wrong_stage_bindings(
    capability_id: str, version: str, stage: str, expected_error: str
) -> None:
    context = _context()
    disposition = "supported_post_submit" if stage == "post_submit" else "supported_pre_submit"
    binding_type = (
        PreSubmissionBindingProposal if stage == "pre_submit" else PostSubmissionBindingProposal
    )
    binding = binding_type(
        requirement_id="requirement.one",
        capability_id=capability_id,
        capability_version=version,
        stage=stage,
    )
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.one",
                statement="Validate one requirement.",
                disposition=disposition,
            ),
        ),
        pre_submit_bindings=(binding,) if stage == "pre_submit" else (),
        post_submit_bindings=(binding,) if stage == "post_submit" else (),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match=expected_error):
        validate_project_guide_compilation_result(context, result)


def test_unified_result_rejects_open_nested_or_executable_configuration() -> None:
    with pytest.raises(ValidationError):
        CapabilityParameter(name="required_packet_fields", value={"command": "sh"})
    with pytest.raises(ValidationError):
        CapabilityParameter(name="required_packet_fields", value="import subprocess")
    with pytest.raises(ValidationError):
        PreSubmissionBindingProposal(
            requirement_id="requirement.packet",
            capability_id="policy.submission_packet.validate",
            capability_version="https://unsafe.invalid",
            stage="pre_submit",
        )
    with pytest.raises(ValidationError):
        PlatformCoverageRef(
            capability_id="artifact.outer_zip.valid",
            capability_version="https://unsafe.invalid",
            stage="pre_submit",
        )
    with pytest.raises(ValidationError):
        CapabilityParameter(name="required_packet_fields", value=float("nan"))
    with pytest.raises(ValidationError):
        SubmissionArtifactPolicyProposal(
            maximum_file_size_bytes="1000",
            maximum_package_size_bytes=10_000,
        )
    with pytest.raises(ValidationError):
        GuideEvidenceRef(
            source_item_id=SOURCE_ITEM_ID,
            document_version_id=DOCUMENT_VERSION_ID,
            sha256=SHA256,
            start_page="0",
            end_page=1,
        )


def test_external_registry_resource_budget_is_deeply_frozen() -> None:
    projection = _capabilities()
    registered = next(item for item in projection.definitions if item.registry_entry)
    with pytest.raises(ValidationError):
        registered.registry_entry.resources.deadline_ms = 99


@pytest.mark.parametrize("field", ["canonical_content", "content_markdown", "provider_url"])
def test_manifest_rejects_document_bodies_and_untrusted_storage_coordinates(field):
    body = _context().material.model_dump(mode="python")
    with pytest.raises(ValidationError, match=field):
        GuideDocumentManifest.model_validate(body | {field: "untrusted content"})


@pytest.mark.parametrize(
    "field", ["source_item_id", "ingest_id", "put_attempt_id", "replica_id", "sha256"]
)
def test_manifest_requires_exact_document_identity(field):
    body = _context().material.model_dump(mode="python")
    document = dict(body["documents"][0])
    del document[field]
    body["documents"] = [document]
    with pytest.raises(ValidationError, match=field):
        GuideDocumentManifest.model_validate(body)


def test_compilation_material_snapshot_cannot_drift_after_validation() -> None:
    snapshot = _context().material
    with pytest.raises(ValidationError):
        snapshot.documents = ()
    with pytest.raises(TypeError):
        snapshot.documents[0] = snapshot.documents[0]
    with pytest.raises(ValidationError):
        snapshot.documents[0].sha256 = "sha256:" + "b" * 64
    body = snapshot.model_dump(mode="python")
    document = dict(body["documents"][0])
    document["sha256"] = "sha256:" + "b" * 64
    changed = GuideDocumentManifest.model_validate(body | {"documents": [document]})
    assert changed.sha256 != snapshot.sha256


def test_unified_result_rejects_unresolved_evidence_lineage() -> None:
    context = _context()
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        findings=(
            CompilationFinding(
                severity="info",
                code="guide.ready",
                message="Guide is complete.",
                evidence_refs=(
                    GuideEvidenceRef(
                        source_item_id=uuid4(),
                        document_version_id=DOCUMENT_VERSION_ID,
                        sha256=SHA256,
                        start_page=1,
                        end_page=1,
                    ),
                ),
            ),
        ),
        submission_artifact_policy=_artifact_policy(),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="source lineage"):
        validate_project_guide_compilation_result(context, result)


def test_supported_requirement_requires_exactly_one_binding() -> None:
    context = _context()
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.packet",
                statement="Validate the submission packet.",
                disposition="supported_pre_submit",
            ),
        ),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="must have one binding"):
        validate_project_guide_compilation_result(context, result)


def test_post_submission_binding_rejects_unowned_parameters() -> None:
    context = _context()
    binding = PostSubmissionBindingProposal(
        requirement_id="requirement.one",
        capability_id="acme.post",
        capability_version="v1.2.3",
        stage="post_submit",
        parameters=(CapabilityParameter(name="unowned_parameter", value=True),),
    )
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.one",
                statement="Validate one requirement.",
                disposition="supported_post_submit",
            ),
        ),
        post_submit_bindings=(binding,),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="value is invalid"):
        validate_project_guide_compilation_result(context, result)


@pytest.mark.parametrize(
    ("status", "finding_severity", "disposition", "expected_error"),
    [
        ("draft_ready", "blocking_gap", "informational", "cannot contain blocking"),
        ("draft_ready", "info", "guide_blocker", "cannot contain blocking"),
        ("draft_ready", "warning", "informational", "cannot contain warnings"),
        (
            "draft_ready_with_warnings",
            "info",
            "informational",
            "requires a warning",
        ),
        ("guide_blocked", "info", "informational", "requires blocking evidence"),
    ],
)
def test_result_status_must_match_findings_and_blocking_dispositions(
    status: str, finding_severity: str, disposition: str, expected_error: str
) -> None:
    result = ProjectGuideCompilationResult(
        status=status,
        findings=(
            CompilationFinding(
                severity=finding_severity,
                code="guide.status",
                message="Guide status evidence.",
            ),
        ),
        submission_artifact_policy=(None if status == "guide_blocked" else _artifact_policy()),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.status",
                statement="Check guide status.",
                disposition=disposition,
            ),
        ),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match=expected_error):
        validate_project_guide_compilation_result(_context(), result)


@pytest.mark.parametrize(
    "invalid_capability_id",
    ["acme.pre", "unknown.capability"],
)
def test_platform_coverage_requires_exact_mandatory_platform_capability(
    invalid_capability_id: str,
) -> None:
    context = _context()
    valid = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.zip",
                statement="Validate the outer ZIP.",
                disposition="platform_covered",
                platform_coverage=PlatformCoverageRef(
                    capability_id="workstream.default",
                    capability_version="v1",
                    stage="pre_submit",
                ),
            ),
        ),
        agent_version="v1",
    )
    validate_project_guide_compilation_result(context, valid)

    invalid = valid.model_copy(
        update={
            "requirements": (
                valid.requirements[0].model_copy(
                    update={
                        "platform_coverage": PlatformCoverageRef(
                            capability_id=invalid_capability_id,
                            capability_version="v1",
                            stage="pre_submit",
                        )
                    }
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="canonical truth"):
        validate_project_guide_compilation_result(context, invalid)


def test_platform_coverage_rejects_registered_project_image() -> None:
    context = _context()
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.zip",
                statement="Validate the outer ZIP.",
                disposition="platform_covered",
                platform_coverage=PlatformCoverageRef(
                    capability_id="acme.pre",
                    capability_version="v1.2.3",
                    stage="pre_submit",
                ),
            ),
        ),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="canonical truth"):
        validate_project_guide_compilation_result(context, result)


def test_platform_coverage_rejects_post_submit_project_image() -> None:
    result = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.packet",
                statement="Run the platform submission-packet check.",
                disposition="platform_covered",
                platform_coverage=PlatformCoverageRef(
                    capability_id="acme.post",
                    capability_version="v1.2.3",
                    stage="post_submit",
                ),
            ),
        ),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="canonical truth"):
        validate_project_guide_compilation_result(_context(), result)


def test_platform_coverage_ref_is_required_only_for_platform_disposition() -> None:
    missing = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.coverage",
                statement="Require canonical coverage proof.",
                disposition="platform_covered",
            ),
        ),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="requires canonical proof"):
        validate_project_guide_compilation_result(_context(), missing)

    misplaced = ProjectGuideCompilationResult(
        status="draft_ready",
        submission_artifact_policy=_artifact_policy(),
        requirements=(
            AtomicGuideRequirement(
                requirement_id="requirement.info",
                statement="Record an informational requirement.",
                disposition="informational",
                platform_coverage=PlatformCoverageRef(
                    capability_id="artifact.outer_zip.valid",
                    capability_version="v1",
                    stage="pre_submit",
                ),
            ),
        ),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="cannot claim platform coverage"):
        validate_project_guide_compilation_result(_context(), misplaced)


def test_blocked_result_cannot_publish_policy_or_bindings() -> None:
    context = _context()
    result = ProjectGuideCompilationResult(
        status="guide_blocked",
        findings=(
            CompilationFinding(
                severity="blocking_gap",
                code="guide.blocked",
                message="Guide has a blocking gap.",
            ),
        ),
        submission_artifact_policy=_artifact_policy(),
        agent_version="v1",
    )
    with pytest.raises(ValueError, match="blocked guide"):
        validate_project_guide_compilation_result(context, result)


@pytest.mark.parametrize("parameters", [[], [{"name": "maximum_file_size_bytes", "value": 1000}]])
def test_pre_submission_binding_accepts_explicit_checker_configuration(parameters):
    """Approved PRE image configuration is distinct from platform intake limits."""
    binding = PreSubmissionBindingProposal(
        requirement_id="requirement.size",
        capability_id="policy.file_size.limit",
        capability_version="v1",
        stage="pre_submit",
        parameters=parameters,
    )
    assert [item.model_dump(mode="json") for item in binding.parameters] == parameters


def test_context_rejects_instruction_version_separate_from_snapshot() -> None:
    payload = _context().model_dump(mode="json")
    payload["instruction_version"] = "different"
    with pytest.raises(ValidationError, match="instruction configuration mismatch"):
        ProjectGuideCompilationContext.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize("value", ["outputs/answer.md", "src/main.py", "tests/**/*.py"])
def test_checker_configuration_accepts_canonical_relative_paths(value: str) -> None:
    parameter = CapabilityParameter(name="required_path", value=value)
    assert parameter.value == value


@pytest.mark.parametrize("value", [
    "/etc/passwd", "../answer.md", "src/../answer.md", "https://example.invalid/x",
    "file:///tmp/x", "src/answer.md\x00", "src/$(command)", "bash/run",
    "token=secret", "Bearer opaque-token", "import subprocess", "src\\main.py",
])
def test_checker_configuration_rejects_unsafe_machine_values(value: str) -> None:
    with pytest.raises(ValidationError):
        CapabilityParameter(name="required_path", value=value)
