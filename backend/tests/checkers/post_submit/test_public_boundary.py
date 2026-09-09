"""New contracts cannot expose persistence, individual dispatch or live execution."""

import ast
import inspect
from pathlib import Path

from app.modules.checkers.api import PostSubmissionExecutionPort, UnavailablePostSubmissionExecution
from app.modules.checkers.api.post_submit import PostSubmissionEvaluationRequest


def test_public_api_has_no_private_owner_types():
    directory = Path(__file__).resolve().parents[3] / "app" / "modules" / "checkers" / "api"
    for name in ("post_submit.py", "post_submit_catalogue.py"):
        tree = ast.parse((directory / name).read_text())
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        assert not any(
            ".models" in item or ".repository" in item or ".runner" in item for item in imports
        )
        assert not any(
            item.startswith(("sqlalchemy", "app.interfaces.project_agents")) for item in imports
        )
    for cls in (PostSubmissionExecutionPort, UnavailablePostSubmissionExecution):
        methods = [
            name
            for name, method in inspect.getmembers(cls, inspect.isfunction)
            if not name.startswith("_")
        ]
        assert methods == ["evaluate_post_submission"]
    assert "checker_names" not in PostSubmissionEvaluationRequest.model_fields
    assert "prepared" not in PostSubmissionEvaluationRequest.model_fields
