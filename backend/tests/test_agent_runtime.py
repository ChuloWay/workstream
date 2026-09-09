"""One replaceable runtime, exact configuration custody, and untrusted output tests."""

from __future__ import annotations

import asyncio
import hashlib
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.adapters.project_agents.openai_agent_sdk import (
    OpenAIAgentSdkProjectGuideRuntime,
    _invalid_compilation_failure_code,
)
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
    project_guide_compilation_prompt_bytes,
)
from app.interfaces.project_guide_runtime import ProjectGuideRuntimeConfiguration
from tests.projects.guide_compilation.helpers import context, ids, result, runtime_configuration


@pytest.fixture(autouse=True)
def model_credentials(monkeypatch):
    """Use a test-only credential; SDK execution is replaced in every invocation test."""
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-only")


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
        {"api_key": "not-allowed"},
        {"timeout_seconds": True},
        {"timeout_seconds": 0},
        {"maximum_prompt_bytes": 16 * 1024 * 1024 + 1},
        {"model": ""},
        {"model_provider": "uninstalled"},
        {"model_provider": "openai_compatible", "model_endpoint": None},
        {"model_endpoint": "https://example.test"},
        {"model_provider": "openai_compatible", "model_endpoint": "http://example.test"},
        {
            "model_provider": "openai_compatible",
            "model_endpoint": "https://user:secret@example.test",
        },
        {
            "model_provider": "openai_compatible",
            "model_endpoint": "https://example.test?key=secret",
        },
        {"model_provider": "openai_compatible", "model_endpoint": "https://example.test#secret"},
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
    assert isinstance(prompt["material"]["canonical_payload"], dict)


@pytest.mark.parametrize("api", ["responses", "chat_completions"])
@pytest.mark.parametrize("provider", ["openai", "openai_compatible"])
async def test_unified_compilation_is_one_strict_tool_free_validated_call(
    monkeypatch, api, provider
):
    from agents import Runner
    import openai

    clients = []
    client_type = openai.AsyncOpenAI

    def create_client(**kwargs):
        client = client_type(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(openai, "AsyncOpenAI", create_client)

    configuration = runtime_configuration().model_copy(
        update={
            "model_api": api,
            "model_provider": provider,
            "model_endpoint": "https://models.example.test/v1"
            if provider == "openai_compatible"
            else None,
        }
    )
    compilation_context = context(ids()).model_copy(update={"runtime_configuration": configuration})
    calls = []

    async def run(agent, prompt, **kwargs):
        calls.append((agent, prompt, kwargs))
        assert agent.instructions == configuration.instructions
        assert agent.tools == [] and agent.handoffs == []
        assert agent.model.model == configuration.model
        assert agent.output_type.is_strict_json_schema() is True
        assert kwargs["max_turns"] == 1
        assert kwargs["run_config"].tracing_disabled is True
        assert kwargs["run_config"].trace_include_sensitive_data is False
        assert "runtime_configuration" not in json.loads(prompt)
        return SimpleNamespace(final_output=result())

    monkeypatch.setattr(Runner, "run", run)
    output = await OpenAIAgentSdkProjectGuideRuntime(configuration).compile_project_guide(
        compilation_context
    )
    assert output == result()
    assert len(calls) == 1
    assert len(clients) == 1
    assert clients[0].max_retries == 0
    assert clients[0].is_closed()
    assert str(clients[0].base_url).rstrip("/") == (
        configuration.model_endpoint or "https://api.openai.com/v1"
    )


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
    assert await runtime.compile_project_guide(context(ids())) == output


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
        await runtime.compile_project_guide(context(ids()))


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
        await runtime.compile_project_guide(context(ids()))


async def test_oversized_prompt_is_rejected_before_sdk_execution(monkeypatch):
    configuration = runtime_configuration().model_copy(update={"maximum_prompt_bytes": 1024})
    runtime = OpenAIAgentSdkProjectGuideRuntime(configuration)

    async def forbidden(*args):
        pytest.fail("oversized prompt reached provider")

    monkeypatch.setattr(runtime, "_run", forbidden)
    with pytest.raises(ProjectAgentRuntimeError, match="size limit"):
        await runtime.compile_project_guide(
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
        await runtime.compile_project_guide(changed)


@pytest.mark.parametrize(
    "error", [RuntimeError("private provider detail"), TimeoutError("private timeout")]
)
async def test_runtime_failure_is_sanitized(monkeypatch, error):
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())

    async def run(*args):
        raise error

    monkeypatch.setattr(runtime, "_run", run)
    with pytest.raises(ProjectAgentRuntimeError) as caught:
        await runtime.compile_project_guide(context(ids()))
    assert "private" not in str(caught.value)
    assert caught.value.__suppress_context__


async def test_unified_compilation_propagates_caller_cancellation(monkeypatch):
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())
    started = asyncio.Event()

    async def run(*args):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(runtime, "_run", run)
    task = asyncio.create_task(runtime.compile_project_guide(context(ids())))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_invalid_compilation_classifier_separates_unsafe_text_from_schema_errors():
    assert (
        _invalid_compilation_failure_code(ValueError("model-produced text is unsafe"))
        == "unsafe_text"
    )
    assert _invalid_compilation_failure_code(TypeError("unknown")) == "schema_invalid"


async def test_runtime_internal_cancellation_is_sanitized(monkeypatch):
    runtime = OpenAIAgentSdkProjectGuideRuntime(runtime_configuration())

    async def run(*args):
        raise asyncio.CancelledError("private provider cancellation")

    monkeypatch.setattr(runtime, "_run", run)
    with pytest.raises(ProjectAgentRuntimeError, match="project guide run cancelled") as caught:
        await runtime.compile_project_guide(context(ids()))
    assert "private" not in str(caught.value)
    assert caught.value.__suppress_context__
