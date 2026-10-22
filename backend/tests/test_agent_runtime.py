"""One replaceable runtime, exact configuration custody, and untrusted output tests."""

from __future__ import annotations

import asyncio
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime
from app.core.config import Settings
from app.core.project_agents import (
    project_guide_runtime_configuration,
)
from app.core.project_guide_instructions import PROJECT_GUIDE_INSTRUCTIONS
from app.interfaces.project_agents import (
    ProjectAgentRuntimeError,
    ProjectAgentRuntimeConfigurationError,
    ProjectGuideCompilationInvalidOutputError,
    canonical_project_guide_compilation_context_bytes,
    invalid_compilation_failure_code,
    project_guide_compilation_prompt_bytes,
)
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from app.modules.projects.api.guide_documents import GuideDocumentManifest
from tests.projects.guide_compilation.helpers import (
    SOURCE_SHA256, context, ids, generated_result as result, runtime_configuration,
)


@pytest.fixture(autouse=True)
def model_credentials(monkeypatch):
    """Use a test-only credential; SDK execution is replaced in every invocation test."""
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-only")


@pytest.fixture(autouse=True)
def scripted_workspace(monkeypatch):
    """Keep these SDK/parser tests network-free; workspace access has separate proof."""
    from app.adapters.project_agents import openai_agent_sdk

    class Workspace:
        container_id = "cntr_test_owned"

        def __init__(self, *args):
            pass

        async def start(self):
            pass

        async def close(self):
            pass

    monkeypatch.setattr(openai_agent_sdk, "OpenAIGuideWorkspace", Workspace)


async def _compile(runtime, compilation_context):
    """Supply scripted prior document access and always release circuit admission."""
    async def opened_handles():
        return frozenset(compilation_context.material.handle_for(document)
                         for document in compilation_context.material.documents)

    capabilities = SimpleNamespace(resources=SimpleNamespace(opened_handles=opened_handles))
    runtime.admit_execution()
    try:
        return await runtime.compile_project_guide(compilation_context, capabilities)
    finally:
        await runtime.aclose()


def test_unified_compilation_instructions_preserve_untrusted_and_lifecycle_boundaries():
    for text in ("untrusted", "pre-submit", "post-submit", "ProjectGuideCompilationAgent"):
        assert text in PROJECT_GUIDE_INSTRUCTIONS


def test_runtime_requires_credentials_before_dispatch(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(ProjectAgentRuntimeConfigurationError, match="credentials are unavailable"):
        OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())


def test_configuration_concerns_are_independent_and_secret_free():
    settings = Settings(
        project_agent_model="configured-model", project_agent_instructions="Trusted instructions."
    )
    configuration = project_guide_runtime_configuration(settings)
    assert configuration.model == "configured-model"
    assert configuration.instructions == "Trusted instructions."
    assert configuration.runtime_key == "openai_agents_sdk"
    assert "unit-test-only" not in configuration.model_dump_json()
    assert (
        configuration.instructions_sha256
        == "sha256:" + hashlib.sha256(b"Trusted instructions.").hexdigest()
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"instructions_sha256": "sha256:" + "0" * 64},
        {"api_key": "not-allowed"}, {"timeout_seconds": True}, {"timeout_seconds": 0},
        {"maximum_manifest_bytes": 1_000_001}, {"maximum_documents": 101},
        {"request_timeout_seconds": 0}, {"maximum_retries": 6}, {"retry_jitter": 1},
        {"model": ""}, {"model_provider": "uninstalled"},
    ],
)
def test_runtime_snapshot_rejects_invalid_or_secret_bearing_shapes(patch):
    with pytest.raises(ValidationError):
        ProjectGuideRuntimeConfiguration.model_validate(
            runtime_configuration().model_dump() | patch
        )


def test_snapshot_changes_identity_but_is_absent_from_provider_user_prompt():
    original = context(ids())
    changed = original.model_copy(
        update={
            "runtime_configuration": original.runtime_configuration.model_copy(
                update={"model": "another-model"}
            )
        }
    )
    assert canonical_project_guide_compilation_context_bytes(
        original
    ) != canonical_project_guide_compilation_context_bytes(changed)
    assert project_guide_compilation_prompt_bytes(
        original
    ) == project_guide_compilation_prompt_bytes(changed)
    prompt = json.loads(project_guide_compilation_prompt_bytes(original))
    assert "runtime_configuration" not in prompt
    assert isinstance(prompt["material"]["documents"], list)
    assert "namespace_fingerprint" not in json.dumps(prompt)
    assert "provider_object_ref" not in json.dumps(prompt)


async def test_unified_compilation_uses_scoped_tools_and_strict_output(monkeypatch):
    from agents import Runner, CodeInterpreterTool, FunctionTool
    import openai

    clients = []
    client_type = openai.AsyncOpenAI

    def create_client(**kwargs):
        client = client_type(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(openai, "AsyncOpenAI", create_client)
    configuration = runtime_configuration()
    compilation_context = context(ids())
    calls = []

    async def run(agent, prompt, **kwargs):
        calls.append((agent, prompt, kwargs))
        assert agent.instructions == configuration.instructions
        assert len(agent.tools) == 2 and agent.handoffs == []
        assert isinstance(agent.tools[0], FunctionTool)
        assert agent.tools[0].name == "open_guide_document"
        assert isinstance(agent.tools[1], CodeInterpreterTool)
        assert agent.tools[1].tool_config["container"] == "cntr_test_owned"
        assert agent.model.model == configuration.model
        assert agent.output_type.is_strict_json_schema() is True
        assert kwargs["max_turns"] == configuration.maximum_turns
        assert kwargs["run_config"].tracing_disabled is True
        assert kwargs["run_config"].trace_include_sensitive_data is False
        assert agent.model_settings.store is False
        assert agent.model_settings.parallel_tool_calls is False
        assert agent.model_settings.retry.max_retries == configuration.maximum_retries
        assert "runtime_configuration" not in json.loads(prompt)
        return SimpleNamespace(final_output=result())

    monkeypatch.setattr(Runner, "run", run)
    output = await _compile(OpenAIAgentSdkProjectGuideRuntime(configuration), compilation_context)
    assert output == result()
    assert len(calls) == len(clients) == 1
    assert clients[0].max_retries == 0 and clients[0].is_closed()
    assert clients[0].timeout == min(configuration.request_timeout_seconds, configuration.timeout_seconds)
    assert str(clients[0].base_url).rstrip("/") == "https://api.openai.com/v1"


@pytest.mark.parametrize("kind", ["mapping", "json", "model"])
async def test_unified_runtime_accepts_complete_sdk_output(monkeypatch, kind):
    output = result()
    value = (
        output.model_dump(mode="json")
        if kind == "mapping"
        else output.model_dump_json()
        if kind == "json"
        else output
    )

    async def run(*args):
        return value

    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())
    monkeypatch.setattr(runtime, "_run", run)
    assert await _compile(runtime, context(ids())) == output


@pytest.mark.parametrize(
    "patch",
    [
        {"agent_version": "wrong"},
        {"status": "guide_blocked"},
        {"findings": [{"severity": "info", "code": "bad", "message": "token=secret123"}]},
    ],
)
async def test_unified_runtime_rejects_invalid_provider_output(monkeypatch, patch):
    async def run(*args):
        return result().model_dump(mode="json") | patch

    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())
    monkeypatch.setattr(runtime, "_run", run)
    with pytest.raises(ProjectGuideCompilationInvalidOutputError):
        await _compile(runtime, context(ids()))


async def test_unified_runtime_rejects_omitted_output_member(monkeypatch):
    output = result().model_dump(mode="json")
    del output["findings"]

    async def run(*args):
        return output

    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())
    monkeypatch.setattr(runtime, "_run", run)
    with pytest.raises(
        ProjectGuideCompilationInvalidOutputError, match="invalid structured output"
    ):
        await _compile(runtime, context(ids()))


async def test_oversized_prompt_is_rejected_before_sdk_execution(monkeypatch):
    configuration = runtime_configuration().model_copy(update={"maximum_manifest_bytes": 1024})
    runtime = OpenAIAgentSdkProjectGuideRuntime(configuration)

    async def forbidden(*args):
        pytest.fail("oversized prompt reached provider")

    monkeypatch.setattr(runtime, "_run", forbidden)
    with pytest.raises(ProjectAgentRuntimeError, match="size limit"):
        await _compile(runtime,
            context(ids()).model_copy(update={"runtime_configuration": configuration})
        )


async def test_runtime_rejects_context_configuration_substitution(monkeypatch):
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())

    async def forbidden(*args):
        pytest.fail("different configuration reached provider")

    monkeypatch.setattr(runtime, "_run", forbidden)
    changed = context(ids()).model_copy(
        update={
            "runtime_configuration": runtime_configuration().model_copy(update={"model": "changed"})
        }
    )
    with pytest.raises(ProjectAgentRuntimeConfigurationError, match="configuration mismatch"):
        await _compile(runtime, changed)


@pytest.mark.parametrize(
    "error", [RuntimeError("private provider detail"), TimeoutError("private timeout")]
)
async def test_runtime_failure_is_sanitized(monkeypatch, error):
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())

    async def run(*args):
        raise error

    monkeypatch.setattr(runtime, "_run", run)
    with pytest.raises(ProjectAgentRuntimeError) as caught:
        await _compile(runtime, context(ids()))
    assert "private" not in str(caught.value)
    assert caught.value.__suppress_context__


async def test_unified_compilation_propagates_caller_cancellation(monkeypatch):
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())
    started = asyncio.Event()

    async def run(*args):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(runtime, "_run", run)
    task = asyncio.create_task(_compile(runtime, context(ids())))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_invalid_compilation_classifier_separates_unsafe_text_from_schema_errors():
    assert (
        invalid_compilation_failure_code(ValueError("model-produced text is unsafe"))
        == "unsafe_text"
    )
    assert invalid_compilation_failure_code(TypeError("unknown")) == "schema_invalid"


async def test_runtime_internal_cancellation_is_sanitized(monkeypatch):
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())

    async def run(*args):
        raise asyncio.CancelledError("private provider cancellation")

    monkeypatch.setattr(runtime, "_run", run)
    with pytest.raises(ProjectAgentRuntimeError, match="project guide run cancelled") as caught:
        await _compile(runtime, context(ids()))
    assert "private" not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.parametrize("kind, expected", [
    ("valid", None), ("malformed", "schema_invalid"),
    ("schema", "schema_invalid"), ("unsafe", "schema_invalid"),
])
@pytest.mark.parametrize("redacted", [True, False])
async def test_actual_sdk_parser_preserves_known_invalid_output(monkeypatch, kind, expected, redacted):
    """Exercise the installed SDK parser before the adapter receives any result."""
    from agents import Runner

    from agents import _debug
    monkeypatch.setattr(_debug, "DONT_LOG_MODEL_DATA", redacted)
    payload = result().model_dump(mode="json")
    if kind == "schema":
        payload["status"] = "not-a-status"
    if kind == "unsafe":
        payload["findings"] = [{"severity": "info", "code": "bad", "message": "token=secret123"}]
    raw = "{invalid" if kind == "malformed" else json.dumps(payload)
    calls = []

    async def run(agent, *args, **kwargs):
        calls.append(1)
        return SimpleNamespace(final_output=agent.output_type.validate_json(raw))

    monkeypatch.setattr(Runner, "run", run)
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())
    if expected is None:
        assert await _compile(runtime, context(ids())) == result()
    else:
        with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
            await _compile(runtime, context(ids()))
        assert caught.value.failure_code == expected
        assert "secret123" not in str(caught.value)
        assert caught.value.__suppress_context__
    assert calls == [1]


async def test_unclassified_sdk_behavior_error_remains_unresolved(monkeypatch):
    """A generic SDK behavior error is not proof of structured-output rejection."""
    from agents import Runner
    from agents.exceptions import ModelBehaviorError

    async def run(*args, **kwargs):
        raise ModelBehaviorError("private provider detail")

    monkeypatch.setattr(Runner, "run", run)
    with pytest.raises(ProjectAgentRuntimeError, match="project guide run failed"):
        await _compile(OpenAIAgentSdkProjectGuideRuntime(runtime_configuration()), context(ids()))


async def _capture_parser_error(runtime):
    """Capture outside the payload-owning test frame, as a runtime caller would."""
    try:
        await _compile(runtime, context(ids()))
    except ProjectGuideCompilationInvalidOutputError as error:
        return error
    pytest.fail("invalid SDK output did not raise")


@pytest.mark.parametrize("redacted", [True, False])
async def test_sdk_parser_error_drops_payload_tracebacks(monkeypatch, redacted):
    """A diagnostic collector must not recover rejected output through the error graph."""
    from agents import Runner, _debug

    marker = "private-parser-output-79436"
    payload = result().model_dump(mode="json")
    payload["findings"] = [{"severity": "info", "code": "bad", "message": f"token={marker}"}]
    raw = json.dumps(payload)
    monkeypatch.setattr(_debug, "DONT_LOG_MODEL_DATA", redacted)

    async def run(agent, *args, **kwargs):
        return SimpleNamespace(final_output=agent.output_type.validate_json(raw))

    monkeypatch.setattr(Runner, "run", run)
    error = await _capture_parser_error(OpenAIAgentSdkProjectGuideRuntime(runtime_configuration()))
    assert error.failure_code == "schema_invalid"
    pending = [error]
    seen = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        assert marker not in str(current)
        traceback = current.__traceback__
        while traceback is not None:
            assert marker not in repr(traceback.tb_frame.f_locals)
            traceback = traceback.tb_next
        pending.extend(link for link in (current.__cause__, current.__context__) if link is not None)


async def _capture_runtime_failure(runtime):
    try:
        await _compile(runtime, context(ids()))
    except ProjectAgentRuntimeError as error:
        return error
    pytest.fail("runtime failure did not raise")


@pytest.mark.parametrize("boundary", ["provider", "post_parser_validation"])
async def test_sanitized_error_graph_drops_provider_and_invalid_values(monkeypatch, boundary):
    marker = "private-runtime-output-78219"
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())

    async def run(*args):
        if boundary == "provider":
            raise RuntimeError(marker)
        payload = result().model_dump(mode="json")
        payload["setup_notes"] = ["token=" + marker]
        return payload

    monkeypatch.setattr(runtime, "_run", run)
    error = (await _capture_runtime_failure(runtime) if boundary == "provider"
             else await _capture_parser_error(runtime))
    pending, seen = [error], set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        assert marker not in str(current)
        frame = current.__traceback__
        while frame is not None:
            assert marker not in repr(frame.tb_frame.f_locals)
            frame = frame.tb_next
        pending.extend(link for link in (current.__cause__, current.__context__) if link is not None)


def test_sdk_output_schema_exposes_the_identifier_rule_to_the_model():
    """The provider sees the same bounded lowercase rule that parsing enforces."""
    import re
    from agents import AgentOutputSchema
    from app.interfaces.project_agents import ProjectGuideCompilationResult

    schema = AgentOutputSchema(ProjectGuideCompilationResult).json_schema()
    for owner, field in (
        ("AtomicGuideRequirement", "requirement_id"),
        ("PreSubmissionBindingProposal", "requirement_id"),
        ("PreSubmissionBindingProposal", "capability_id"),
        ("PreSubmissionBindingProposal", "capability_version"),
        ("PlatformCoverageRef", "capability_id"),
        ("PlatformCoverageRef", "capability_version"),
        ("CapabilityParameter", "name"),
        ("CompilationFinding", "code"),
    ):
        pattern = schema["$defs"][owner]["properties"][field]["pattern"]
        assert re.fullmatch(pattern, "r001")
        assert not re.fullmatch(pattern, "R001")
        assert not re.fullmatch(pattern, "r" * 101)
        assert not re.fullmatch(pattern, "r/001")


def test_sdk_output_schema_has_one_intake_configuration_and_separate_post_parameters():
    """Actual SDK schema cannot ask the model for two conflicting intake policies."""
    from agents import AgentOutputSchema
    from app.interfaces.project_agents import ProjectGuideCompilationResult

    schema = AgentOutputSchema(ProjectGuideCompilationResult).json_schema()
    intake = schema["$defs"]["SubmissionArtifactPolicyProposal"]
    for field in ("maximum_file_size_bytes", "maximum_package_size_bytes"):
        assert field in intake["required"]
        assert {item["type"] for item in intake["properties"][field]["anyOf"]} == {"integer", "null"}
    pre = schema["$defs"]["PreSubmissionBindingProposal"]
    post = schema["$defs"]["PostSubmissionBindingProposal"]
    assert pre["additionalProperties"] is False
    assert "parameters" in pre["properties"]
    assert pre["properties"]["parameters"]["maxItems"] == 50
    assert post["properties"]["parameters"]["maxItems"] == 50
    assert "parameters" in post["properties"]
    parameter_values = schema["$defs"]["CapabilityParameter"]["properties"]["value"]["anyOf"]
    array = next(item for item in parameter_values if item.get("type") == "array")
    assert array["minItems"] == 1
    assert array["maxItems"] == 50


def test_default_instructions_advertise_contextual_output_constraints():
    """Keep rules the JSON schema cannot express visible to the model."""
    from app.core.project_guide_instructions import PROJECT_GUIDE_INSTRUCTIONS

    instructions = " ".join(PROJECT_GUIDE_INSTRUCTIONS.split())
    for rule in (
        "Only supported_pre_submit and supported_post_submit have binding proposals",
        "platform_coverage must be null unless the disposition is platform_covered",
        "they are not projected or executable while blocked",
        "return exactly one capability_suggestions item with its requirement_id",
        "A fully covered project may have no suggestions",
        "Both pre-submit and post-submit bindings carry parameters",
        "they do not require an automated judge",
        "A guide_blocker requirement requires guide_blocked",
        "Capability gaps alone are not guide deficiencies",
        "can reliably finish within 60 seconds",
        "Automation alone does not make a check POST",
        "Give every atomic requirement a classification_rationale",
        "Recording paths in submission_artifact_policy does not prove",
        "Supply both start_page and end_page together",
        "for a single page use that same number at both ends",
        "Paraphrase section headings using the same safe plain-prose rules",
        "Required and forbidden policy lists must not overlap",
        "maximum file size must not exceed the maximum package size",
        "return null for that policy field",
        "Do not block a guide for omitting intake size limits",
    ):
        assert rule in instructions


async def test_whole_run_deadline_cancels_once_and_closes_without_reinvocation(monkeypatch):
    """The whole-run budget interrupts an outstanding request before its own timeout."""
    from agents import Runner
    from app.adapters.project_agents import openai_agent_sdk

    events = []

    class Workspace:
        container_id = "cntr_deadline_probe"

        def __init__(self, *args):
            pass

        async def start(self):
            events.append("start")

        async def close(self):
            events.append("close")

    async def blocked_run(*args, **kwargs):
        events.append("run")
        try:
            await asyncio.Event().wait()
        finally:
            events.append("cancelled")

    monkeypatch.setattr(openai_agent_sdk, "OpenAIGuideWorkspace", Workspace)
    monkeypatch.setattr(Runner, "run", blocked_run)
    config = runtime_configuration().model_copy(update={"timeout_seconds": 1, "request_timeout_seconds": 300})
    assert config.request_timeout_seconds == 300
    runtime = OpenAIAgentSdkProjectGuideRuntime(config)
    started = asyncio.get_running_loop().time()
    try:
        with pytest.raises(ProjectAgentRuntimeError, match="project guide run timed out") as caught:
            await _compile(runtime, context(ids()).model_copy(update={"runtime_configuration": config}))
        assert 0.8 <= asyncio.get_running_loop().time() - started < 5
        assert events == ["start", "run", "cancelled", "close"]
        assert caught.value.__suppress_context__
    finally:
        await runtime.aclose()


# Manager-authored (provider-free) runtime ---------------------------------

_MANAGER_PAIR = {"runtime_key": "manager_authored", "model_provider": "none",
                 "model_api": "none", "model": "none"}


@pytest.mark.parametrize(
    "patch",
    [
        {"model_provider": "none", "model_api": "none"},
        {"model_provider": "none"},
        {"model_api": "none"},
        _MANAGER_PAIR | {"model_provider": "openai", "model_api": "responses"},
        _MANAGER_PAIR | {"model_api": "responses"},
        _MANAGER_PAIR | {"model": "gpt-5.6-terra"},
        {"model": "none"},
    ],
)
def test_provider_none_is_only_valid_for_the_manager_authored_runtime(patch):
    with pytest.raises(ValidationError, match="guide runtime"):
        ProjectGuideRuntimeConfiguration.model_validate(runtime_configuration().model_dump() | patch)
    with pytest.raises(ValidationError, match="guide runtime"):
        Settings(**{"project_agent_" + ("runtime" if key == "runtime_key" else key): value
                    for key, value in (runtime_configuration().model_dump(
                        include={"runtime_key", "model_provider", "model_api", "model"}) | patch).items()})


def test_manager_authored_settings_snapshot_records_absent_inference():
    settings = Settings(project_agent_runtime="manager_authored", project_agent_model_provider="none",
                        project_agent_model_api="none", project_agent_model="none")
    configuration = project_guide_runtime_configuration(settings)
    assert configuration.model_dump(include=set(_MANAGER_PAIR)) == _MANAGER_PAIR
    assert configuration.provider_free
    assert ProjectGuideRuntimeConfiguration.model_validate(configuration.model_dump()) == configuration
    default = project_guide_runtime_configuration(Settings())
    assert (default.runtime_key, default.model_provider, default.model_api) == (
        "openai_agents_sdk", "openai", "responses")
    assert not default.provider_free


def _manager_material(rules: bytes, *, extra: tuple[bytes, ...] = (), source_ids=()):
    """Return a context with one PDF original, the rules document and optional Markdown."""
    from tests.projects.guide_compilation.helpers import (
        SOURCE_BYTES, manager_runtime_configuration,
    )

    base = context(ids(), configuration=manager_runtime_configuration())
    pdf = base.material.documents[0]
    bodies = {pdf.sha256: SOURCE_BYTES}
    documents = [pdf]
    chosen = iter(source_ids)
    for order, body in enumerate((rules, *extra), start=1):
        digest = "sha256:" + hashlib.sha256(body).hexdigest()
        bodies[digest] = body
        documents.append(pdf.model_copy(update={
            "source_item_id": next(chosen, None) or uuid4(), "ingest_id": uuid4(),
            "item_order": order, "put_attempt_id": uuid4(), "sha256": digest,
            "byte_count": len(body), "media_type": "text/markdown",
        }))
    material = GuideDocumentManifest.model_validate(
        base.material.model_copy(update={"documents": tuple(documents)}).model_dump())
    return base.model_copy(update={"material": material}), bodies


class _DirectGrant:
    """Scripted ART grant and custody recording each direct read once."""

    def __init__(self, compilation_context, bodies, *, fail=False):
        from contextlib import asynccontextmanager
        from io import BytesIO
        from app.modules.projects.api.guide_documents import OpenGuideDocument

        manifest = compilation_context.material
        self.opened, self.recorded = [], []

        @asynccontextmanager
        async def open_document(handle):
            if fail:
                raise RuntimeError("private storage detail")
            self.opened.append(handle)
            document = next(item for item in manifest.documents if manifest.handle_for(item) == handle)
            with BytesIO(bodies[document.sha256]) as reader:
                yield OpenGuideDocument(document, reader)

        async def record_direct_document_open(handle):
            self.recorded.append(handle)

        async def forbidden(*args, **kwargs):
            pytest.fail("provider-free runtime touched provider resource custody")

        self.capabilities = SimpleNamespace(
            documents=SimpleNamespace(open=open_document),
            resources=SimpleNamespace(record_direct_document_open=record_direct_document_open,
                                      begin_allocation=forbidden, record_allocated=forbidden,
                                      record_document_open=forbidden),
        )


def _rules(**overrides) -> bytes:
    body = {
        "format": "workstream.project_guide_rules.v1",
        "status": "draft_ready",
        "findings": [{"severity": "info", "code": "guide.ready", "message": "Guide is complete.",
                      "evidence_refs": [{"document": SOURCE_SHA256, "start_page": 1, "end_page": 2}]}],
        "submission_artifact_policy": {"maximum_file_size_bytes": 1000,
                                       "maximum_package_size_bytes": 10000,
                                       "required_artifacts": ["submission"]},
        "requirements": [{
            "requirement_id": "guide.context", "statement": "Use the project guide.",
            "disposition": "informational", "platform_coverage": None,
            "classification_rationale": "This identifies the governing guide for the work.",
            "check_specification": None,
            # The rules document itself supplies this background requirement.
            # PDF coverage remains owned by findings, including negative cases.
            "evidence_refs": [],
        }], "pre_submit_bindings": [], "post_submit_bindings": [],
        "capability_suggestions": [], "setup_notes": [],
    } | overrides
    return json.dumps(body).encode()


async def _manager_compile(compilation_context, grant):
    from app.adapters.project_agents import create_project_guide_runtime

    runtime = create_project_guide_runtime(compilation_context.runtime_configuration)
    runtime.admit_execution()
    try:
        return await runtime.compile_project_guide(compilation_context, grant.capabilities)
    finally:
        await runtime.aclose()


async def test_manager_authored_runtime_converts_rules_without_credentials_or_network(monkeypatch):
    import socket
    from app.adapters.project_agents.manager_authored import ManagerAuthoredProjectGuideRuntime

    monkeypatch.delenv("OPENAI_API_KEY")

    def no_network(*args, **kwargs):
        pytest.fail("manager-authored runtime opened a network connection")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    notes_id = uuid4()
    rules = _rules(findings=[
        {"severity": "info", "code": "guide.ready", "message": "Guide is complete.",
         "evidence_refs": [{"document": SOURCE_SHA256, "start_page": 1, "end_page": 2}]},
        {"severity": "info", "code": "guide.notes", "message": "Reviewer notes are present.",
         "evidence_refs": [{"document": f"{notes_id}.md", "section": "Reviewer notes"}]},
    ])
    compilation_context, bodies = _manager_material(
        rules, extra=(b"# Reviewer notes\n\nPlain guide prose.",), source_ids=(None, notes_id))
    material = compilation_context.material
    pdf, rules_doc, notes = material.documents
    grant = _DirectGrant(compilation_context, bodies)
    from app.adapters.project_agents import create_project_guide_runtime

    runtime = create_project_guide_runtime(compilation_context.runtime_configuration)
    assert isinstance(runtime, ManagerAuthoredProjectGuideRuntime)
    assert runtime.identity == compilation_context.runtime_configuration.adapter_identity
    outcome = await _manager_compile(compilation_context, grant)

    handles = [material.handle_for(item) for item in material.documents]
    assert grant.opened == grant.recorded == handles
    assert outcome.status == "draft_ready"
    assert (outcome.agent_name, outcome.agent_version, outcome.schema_version) == (
        "ProjectGuideCompilationAgent", compilation_context.agent_version,
        "project_guide_compilation_result.v1")
    first, second = outcome.findings
    assert [(ref.source_item_id, ref.document_version_id, ref.sha256, ref.start_page)
            for ref in first.evidence_refs] == [
        (pdf.source_item_id, pdf.ingest_id, pdf.sha256, 1),
        (rules_doc.source_item_id, rules_doc.ingest_id, rules_doc.sha256, None)]
    assert [(ref.source_item_id, ref.section) for ref in second.evidence_refs] == [
        (notes.source_item_id, "Reviewer notes"), (rules_doc.source_item_id, None)]


@pytest.mark.parametrize(
    ("rules", "extra", "failure"),
    [
        (b"# Ordinary guide text without rules", (), "schema_invalid"),
        (b'{"format": "workstream.project_guide_rules.v1", "status": ', (), "schema_invalid"),
        (_rules(status="draft_ready", findings=[]), (), "schema_invalid"),
        (_rules(), (_rules(setup_notes=["Second rules document."]),), "schema_invalid"),
        (_rules(agent_version="v9"), (), "schema_invalid"),
        (_rules(findings=[{"severity": "info", "code": "guide.ready", "message": "Complete.",
                           "evidence_refs": [{"document": "sha256:" + "0" * 64}]}]), (), "schema_invalid"),
        (_rules(findings=[{"severity": "info", "code": "guide.ready", "message": "Complete.",
                           "evidence_refs": [{"document": "missing.pdf"}]}]), (), "schema_invalid"),
        (_rules(findings=[{"severity": "info", "code": "guide.ready", "message": "Complete.",
                           "evidence_refs": [{"source_item_id": str(uuid4())}]}]), (), "schema_invalid"),
        (_rules(findings=[{"severity": "info", "code": "guide.ready",
                           "message": "Run curl against the endpoint."}]), (), "unsafe_text"),
        (_rules(findings=[{"severity": "info", "code": "guide.ready", "message": "Complete."}]),
         (), "schema_invalid"),
    ],
    ids=["missing", "malformed_json", "no_citations", "two_rules_documents", "extra_field",
         "unknown_sha256", "unknown_filename", "foreign_reference_shape", "unsafe_text",
         "ready_without_every_document"],
)
async def test_manager_authored_runtime_rejects_invalid_rules_as_terminal_output(
        monkeypatch, rules, extra, failure):
    monkeypatch.delenv("OPENAI_API_KEY")
    compilation_context, bodies = _manager_material(rules, extra=extra)
    grant = _DirectGrant(compilation_context, bodies)
    with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
        await _manager_compile(compilation_context, grant)
    assert caught.value.failure_code == failure
    assert caught.value.__suppress_context__
    material = compilation_context.material
    assert grant.recorded == [material.handle_for(item) for item in material.documents]


async def test_manager_authored_runtime_guards_admission_configuration_and_access(monkeypatch):
    from app.adapters.project_agents.manager_authored import ManagerAuthoredProjectGuideRuntime

    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(ProjectAgentRuntimeConfigurationError, match="unsupported"):
        ManagerAuthoredProjectGuideRuntime(runtime_configuration())
    compilation_context, bodies = _manager_material(_rules())
    runtime = ManagerAuthoredProjectGuideRuntime(compilation_context.runtime_configuration)
    grant = _DirectGrant(compilation_context, bodies)
    with pytest.raises(ProjectAgentRuntimeError, match="was not admitted"):
        await runtime.compile_project_guide(compilation_context, grant.capabilities)
    runtime.admit_execution()
    with pytest.raises(ProjectAgentRuntimeError, match="already acquired"):
        runtime.admit_execution()
    with pytest.raises(ProjectAgentRuntimeConfigurationError, match="configuration mismatch"):
        await runtime.compile_project_guide(context(ids()), grant.capabilities)
    failing = _DirectGrant(compilation_context, bodies, fail=True)
    with pytest.raises(ProjectAgentRuntimeError, match="document access failed") as caught:
        await runtime.compile_project_guide(compilation_context, failing.capabilities)
    assert caught.value.__suppress_context__ and "private" not in str(caught.value)
    assert failing.recorded == []

    class Custody:
        def __init__(self, rows):
            self.rows = rows

        async def cleanup_resources(self):
            return self.rows

    assert await runtime.cleanup_resources(Custody(())) is True
    assert await runtime.cleanup_resources(Custody(("unexpected",))) is False


async def test_manager_authored_runtime_refuses_correction_successors_before_reading(monkeypatch):
    """A correction reason cannot change authored rules, so it is never silently ignored."""
    from app.interfaces.project_agents import ProjectGuideCorrectionFeedback

    monkeypatch.delenv("OPENAI_API_KEY")
    compilation_context, bodies = _manager_material(_rules())
    corrected = compilation_context.model_copy(update={
        "correction_feedback": ProjectGuideCorrectionFeedback(
            operation_id=uuid4(), predecessor_compilation_id=uuid4(),
            predecessor_result_hash="sha256:" + "1" * 64, target_digest="sha256:" + "2" * 64,
            reason="Require a test report.")})
    grant = _DirectGrant(corrected, bodies)
    with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
        await _manager_compile(corrected, grant)
    assert caught.value.failure_code == "schema_invalid"
    assert grant.opened == grant.recorded == []


async def test_manager_authored_runtime_retains_only_the_first_parsed_rules_document(monkeypatch):
    """Later rules documents already invalidate the guide, so their bodies are not kept."""
    from app.adapters.project_agents.manager_authored import _read_rules_documents

    monkeypatch.delenv("OPENAI_API_KEY")
    compilation_context, bodies = _manager_material(
        _rules(), extra=(_rules(setup_notes=["Second."]), _rules(setup_notes=["Third."])))
    grant = _DirectGrant(compilation_context, bodies)
    candidates = await _read_rules_documents(compilation_context, grant.capabilities)
    assert [document for document, _ in candidates] == list(compilation_context.material.documents[1:])
    assert isinstance(candidates[0][1], dict)
    assert [parsed for _, parsed in candidates[1:]] == [None, None]
    material = compilation_context.material
    assert grant.recorded == [material.handle_for(item) for item in material.documents]


async def test_manager_authored_runtime_rejects_rules_the_citation_rule_would_not_catch(monkeypatch):
    """Exactly-one and resolvable-reference rules fail on their own, not via coverage."""
    monkeypatch.delenv("OPENAI_API_KEY")
    valid_ref = {"document": SOURCE_SHA256}
    first_id, second_id = uuid4(), uuid4()
    # Each rules document cites the other, so whichever one a regression chose,
    # every document would be cited and only the exactly-one rule can reject.
    duplicated, bodies = _manager_material(
        _rules(findings=[{"severity": "info", "code": "guide.ready", "message": "Complete.",
                          "evidence_refs": [valid_ref, {"document": f"{second_id}.md"}]}]),
        extra=(_rules(findings=[{"severity": "info", "code": "guide.ready", "message": "Complete.",
                                 "evidence_refs": [valid_ref, {"document": f"{first_id}.md"}]}]),),
        source_ids=(first_id, second_id))
    unresolved, unresolved_bodies = _manager_material(_rules(findings=[
        {"severity": "info", "code": "guide.ready", "message": "Complete.",
         "evidence_refs": [valid_ref, {"document": "sha256:" + "0" * 64}]}]))
    for compilation_context, documents in ((duplicated, bodies), (unresolved, unresolved_bodies)):
        with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
            await _manager_compile(compilation_context, _DirectGrant(compilation_context, documents))
        assert caught.value.failure_code == "schema_invalid"


async def test_manager_authored_runtime_ignores_non_candidates_and_survives_deep_nesting(monkeypatch):
    from app.adapters.project_agents.manager_authored import MAXIMUM_RULES_DOCUMENT_BYTES

    monkeypatch.delenv("OPENAI_API_KEY")
    nested = b'{"format": "workstream.project_guide_rules.v1", "x": ' + b"[" * 200_000 + b"]" * 200_000 + b"}"
    oversized = _rules(setup_notes=["Padding."]).replace(
        b'"setup_notes"', b'"pad": "' + b" " * MAXIMUM_RULES_DOCUMENT_BYTES + b'", "setup_notes"')
    for body in (nested, oversized):
        compilation_context, bodies = _manager_material(body)
        grant = _DirectGrant(compilation_context, bodies)
        with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
            await _manager_compile(compilation_context, grant)
        assert caught.value.failure_code == "schema_invalid"
        assert len(grant.recorded) == 2
    # Rules JSON stored under a non-Markdown media type is read but never treated as rules.
    compilation_context, bodies = _manager_material(_rules())
    pdf, rules_doc = compilation_context.material.documents
    relabeled = compilation_context.material.model_copy(update={"documents": (
        pdf, rules_doc.model_copy(update={"media_type": "application/pdf"}))})
    compilation_context = compilation_context.model_copy(update={"material": relabeled})
    with pytest.raises(ProjectGuideCompilationInvalidOutputError) as caught:
        await _manager_compile(compilation_context, _DirectGrant(compilation_context, bodies))
    assert caught.value.failure_code == "schema_invalid"


async def test_manager_authored_runtime_refuses_a_substituted_document_version(monkeypatch):
    from contextlib import asynccontextmanager
    from io import BytesIO
    from app.modules.projects.api.guide_documents import OpenGuideDocument

    monkeypatch.delenv("OPENAI_API_KEY")
    compilation_context, bodies = _manager_material(_rules())
    grant = _DirectGrant(compilation_context, bodies)

    @asynccontextmanager
    async def substituted(handle):
        document = compilation_context.material.documents[0]
        with BytesIO(bodies[document.sha256]) as reader:
            yield OpenGuideDocument(document.model_copy(update={"ingest_id": uuid4()}), reader)

    grant.capabilities.documents.open = substituted
    with pytest.raises(ProjectAgentRuntimeError, match="document access failed"):
        await _manager_compile(compilation_context, grant)
    assert grant.recorded == []
