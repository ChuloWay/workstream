"""Repository response-handling guards; SQL execution is a controlled port."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.modules.projects import sufficiency_mutation_repository as module
from projects.client_fixtures import (
    clear_project_settings_cache_after_test as clear_project_settings_cache_after_test,
)
from projects.sufficiency_mutations import rows


def reservation_values():
    return dict(
        actor_profile_id=str(rows.ACTOR),
        identity_link_id=str(rows.LINK),
        action_id="project.guide_sufficiency.run",
        idempotency_key=rows.KEY,
        request_digest=rows.STALE_HASH,
        resource_context_digest=rows.RESOURCE_HASH,
        operation_id=UUID(int=20),
        project_id=str(rows.PROJECT),
        guide_id=str(rows.GUIDE),
        source_snapshot_id=str(rows.SNAPSHOT),
        report_id=None,
        setup_run_id=str(rows.SETUP),
        setup_generation=1,
    )


@pytest.fixture
def conflict_case():
    values = reservation_values()
    row = SimpleNamespace(
        id=UUID(int=30), **values, status="pending", response_json=None, committed_at=None
    )
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=None), get=AsyncMock()
    )
    repository = module.GuideSufficiencyMutationReplayRepository(session)

    async def find(actor, action, key):
        assert (actor, action, key) == (row.actor_profile_id, row.action_id, row.idempotency_key)
        return row

    repository.find = AsyncMock(side_effect=find)
    return SimpleNamespace(repository=repository, session=session, row=row, values=values)


@pytest.mark.parametrize("status,expected", [("pending", "pending"), ("committed", "replayed")])
async def test_reservation_classifies_existing_conflict(conflict_case, status, expected):
    case = conflict_case
    case.row.status = status
    if status == "committed":
        case.row.response_json = {"id": str(rows.REPORT)}
        case.row.report_id = case.values["report_id"] = str(rows.REPORT)
        case.row.committed_at = rows.NOW
    assert await case.repository.reserve(**case.values) == (expected, case.row)
    case.repository.find.assert_awaited_once_with(
        str(rows.ACTOR), "project.guide_sufficiency.run", rows.KEY
    )
    case.session.get.assert_not_awaited()


async def test_reservation_rejects_changed_request(conflict_case):
    case = conflict_case
    values = {**case.values, "request_digest": "sha256:" + "f" * 64}
    assert values["request_digest"] != case.row.request_digest
    assert await case.repository.reserve(**values) == ("mismatch", case.row)
    case.repository.find.assert_awaited_once_with(
        str(rows.ACTOR), "project.guide_sufficiency.run", rows.KEY
    )
    case.session.get.assert_not_awaited()


async def test_reservation_returns_claimed_row(monkeypatch):
    row = SimpleNamespace(id=UUID(int=30))
    monkeypatch.setattr(module, "uuid4", lambda: UUID(int=30))
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=row.id), get=AsyncMock(return_value=row)
    )
    repository = module.GuideSufficiencyMutationReplayRepository(session)
    repository.find = AsyncMock()
    assert await repository.reserve(**reservation_values()) == ("claimed", row)
    session.get.assert_awaited_once_with(module.GuideSufficiencyMutationIdempotencyRecord, row.id)
    repository.find.assert_not_awaited()


async def test_missing_completion_is_integrity_error():
    session = SimpleNamespace(scalar=AsyncMock(return_value=None))
    repository = module.GuideSufficiencyMutationReplayRepository(session)
    with pytest.raises(
        module.ProjectRepositoryIntegrityError, match="invalid sufficiency replay completion"
    ):
        await repository.complete(
            SimpleNamespace(id=str(UUID(int=30))),
            response_json={"id": str(rows.REPORT)},
            report_id=str(rows.REPORT),
        )
    session.scalar.assert_awaited_once()


async def test_completion_accepts_returned_row():
    session = SimpleNamespace(scalar=AsyncMock(return_value=str(UUID(int=30))))
    repository = module.GuideSufficiencyMutationReplayRepository(session)
    assert (
        await repository.complete(
            SimpleNamespace(id=str(UUID(int=30))),
            response_json={"id": str(rows.REPORT)},
            report_id=str(rows.REPORT),
        )
        is None
    )
    session.scalar.assert_awaited_once()
