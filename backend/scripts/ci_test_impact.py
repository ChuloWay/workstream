"""Conservative source and test dependency closure for CI selection."""

from __future__ import annotations

import ast
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
import io
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
from typing import Iterator

from scripts.authorization_boundary import (
    AuthorizationBoundaryError,
    _DynamicImportVisitor,
    _resolve_from,
)


# Explicit product ownership, not filename similarity. Other owners remain full.
OWNER_TEST_ROOTS = {
    "projects": ("tests/projects/",),
    "tasks": ("tests/tasks/",),
    "checkers": ("tests/checkers/",),
    "reviews": ("tests/reviews/",),
}
SOURCE_READ_CALLS = frozenset({
    "open", "read_text", "read_bytes", "glob", "rglob", "getsource",
    "getsourcefile", "getfile", "iterdir", "walk",
})


class ImpactUncertain(ValueError):
    """Dependency evidence cannot justify omitting tests."""


@contextmanager
def immutable_base_tree(root: Path, revision: str) -> Iterator[Path]:
    """Materialize only regular Python sources from one exact Git commit."""
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ImpactUncertain("invalid_base_revision")
    try:
        result = subprocess.run(
            ["git", "archive", "--format=tar", revision, "backend/app", "backend/tests"],
            cwd=root, check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ImpactUncertain("unavailable_base_tree") from exc
    with tempfile.TemporaryDirectory(prefix="workstream-ci-base-") as directory:
        base = Path(directory)
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            for member in archive:
                relative = Path(member.name)
                if relative.suffix != ".py":
                    continue
                if (not member.isfile() or relative.is_absolute() or
                        ".." in relative.parts or relative.parts[:2] not in
                        {("backend", "app"), ("backend", "tests")}):
                    raise ImpactUncertain("unsafe_base_python_source")
                content = archive.extractfile(member)
                if content is None:
                    raise ImpactUncertain("missing_base_python_source")
                destination = base / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content.read())
        yield base


@dataclass(frozen=True)
class DependencyGraph:
    """Repository-local imports plus implicit package and fixture consumers."""

    reverse: dict[str, frozenset[str]]
    paths: frozenset[str]
    uncertain_tests: frozenset[str]
    sentinels: frozenset[str]


def _module(path: str) -> str:
    return path.removesuffix(".py").replace("/", ".").removesuffix(".__init__")


def dependency_graph(root: Path) -> DependencyGraph:
    """Inspect Python without importing application or test code."""
    backend = root / "backend"
    files = {
        path.relative_to(backend).as_posix(): path
        for directory in (backend / "app", backend / "tests")
        for path in directory.rglob("*.py")
    }
    if not files or any(path.is_symlink() for path in files.values()):
        raise ImpactUncertain("missing_or_symlinked_python_inventory")
    modules: dict[str, str] = {}
    for relative in files:
        name = _module(relative)
        if name in modules:
            raise ImpactUncertain("ambiguous_module_inventory")
        modules[name] = relative
    namespaces = {
        ".".join(name.split(".")[:end])
        for name in modules
        for end in range(1, len(name.split(".")))
    }
    bare_support: dict[str, list[str]] = defaultdict(list)
    for name, relative in modules.items():
        if relative.startswith("tests/"):
            parts = name.split(".")
            for start in range(1, len(parts)):
                bare_support[".".join(parts[start:])].append(relative)
    reverse: dict[str, set[str]] = defaultdict(set)
    uncertain: set[str] = set()
    sentinels: set[str] = set()
    for relative, path in files.items():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, SyntaxError) as exc:
            raise ImpactUncertain("unparseable_python") from exc
        try:
            # Reuse the boundary scanner's dynamic-loading guard on the AST
            # already parsed above; reparsing every source doubles planner work.
            _DynamicImportVisitor().visit(tree)
        except AuthorizationBoundaryError as exc:
            if relative.startswith("app/"):
                raise ImpactUncertain("dynamic_production_dependency") from exc
            uncertain.add(relative)
        name = _module(relative)
        targets: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "pytest_plugins"
                for target in node.targets
            ):
                try:
                    plugins = ast.literal_eval(node.value)
                except (ValueError, TypeError) as exc:
                    raise ImpactUncertain("dynamic_pytest_plugins") from exc
                if isinstance(plugins, str):
                    plugins = (plugins,)
                if not isinstance(plugins, (tuple, list)) or any(
                    not isinstance(plugin, str) for plugin in plugins
                ):
                    raise ImpactUncertain("invalid_pytest_plugins")
                targets.update(plugins)
            if isinstance(node, ast.Import):
                targets.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                try:
                    base = _resolve_from(node, name, is_package=path.name == "__init__.py")
                except AuthorizationBoundaryError as exc:
                    raise ImpactUncertain("unresolved_relative_import") from exc
                targets.add(base)
                # Either a package submodule or a symbol; resolve both safely.
                targets.update(f"{base}.{alias.name}" for alias in node.names)
            elif isinstance(node, ast.Call) and relative.startswith("tests/"):
                called = node.func
                called_name = called.attr if isinstance(called, ast.Attribute) else (
                    called.id if isinstance(called, ast.Name) else ""
                )
                mode_index = 0 if isinstance(called, ast.Attribute) else 1
                mode = node.args[mode_index] if len(node.args) > mode_index else None
                explicit_write = (
                    called_name == "open" and isinstance(mode, ast.Constant)
                    and isinstance(mode.value, str)
                    and any(flag in mode.value for flag in "wax")
                    and "+" not in mode.value
                )
                if called_name in SOURCE_READ_CALLS and not explicit_write:
                    sentinels.add(relative)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if relative.startswith("tests/") and any(
                    marker in node.value.lower()
                    for marker in ("backend/", "app/", "app.")
                ):
                    sentinels.add(relative)
        for target in targets:
            parts = target.split(".")
            matches = [modules[".".join(parts[:end])]
                       for end in range(1, len(parts) + 1)
                       if ".".join(parts[:end]) in modules]
            if matches:
                for dependency in matches:
                    reverse[dependency].add(relative)
            elif target in namespaces:
                # Namespace packages have no initializer; concrete aliases above
                # still contribute their own module edges.
                continue
            elif parts[0] in {"app", "tests"}:
                raise ImpactUncertain("unresolved_repository_import")
            else:
                # pytest also admits bare, test-directory-local support imports.
                adjacent = [
                    (parent / target.replace(".", "/")).as_posix() + ".py"
                    for parent in Path(relative).parents
                ]
                nearest = next((candidate for candidate in adjacent if candidate in files), None)
                if nearest is not None:
                    reverse[nearest].add(relative)
                    continue
                local = bare_support[target]
                if len(local) > 1:
                    raise ImpactUncertain(f"ambiguous_test_support_import:{relative}:{target}")
                if local:
                    reverse[local[0]].add(relative)
        parents = Path(relative).parents
        for parent in parents:
            for implicit in ("__init__.py", "conftest.py"):
                candidate = (parent / implicit).as_posix()
                if candidate in files and candidate != relative and (
                    implicit == "__init__.py" or relative.startswith("tests/")
                ):
                    reverse[candidate].add(relative)
    return DependencyGraph(
        {path: frozenset(consumers) for path, consumers in reverse.items()},
        frozenset(files), frozenset(uncertain), frozenset(sentinels),
    )


def affected_modules(
    base: DependencyGraph,
    head: DependencyGraph,
    changed: tuple[str, ...],
    executable_modules: tuple[str, ...],
) -> tuple[str, ...]:
    """Union base/head consumers, owner tests and non-import sentinels."""
    executable = set(executable_modules)
    if not executable or not executable <= head.paths:
        raise ImpactUncertain("unresolved_executable_inventory")
    reverse: dict[str, set[str]] = defaultdict(set)
    for graph in (base, head):
        for path, consumers in graph.reverse.items():
            reverse[path].update(consumers)
    seeds: set[str] = set()
    selected: set[str] = set()
    for path in changed:
        relative = path.removeprefix("backend/")
        if relative not in base.paths | head.paths:
            raise ImpactUncertain("unmapped_changed_python")
        if relative.startswith("tests/"):
            if relative not in executable:
                raise ImpactUncertain("changed_test_support_or_deleted_test")
        else:
            parts = Path(relative).parts
            if len(parts) < 4 or parts[:2] != ("app", "modules"):
                raise ImpactUncertain("shared_application_surface")
            owner = parts[2]
            if owner not in OWNER_TEST_ROOTS:
                raise ImpactUncertain("cross_cutting_owner")
            if any(part in {"api", "models", "schemas"} or
                   part.endswith(("models.py", "schemas.py", "model.py", "schema.py"))
                   for part in parts[3:]):
                raise ImpactUncertain("schema_or_public_contract")
            roots = OWNER_TEST_ROOTS[owner]
            owned = {module for module in executable if module.startswith(roots)}
            if not owned:
                raise ImpactUncertain("unmapped_owner_tests")
            selected.update(owned)
        seeds.add(relative)
    # Test modules can also be loaded dynamically or inspected as source by
    # other tests. Test-only diffs do not excuse these non-import consumers.
    seeds.update(base.uncertain_tests | head.uncertain_tests)
    seeds.update(base.sentinels | head.sentinels)
    pending = list(seeds)
    reached = set(seeds)
    while pending:
        for consumer in reverse[pending.pop()] - reached:
            reached.add(consumer)
            pending.append(consumer)
    selected.update(reached & executable)
    for uncertain in head.uncertain_tests:
        if uncertain not in executable and not reverse[uncertain]:
            raise ImpactUncertain("unresolved_uncertain_test_support")
    if not selected:
        raise ImpactUncertain("zero_selected_modules")
    return tuple(sorted(selected))
