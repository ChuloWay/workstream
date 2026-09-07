"""Syntax-aware negative reachability proofs for the hidden finalization owner."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OWNER = ROOT / "app/modules/projects/guide_compilation"
SOURCES = (
    OWNER / "finalization.py",
    OWNER / "finalization_payloads.py",
    OWNER / "custody_payloads.py",
)


def imports_and_calls(paths):
    imports = set()
    calls = set()
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
                elif isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
    return imports, calls


def test_finalization_has_no_route():
    imports, calls = imports_and_calls((ROOT / "app/modules/projects/router.py",))
    assert not any("finalization" in name.lower() for name in imports | calls)


def test_finalization_has_no_queue_composition():
    imports, calls = imports_and_calls((ROOT / "app/workers/project_setup.py",))
    assert not any("finalization" in name.lower() for name in imports | calls)


def test_finalization_cannot_call_projection_ports():
    imports, calls = imports_and_calls(SOURCES)
    assert imports.isdisjoint(
        {
            "projections",
            "projection_payloads",
            "GuideCompilationProjectionService",
            "ArtifactPolicyProjectionPort",
            "GuideSufficiencyProjectionPort",
        }
    )
    assert calls.isdisjoint({"project_guide_sufficiency", "project_submission_artifact_policy"})


def test_finalization_cannot_import_or_call_provider():
    imports, calls = imports_and_calls(SOURCES)
    assert not any(
        name.startswith(("app.adapters.project_agents", "openai", "agents")) for name in imports
    )
    assert calls.isdisjoint({"compile_project_guide", "run", "run_sync", "create_response"})


def test_finalization_cannot_reach_legacy_inference():
    imports, calls = imports_and_calls(SOURCES)
    assert "app.modules.projects.service" not in imports
    assert calls.isdisjoint(
        {
            "analyze_guide_sufficiency",
            "derive_submission_artifact_policy",
            "derive_post_submit_checker_policy",
        }
    )


def test_finalization_cannot_reach_approval_or_activation():
    _, calls = imports_and_calls(SOURCES)
    assert calls.isdisjoint(
        {
            "approve_submission_artifact_policy",
            "activate_project_guide",
            "approve_post_submit_checker_policy",
        }
    )


def test_finalization_has_no_downstream_product_imports():
    imports, _ = imports_and_calls(SOURCES)
    assert not any(
        name.startswith(
            tuple(
                "app.modules." + owner
                for owner in ("tasks", "reviews", "contributions", "compensation", "checkers")
            )
        )
        for name in imports
    )


def test_negative_structure_probe_detects_forbidden_calls(tmp_path):
    path = tmp_path / "mutation.py"
    path.write_text(
        "from app.modules.projects.service import ProjectService\nservice.project_guide_sufficiency()\n"
    )
    imports, calls = imports_and_calls((path,))
    assert "app.modules.projects.service" in imports
    assert "project_guide_sufficiency" in calls
