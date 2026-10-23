"""Frozen, mutually exclusive project-agent SDK installation selections."""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import tomllib


BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PIN = re.compile(r"^([A-Za-z0-9._-]+)==([^ ;]+)")


def _exported_versions(extra: str | None, *, python: str = "3.12") -> dict[str, str]:
    uv = shutil.which("uv")
    assert uv is not None, "the frozen dependency proof requires uv"
    command = [
        uv,
        "export",
        "--frozen",
        "--offline",
        "--no-python-downloads",
        "--python",
        python,
        "--no-dev",
        "--no-hashes",
        "--no-header",
        "--no-annotate",
        "--no-emit-project",
    ]
    if extra is not None:
        command.extend(("--extra", extra))
    completed = subprocess.run(
        command,
        cwd=BACKEND_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    versions: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        match = _PIN.match(line)
        if match is not None:
            versions[match.group(1).lower().replace("_", "-")] = match.group(2)
    return versions


def test_project_agent_sdk_extras_keep_exact_isolated_resolutions() -> None:
    agents = _exported_versions("agents")
    assert agents["openai-agents"] == "0.24.0"
    assert agents["openai"] == "3.37.0"
    assert "omnicoreagent" not in agents
    assert "litellm" not in agents

    omnicore = _exported_versions("omnicore")
    assert omnicore["omnicoreagent"] == "0.6.0"
    assert omnicore["litellm"] == "1.106.2"
    assert omnicore["openai"] == "2.54.0"
    assert omnicore["boto3"] == "1.43.3"
    assert "openai-agents" not in omnicore

    for selection in (agents, omnicore):
        assert selection["pydantic"] == "2.13.5"
        assert selection["aiobotocore"] == "3.8.0"
        assert selection["botocore"] == "1.43.3"


def test_base_python_311_selection_excludes_both_agent_sdk_environments() -> None:
    base = _exported_versions(None, python="3.11")
    assert "openai-agents" not in base
    assert "omnicoreagent" not in base
    assert "litellm" not in base


def test_project_agent_sdk_extras_fail_closed_when_co_selected() -> None:
    uv = shutil.which("uv")
    assert uv is not None, "the frozen dependency proof requires uv"
    completed = subprocess.run(
        [
            uv,
            "export",
            "--frozen",
            "--offline",
            "--no-python-downloads",
            "--python",
            "3.12",
            "--no-dev",
            "--extra",
            "agents",
            "--extra",
            "omnicore",
            "--no-hashes",
            "--no-emit-project",
        ],
        cwd=BACKEND_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "incompatible with the declared conflicts" in completed.stderr


def test_omnicore_selection_retains_base_python_support_and_requires_python_312() -> None:
    with (BACKEND_ROOT / "pyproject.toml").open("rb") as source:
        project = tomllib.load(source)
    assert project["project"]["requires-python"] == ">=3.11,<3.13"
    assert project["project"]["optional-dependencies"]["omnicore"] == [
        "omnicoreagent==0.6.0; python_version >= '3.12'",
        "litellm==1.106.2; python_version >= '3.12'",
        "openai==2.54.0; python_version >= '3.12'",
    ]
    assert project["tool"]["uv"]["conflicts"] == [[{"extra": "agents"}, {"extra": "omnicore"}]]


def test_shared_worker_dependency_supports_no_prefetch_control() -> None:
    """Every SDK image must install a Celery release with no-prefetch support."""
    with (BACKEND_ROOT / "pyproject.toml").open("rb") as source:
        project = tomllib.load(source)
    assert "celery[redis]>=5.6,<6.0" in project["project"]["dependencies"]
