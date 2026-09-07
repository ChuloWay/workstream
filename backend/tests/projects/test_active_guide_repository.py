"""Active-guide query scope and result handling without database lock claims."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import ProjectGuide
from app.modules.projects.repository import ProjectRepository, ProjectRepositoryIntegrityError


@pytest.mark.parametrize("method", ["get_active_guide", "lock_active_guide"])
@pytest.mark.parametrize("count", [0, 1, 2], ids=["absent", "single", "ambiguous"])
async def test_active_guide_lookup_scope_and_cardinality(method, count):
    """Select this project's active guide, or fail closed on ambiguous results."""
    guides = [
        ProjectGuide(id=f"guide-{index}", project_id="project-target", version=f"v{index}", status="active")
        for index in range(count)
    ]
    result = MagicMock(spec=Result)
    result.scalars.return_value.all.return_value = guides
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = result

    lookup = getattr(ProjectRepository(session), method)
    if count == 2:
        with pytest.raises(ProjectRepositoryIntegrityError, match="^multiple active guides found for project$"):
            await lookup("project-target")
    else:
        assert await lookup("project-target") is (guides[0] if count else None)

    session.execute.assert_awaited_once()
    statement = session.execute.call_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert compiled.params == {"project_id_1": "project-target", "status_1": "active"}
    assert "WHERE project_guides.project_id = %(project_id_1)s AND project_guides.status = %(status_1)s" in str(compiled)
    assert str(compiled).endswith("FOR UPDATE") is (method == "lock_active_guide")
    assert statement.column_descriptions[0]["entity"] is ProjectGuide
