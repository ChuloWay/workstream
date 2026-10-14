"""Exercise selected CI end to end using real PostgreSQL/MinIO and a controlled diff."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.test_lane_catalogue import LANES


def _run(root: Path, log: Path, *args: str, expect_success: bool = True) -> int:
    """Run a real process, preserving failure output outside the fixture tree."""
    with log.open("wb") as output:
        result = subprocess.run(args, cwd=root, stdout=output, stderr=subprocess.STDOUT,
                                check=False, timeout=600)
    if (result.returncode == 0) != expect_success:
        raise RuntimeError(f"unexpected_probe_result:{log.name}:{result.returncode}")
    return result.returncode


def _git(root: Path, *args: str) -> str:
    """Operate only in the disposable fixture repository."""
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _fixture(root: Path, source: Path) -> str:
    """Retain the actual CI owners and schema; replace only the fixture workload."""
    backend = root / "backend"
    backend.mkdir()
    for name in ("app", "scripts", "alembic"):
        shutil.copytree(source / name, backend / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("alembic.ini", "pyproject.toml", ".coveragerc"):
        if (source / name).is_file():
            shutil.copyfile(source / name, backend / name)
    (backend / "tests/projects").mkdir(parents=True)
    (backend / "app/modules/projects/ci_selection_probe.py").write_text("VALUE = 1\n")
    owner = "tests/projects/test_selected_probe.py"
    (backend / owner).write_text(
        "from app.modules.projects.ci_selection_probe import VALUE\n"
        "import asyncio\nimport os\nimport asyncpg\n"
        "def test_changed_leaf_and_real_database():\n"
        "    assert VALUE == 2\n"
        "    async def exercise():\n"
        "        url = os.environ['WORKSTREAM_TEST_DATABASE_URL'].replace('postgresql+asyncpg:', 'postgresql:')\n"
        "        connection = await asyncpg.connect(url)\n"
        "        try:\n"
        "            await connection.execute('CREATE TABLE ci_selection_probe (value integer NOT NULL)')\n"
        "            await connection.execute('INSERT INTO ci_selection_probe VALUES (2)')\n"
        "            assert await connection.fetchval('SELECT value FROM ci_selection_probe') == VALUE\n"
        "        finally:\n"
        "            await connection.close()\n"
        "    asyncio.run(exercise())\n"
    )
    catalogue = (
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True)\nclass TestLane:\n"
        "    name: str\n    modules: tuple[str, ...]\n    requires_postgres: bool = True\n"
        "ADMIN_RUNNER_MODULE = 'tests/test_isolated_database_runner.py'\n"
        "PARTITION_LANES_BY_MODULE = {}\nLANES = (\n"
    )
    for index, lane in enumerate(LANES):
        module = owner if lane.name == "project_lifecycle_a" else f"tests/test_unrelated_{index}.py"
        if module != owner:
            (backend / module).write_text("def test_unrelated():\n    assert 2 + 2 == 4\n")
        modules = (module,)
        if lane.name == "schema_contracts":
            admin = "tests/test_isolated_database_runner.py"
            (backend / admin).write_text("def test_admin_workload_marker():\n    assert True\n")
            modules += (admin,)
        catalogue += f"    TestLane({lane.name!r}, {modules!r}),\n"
    (backend / "scripts/test_lane_catalogue.py").write_text(catalogue + ")\n")
    (root / ".gitignore").write_text("__pycache__/\n*.pyc\n.pytest_cache/\n.coverage*\n")
    _git(root, "init", "--quiet")
    _git(root, "config", "user.name", "CI Selection Probe")
    _git(root, "config", "user.email", "ci-selection@example.invalid")
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "controlled base")
    return _git(root, "rev-parse", "HEAD")


def probe(output: Path) -> None:
    """Prove full/selected success and that an affected regression still fails."""
    if not os.environ.get("WORKSTREAM_TEST_ADMIN_DATABASE_URL") or not os.environ.get("WORKSTREAM_TEST_MINIO_ENDPOINT"):
        raise RuntimeError("probe_requires_real_postgres_and_minio")
    output.mkdir(mode=0o700)
    source = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="workstream-ci-selection-probe-") as temporary:
        root = Path(temporary)
        base = _fixture(root, source)
        backend = root / "backend"
        leaf = backend / "app/modules/projects/ci_selection_probe.py"
        leaf.write_text("VALUE = 2\n")
        _git(root, "add", ".")
        _git(root, "commit", "--quiet", "-m", "controlled leaf change")
        head = _git(root, "rev-parse", "HEAD")
        identity = ("--base-sha", base, "--pr-head-sha", head)
        _run(backend, output / "selection.log", sys.executable, "scripts/ci_selection_receipt.py",
             *identity, "--tested-sha", head, "--output-dir", str(output / "plan"),
             "--github-output", str(output / "outputs"))
        receipt_path = output / "plan/selection.json"
        receipt = json.loads(receipt_path.read_bytes())
        if receipt["selected_modules"] != ["tests/projects/test_selected_probe.py"]:
            raise RuntimeError("probe_failed_to_omit_unrelated_work")
        if receipt["lanes"] != ["project_lifecycle_a"] or len(receipt["omitted_modules"]) != 10:
            raise RuntimeError("probe_wrong_execution_inventory")
        # Hosted lanes have separate MinIO containers. This bounded local probe
        # has one provider, so run lanes sequentially to preserve bucket custody.
        for lane in LANES:
            full_bundle = output / "full-bundles" / f"backend-lane-{head}-{lane.name}-attempt-1"
            full_bundle.mkdir(parents=True)
            _run(backend, output / f"full-{lane.name}.log", sys.executable, "scripts/run_test_lanes.py",
                 "--lane", lane.name, "--metadata-dir", str(full_bundle / "metadata"),
                 "--summary-json", str(full_bundle / "summary.json"))
        _run(backend, output / "full-merge.log", sys.executable, "-m", "scripts.merge_test_lane_evidence",
             "--input-root", str(output / "full-bundles"), "--metadata-dir", str(output / "full"),
             "--summary-json", str(output / "full-summary.json"), "--expected-head", head, "--run-attempt", "1")
        _run(backend, output / "full-validation.log", sys.executable, "scripts/validate_test_lane_evidence.py",
             "--metadata-dir", str(output / "full"), "--summary-json", str(output / "full-summary.json"))
        import hashlib
        digest = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        bundle = output / "bundles" / f"backend-selected-{digest}-{head}-project_lifecycle_a-attempt-1"
        bundle.mkdir(parents=True)
        _run(backend, output / "selected.log", sys.executable, "scripts/run_test_lanes.py",
             "--lane", "project_lifecycle_a", "--selection-file", str(receipt_path), *identity,
             "--metadata-dir", str(bundle / "metadata"), "--summary-json", str(bundle / "summary.json"))
        _run(backend, output / "merge.log", sys.executable, "-m", "scripts.merge_test_lane_evidence",
             "--input-root", str(output / "bundles"), "--metadata-dir", str(output / "selected"),
             "--summary-json", str(output / "selected-summary.json"), "--expected-head", head,
             "--run-attempt", "1", "--selection-file", str(receipt_path), *identity)
        _run(backend, output / "selected-validation.log", sys.executable, "scripts/validate_test_lane_evidence.py",
             "--metadata-dir", str(output / "selected"), "--summary-json", str(output / "selected-summary.json"), *identity)
        # Same dependency change, deliberately wrong behavior: both selected
        # execution and the full fixture test invocation must catch the defect.
        leaf.write_text("VALUE = 3\n")
        _git(root, "add", ".")
        _git(root, "commit", "--quiet", "-m", "insert controlled regression")
        bad_head = _git(root, "rev-parse", "HEAD")
        bad_identity = ("--base-sha", base, "--pr-head-sha", bad_head)
        _run(backend, output / "bad-selection.log", sys.executable, "scripts/ci_selection_receipt.py",
             *bad_identity, "--tested-sha", bad_head, "--output-dir", str(output / "bad-plan"),
             "--github-output", str(output / "bad-outputs"))
        _run(backend, output / "bad-selected.log", sys.executable, "scripts/run_test_lanes.py",
             "--lane", "project_lifecycle_a", "--selection-file", str(output / "bad-plan/selection.json"),
             *bad_identity, "--metadata-dir", str(output / "bad-selected"),
             "--summary-json", str(output / "bad-summary.json"), expect_success=False)
        _run(backend, output / "bad-full.log", sys.executable, "-m", "pytest", "-q", "tests", expect_success=False)
        if "assert 3 == 2" not in (output / "bad-full.log").read_text():
            raise RuntimeError("full_probe_failed_for_wrong_reason")
        if "assert 3 == 2" not in (output / "bad-selected/project_lifecycle_a.log").read_text():
            raise RuntimeError("selected_probe_failed_for_wrong_reason")
    print("Full and selected proof passed; both caught the inserted leaf regression. Cleanup verified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    probe(parser.parse_args().output_dir.resolve())
