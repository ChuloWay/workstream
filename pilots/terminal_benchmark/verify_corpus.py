"""Verify only reviewed repository corpus assets; this is not an upload sandbox."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parent
BASE = "python:3.12-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2"
FILES = (
    "task.toml", "instruction.md", "environment/Dockerfile", ".dockerignore",
    "workspace/program.py", "solution/program.py", "tests/test_task.py", "tests/cases.json",
)


def validate_package(package: Path, external_task_id: str) -> None:
    """Check this corpus's fixed mechanical package contract before executing it."""
    for name in FILES:
        path = package / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"missing or linked package member: {name}")
    metadata = tomllib.loads((package / "task.toml").read_text())
    expected = {
        "external_task_id": external_task_id,
        "entrypoint": ["python", "/workspace/program.py", "INPUT.json", "OUTPUT.json"],
        "test_command": ["python", "/tests/test_task.py", "/workspace/program.py"],
        "build_context": ".", "dockerfile": "environment/Dockerfile",
        "reference_program": "solution/program.py",
    }
    if metadata != expected:
        raise ValueError("package metadata does not match the fixed corpus contract")
    dockerfile = (package / "environment/Dockerfile").read_text().splitlines()
    if dockerfile != [
        f"FROM {BASE}", "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1",
        "WORKDIR /workspace", "COPY --chown=65532:65532 workspace/ /workspace/",
        "USER 65532:65532",
    ]:
        raise ValueError("package Dockerfile differs from the reviewed offline recipe")
    if (package / ".dockerignore").read_text().splitlines() != ["solution/", "tests/"]:
        raise ValueError("reference or tests are not excluded from the build context")
    if not (package / "instruction.md").read_text().strip():
        raise ValueError("empty instructions")
    cases = json.loads((package / "tests/cases.json").read_text())
    if not cases or len({case["name"] for case in cases}) != len(cases):
        raise ValueError("missing or duplicate golden cases")


def run_cases(package: Path, program_text: str, *, ineffective_tests: bool = False, case_name: str | None = None) -> bool:
    """Calibrate trusted assets in an isolated copy without copying solution/ there."""
    with tempfile.TemporaryDirectory(prefix="workstream-corpus-") as directory:
        root = Path(directory)
        workspace = root / "workspace"
        workspace.mkdir()
        shutil.copytree(package / "tests", root / "tests")
        if case_name is not None:
            cases_path = root / "tests/cases.json"
            selected = [case for case in json.loads(cases_path.read_text()) if case["name"] == case_name]
            if len(selected) != 1:
                raise ValueError("named discriminating case is absent or duplicated")
            cases_path.write_text(json.dumps(selected))
        program = workspace / "program.py"
        program.write_text(program_text)
        if ineffective_tests:
            (root / "tests/test_task.py").write_text('print("passed")\n')
        result = subprocess.run(
            [sys.executable, str(root / "tests/test_task.py"), str(program)],
            cwd=root, capture_output=True, text=True, timeout=45, check=False,
        )
        if result.returncode not in (0, 1):
            raise RuntimeError("corpus test process failed outside an assertion boundary")
        if result.returncode == 1 and "AssertionError:" not in result.stderr:
            raise RuntimeError("corpus test harness crashed: " + result.stderr[-1500:])
        return result.returncode == 0


def require_starter_failure(package: Path, starter: str, *, ineffective_tests: bool = False) -> None:
    if run_cases(package, starter, ineffective_tests=ineffective_tests):
        raise AssertionError("unchanged starter unexpectedly passed")


def verify() -> dict:
    corpus = json.loads((ROOT / "corpus.json").read_text())
    actual_names = sorted(str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and p.suffix != ".pyc" and p.name != "corpus.json")
    if actual_names != sorted(corpus["sha256"]):
        raise ValueError("corpus file membership differs from its reviewed manifest")
    for name, expected in corpus["sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"corpus hash changed: {name}")
    tasks = json.loads((ROOT / "tasks.json").read_text())["tasks"]
    if [t["external_task_id"] for t in tasks] != [p["external_task_id"] for p in corpus["packages"]]:
        raise ValueError("native task import and package membership disagree")
    negatives = json.loads((ROOT / "negative-cases.json").read_text())["near_miss_solutions"]
    if [(n["external_task_id"], n["package"]) for n in negatives] != [(p["external_task_id"], p["path"]) for p in corpus["packages"]]:
        raise ValueError("near-miss membership differs from corpus")
    evidence = []
    for item, negative in zip(corpus["packages"], negatives, strict=True):
        package = ROOT / item["path"]
        validate_package(package, item["external_task_id"])
        starter = (package / "workspace/program.py").read_text()
        reference = (package / "solution/program.py").read_text()
        require_starter_failure(package, starter)
        for _ in range(3):
            if not run_cases(package, reference):
                raise AssertionError(f"reference failed: {item['path']}")
        mutation = negative["near_miss"]
        if reference.count(mutation["replace"]) != 1:
            raise AssertionError("near-miss mutation must match exactly once")
        changed = reference.replace(mutation["replace"], mutation["with"])
        if not run_cases(package, reference, case_name=mutation["caught_by"]):
            raise AssertionError("named discriminating case rejected the valid control")
        if run_cases(package, changed, case_name=mutation["caught_by"]):
            raise AssertionError("plausible wrong solution was not rejected")
        try:
            require_starter_failure(package, starter, ineffective_tests=True)
        except AssertionError as exc:
            if str(exc) != "unchanged starter unexpectedly passed":
                raise
        else:
            raise AssertionError("ineffective tests escaped calibration rejection")
        # Package invalidity must fail at validation, not at incidental Python execution.
        for mutation_name in ("missing-tests", "wrong-task-identity", "unpinned-base"):
            with tempfile.TemporaryDirectory(prefix="workstream-invalid-package-") as directory:
                altered = Path(directory) / "package"
                shutil.copytree(package, altered)
                if mutation_name == "missing-tests":
                    (altered / "tests/test_task.py").unlink()
                elif mutation_name == "wrong-task-identity":
                    path = altered / "task.toml"
                    path.write_text(path.read_text().replace(item["external_task_id"], "foreign-task"))
                else:
                    (altered / "environment/Dockerfile").write_text("FROM python:latest\n")
                try:
                    validate_package(altered, item["external_task_id"])
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"invalid package survived: {mutation_name}")
        evidence.append({"external_task_id": item["external_task_id"], "reference_passes": 3, "starter_rejected": True, "near_miss_rejected": True})
    return {"proof": "trusted_native_corpus_only", "packages": evidence, "docker_gvisor_hosted_proof": "pending"}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
