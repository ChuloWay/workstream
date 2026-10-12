"""New contracts cannot expose persistence, individual dispatch or live execution."""

import ast
from pathlib import Path

from app.modules.checkers.api.selected_post_submit import SelectedPostSubmissionEvaluationRequest


def test_public_api_has_no_private_owner_types():
    directory = Path(__file__).resolve().parents[3] / "app" / "modules" / "checkers" / "api"
    for name in ("selected_post_submit.py", "external.py"):
        tree = ast.parse((directory / name).read_text())
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        assert not any(
            ".models" in item or ".repository" in item or ".runner" in item for item in imports
        )
        assert not any(
            item.startswith(("sqlalchemy", "app.interfaces.project_agents")) for item in imports
        )
    assert "checker_names" not in SelectedPostSubmissionEvaluationRequest.model_fields
    assert "prepared" not in SelectedPostSubmissionEvaluationRequest.model_fields
