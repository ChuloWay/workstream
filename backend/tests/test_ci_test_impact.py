"""Behavioral counterexamples for conservative CI dependency selection."""

from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from scripts.ci_test_impact import ImpactUncertain, affected_modules, dependency_graph
from scripts import ci_selection_receipt, select_ci_scope


def _tree(root: Path, sources: dict[str, str]) -> Path:
    for relative, source in sources.items():
        path = root / "backend" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return root


def test_removed_import_and_package_initializer_keep_transitive_consumers(tmp_path: Path) -> None:
    sources = {
        "app/modules/projects/leaf.py": "value = 1\n",
        "app/modules/projects/__init__.py": "from . import leaf\n",
        "app/modules/tasks/consumer.py": "from app.modules import projects\n",
        "tests/projects/test_owner.py": "def test_owner(): pass\n",
        "tests/tasks/test_consumer.py": "from app.modules.tasks import consumer\n",
        "tests/reviews/test_unrelated.py": "def test_unrelated(): pass\n",
    }
    base = dependency_graph(_tree(tmp_path / "base", sources))
    sources["app/modules/projects/__init__.py"] = ""
    head = dependency_graph(_tree(tmp_path / "head", sources))
    executable = tuple(path for path in sources if path.startswith("tests/"))
    selected = affected_modules(
        base, head, ("backend/app/modules/projects/leaf.py",), executable,
    )
    assert selected == ("tests/projects/test_owner.py", "tests/tasks/test_consumer.py")


def test_uncertain_support_source_readers_and_plugin_consumers_are_retained(tmp_path: Path) -> None:
    sources = {
        "app/modules/projects/leaf.py": "value = 1\n",
        "tests/projects/test_owner.py": "def test_owner(): pass\n",
        "tests/reviews/plugin.py": "from app.modules.projects import leaf\n",
        "tests/reviews/conftest.py": 'pytest_plugins = ("plugin",)\n',
        "tests/reviews/test_plugin_user.py": "def test_plugin_user(): pass\n",
        "tests/support.py": "def inspect_it(value): return vars(value)\n",
        "tests/tasks/test_dynamic_user.py": "from tests.support import inspect_it\n",
        "tests/test_source_reader.py": 'from pathlib import Path\nsource = Path("x").read_text()\n',
        "tests/test_unrelated.py": "def test_unrelated(): pass\n",
    }
    graph = dependency_graph(_tree(tmp_path, sources))
    executable = tuple(path for path in sources if Path(path).name.startswith("test_"))
    selected = affected_modules(
        graph, graph, ("backend/app/modules/projects/leaf.py",), executable,
    )
    assert set(selected) == set(executable) - {"tests/test_unrelated.py"}


def test_production_dynamic_loading_requires_full_fallback(tmp_path: Path) -> None:
    _tree(tmp_path, {"app/modules/projects/leaf.py": "import importlib\n"})
    with pytest.raises(ImpactUncertain, match="dynamic_production_dependency"):
        dependency_graph(tmp_path)


@pytest.mark.parametrize("reader", [
    'from pathlib import Path\ndef read(): return Path("backend/app/modules/tasks/leaf.py").read_text()\n',
    'REGISTRY = {"reader": "app.modules.tasks.leaf:read"}\n',
    'from pathlib import Path\nread = Path.read_text\ndef consume(path): return read(path)\n',
    'read = open\ndef consume(path): return read(path).read()\n',
])
@pytest.mark.parametrize("reader_tree", ["base", "head", "both"])
def test_cross_owner_non_import_consumers_force_full_fallback(
    tmp_path: Path, reader: str, reader_tree: str,
) -> None:
    sources = {
        "app/modules/tasks/leaf.py": "value = 1\n",
        "app/modules/projects/reader.py": "value = 1\n",
        "tests/tasks/test_leaf.py": "from app.modules.tasks import leaf\n",
        "tests/projects/test_reader.py": "from app.modules.projects import reader\n",
    }
    base_sources = {**sources, "app/modules/projects/reader.py":
                    reader if reader_tree in {"base", "both"} else "value = 1\n"}
    head_sources = {**sources, "app/modules/projects/reader.py":
                    reader if reader_tree in {"head", "both"} else "value = 1\n"}
    base = dependency_graph(_tree(tmp_path / "base", base_sources))
    head = dependency_graph(_tree(tmp_path / "head", head_sources))
    executable = tuple(path for path in sources if path.startswith("tests/"))
    with pytest.raises(ImpactUncertain, match="production_non_import_dependency"):
        affected_modules(base, head, ("backend/app/modules/tasks/leaf.py",), executable)
    # Unknown readers can consume test source too; do not assume otherwise.
    with pytest.raises(ImpactUncertain, match="production_non_import_dependency"):
        affected_modules(base, head, ("backend/tests/tasks/test_leaf.py",), executable)


@pytest.mark.parametrize("changed", [
    "backend/tests/support.py", "backend/tests/deleted_test.py",
    "backend/app/modules/authorization/operation.py",
    "backend/app/modules/projects/models.py",
])
def test_support_deleted_and_protected_changes_require_full_fallback(tmp_path: Path, changed: str) -> None:
    sources = {
        changed.removeprefix("backend/"): "value = 1\n",
        "tests/projects/test_owner.py": "def test_owner(): pass\n",
    }
    graph = dependency_graph(_tree(tmp_path, sources))
    with pytest.raises(ImpactUncertain):
        affected_modules(graph, graph, (changed,), ("tests/projects/test_owner.py",))


def test_test_only_change_includes_importing_tests_without_owner_wide_expansion(tmp_path: Path) -> None:
    sources = {
        "tests/projects/test_one.py": "value = 1\n",
        "tests/tasks/test_two.py": "from tests.projects.test_one import value\n",
        "tests/projects/test_unrelated.py": "def test_unrelated(): pass\n",
    }
    graph = dependency_graph(_tree(tmp_path, sources))
    selected = affected_modules(
        graph, graph, ("backend/tests/projects/test_one.py",), tuple(sources),
    )
    assert selected == ("tests/projects/test_one.py", "tests/tasks/test_two.py")


def test_git_selection_receipt_binds_event_inventory_and_omissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real base/head diff selects its consumer; receipt tampering cannot pass."""
    root = _tree(tmp_path, {
        "app/modules/projects/leaf.py": "value = 1\n",
        "tests/projects/test_owner.py": "from app.modules.projects.leaf import value\n",
        "tests/tasks/test_consumer.py": "from app.modules.projects.leaf import value\n",
        "tests/reviews/test_unrelated.py": "def test_unrelated(): pass\n",
    })

    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    git("init", "--quiet")
    git("config", "user.name", "Selection Test")
    git("config", "user.email", "selection@example.invalid")
    git("add", ".")
    git("commit", "--quiet", "-m", "base")
    base = git("rev-parse", "HEAD")
    (root / "backend/app/modules/projects/leaf.py").write_text("value = 2\n")
    git("add", ".")
    git("commit", "--quiet", "-m", "leaf change")
    head = git("rev-parse", "HEAD")
    modules = ("tests/projects/test_owner.py", "tests/reviews/test_unrelated.py",
               "tests/tasks/test_consumer.py")
    lanes = (SimpleNamespace(name="project_lifecycle_a", modules=(modules[0], modules[2])),
             SimpleNamespace(name="task_lifecycle_a", modules=(modules[1],)))
    monkeypatch.setattr(ci_selection_receipt, "LANES", lanes)
    monkeypatch.setattr(select_ci_scope, "LANES_BY_TEST_MODULE", {
        module: (lane.name,) for lane in lanes for module in lane.modules
    })
    manifest = {"schema_version": 1, "head_sha": head, "nodes": [
        {"nodeid": module + "::test_behavior", "module": module,
         "execution_kind": "ordinary_isolated",
         "lane": "task_lifecycle_a" if module == modules[1] else "project_lifecycle_a"}
        for module in modules
    ]}
    args = dict(base_sha=base, pr_head_sha=head, tested_sha=head, manifest=manifest)
    receipt = ci_selection_receipt.build_receipt(root, **args)
    assert receipt["selected_modules"] == [modules[0], modules[2]]
    assert receipt["omitted_modules"] == [modules[1]]
    assert receipt["lanes"] == ["project_lifecycle_a"]
    path = root / "selection.json"
    path.write_bytes(ci_selection_receipt.receipt_bytes(receipt))
    assert ci_selection_receipt.verify_receipt(path, root, **args) == receipt
    for key, replacement in (
        ("selected_nodes", receipt["selected_nodes"][:-1]),
        ("omitted_modules", []), ("lanes", ["task_lifecycle_a"]),
        ("input_sha256", "0" * 64), ("pr_head_sha", base),
    ):
        path.write_bytes(ci_selection_receipt.receipt_bytes({**receipt, key: replacement}))
        with pytest.raises(ci_selection_receipt.SelectionError, match="receipt_mismatch"):
            ci_selection_receipt.verify_receipt(path, root, **args)
    path.write_bytes(ci_selection_receipt.receipt_bytes(receipt))
    (root / "backend/tests/reviews/test_unrelated.py").write_text("# changed since selection\n")
    with pytest.raises(ci_selection_receipt.SelectionError, match="receipt_mismatch"):
        ci_selection_receipt.verify_receipt(path, root, **args)


def test_selected_bundle_inventory_rejects_missing_foreign_and_future_attempts(tmp_path: Path) -> None:
    from scripts.merge_test_lane_evidence import select_lane_bundles
    from scripts.run_test_lanes import LaneError

    selection = {"lanes": ["schema_contracts"], "selected_nodes": ["one"]}
    head = "a" * 40
    prefix = f"backend-selected-{ci_selection_receipt.receipt_digest(selection)}-{head}-schema_contracts"
    with pytest.raises(LaneError, match="invalid_lane_bundle_set"):
        select_lane_bundles(tmp_path, head, 2, selection=selection)
    first = tmp_path / (prefix + "-attempt-1")
    first.mkdir()
    second = tmp_path / (prefix + "-attempt-2")
    second.mkdir()
    assert select_lane_bundles(tmp_path, head, 2, selection=selection) == {"schema_contracts": second}
    with pytest.raises(LaneError, match="invalid_lane_bundle_set"):
        select_lane_bundles(tmp_path, head, 1, selection=selection)
    foreign = tmp_path / f"backend-lane-{head}-schema_contracts-attempt-2"
    foreign.mkdir()
    with pytest.raises(LaneError, match="invalid_lane_bundle_set"):
        select_lane_bundles(tmp_path, head, 2, selection=selection)
