"""Standard mock ports; no duplicate authorization, replay, or lifecycle evaluator."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.modules.projects import sufficiency_mutation_service as module
from projects.sufficiency_mutations import rows


@pytest.fixture
def case():
    session = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    service = module.GuideSufficiencyMutationService(session)
    report, setup = rows.report_row(), rows.setup_row()
    lineage = module._Lineage(
        "v1", rows.SNAPSHOT, rows.SNAPSHOT_HASH, 1, rows.SETUP, rows.STALE_HASH
    )
    resolved = SimpleNamespace(
        profile=SimpleNamespace(id=str(rows.ACTOR)),
        identity_link=SimpleNamespace(id=str(rows.LINK)),
    )
    decision = SimpleNamespace(
        matched_authority_kind=module.MatchedAuthorityKind.ADMIN_ROLE_GRANT,
        matched_grant_id=rows.GRANT,
        matched_scope_project_id=rows.PROJECT,
        decision_id=UUID(int=10),
        resource_context_digest=rows.RESOURCE_HASH,
    )
    handle = object()
    prepared = SimpleNamespace(
        prepare=AsyncMock(return_value=handle),
        consume=AsyncMock(return_value=decision),
        deny_unsupported=AsyncMock(side_effect=RuntimeError("unexpected authorization denial")),
    )

    async def add_report(value):
        value.created_at = rows.NOW
        return value

    projects = SimpleNamespace(
        get_sufficiency_report_for_snapshot=AsyncMock(return_value=None),
        get_guide_sufficiency_report=AsyncMock(return_value=report),
        lock_guide_sufficiency_report=AsyncMock(return_value=report),
        add_guide_sufficiency_report=AsyncMock(side_effect=add_report),
        lock_project_setup_run=AsyncMock(return_value=setup),
    )
    reservation = SimpleNamespace(id=str(UUID(int=11)))
    replay = SimpleNamespace(
        find=AsyncMock(return_value=None),
        reserve=AsyncMock(return_value=("claimed", reservation)),
        complete=AsyncMock(),
    )
    actual_lineage = service._lineage
    service._lineage = AsyncMock(return_value=lineage)
    service._projects, service._replay = projects, replay
    return SimpleNamespace(
        service=service,
        session=session,
        projects=projects,
        replay=replay,
        report=report,
        setup=setup,
        lineage=lineage,
        resolved=resolved,
        decision=decision,
        prepared=prepared,
        handle=handle,
        reservation=reservation,
        actual_lineage=actual_lineage,
    )
