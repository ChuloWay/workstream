# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalOperand=false
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from uuid import UUID, uuid4

import pytest
from sqlalchemy import UniqueConstraint, event

from app.db import session as db_session
from app.modules.actors.models import (
    ActorIdentityLink,
    ActorProfile,
)
from app.modules.actors.repository import ActorRepository
from app.modules.actors.api import ServiceIdentity

from tests.actors.support import ISSUER
from tests.actors.support import resolved_actor


def test_candidate_exists_query_is_backed_by_one_link_per_profile_constraint() -> None:
    assert any(
        isinstance(constraint, UniqueConstraint)
        and {column.name for column in constraint.columns} == {"actor_profile_id"}
        for constraint in ActorIdentityLink.__table__.constraints
    )


@pytest.fixture
async def candidate_rows(actor_database_env):
    created_at = datetime(2026, 7, 22, tzinfo=UTC)
    caller_id = UUID(int=1)
    eligible_ids = [UUID(int=value) for value in (5, 6, 7)]
    inactive_id = UUID(int=2)
    revoked_id = UUID(int=3)
    service_id = UUID(int=4)
    async with db_session.get_session_factory()() as session:
        profiles = [
            ActorProfile(
                id=str(actor_id),
                actor_kind="human",
                status=("suspended" if actor_id == inactive_id else "active"),
                provisioning_method="automatic_first_access",
                created_by=str(actor_id),
                created_at=created_at,
                suspended_by=(str(caller_id) if actor_id == inactive_id else None),
                suspended_at=(created_at if actor_id == inactive_id else None),
                suspension_reason=("test hold" if actor_id == inactive_id else None),
            )
            for actor_id in [caller_id, *eligible_ids, inactive_id, revoked_id]
        ]
        session.add_all(profiles)
        session.add(
            ActorProfile(
                id=str(service_id),
                actor_kind="service",
                status="active",
                provisioning_method="manual_service_provisioning",
                service_identity=ServiceIdentity.ARTIFACT_VERIFIER.value,
                created_by=str(caller_id),
                created_at=created_at,
            )
        )
        await session.flush()
        session.add_all(
            [
                ActorIdentityLink(
                    id=str(uuid4()),
                    actor_profile_id=str(actor_id),
                    issuer=ISSUER,
                    subject=f"candidate-{actor_id}",
                    subject_kind="human",
                    status=("revoked" if actor_id == revoked_id else "active"),
                    linked_by=str(actor_id),
                    last_verified_at=created_at,
                    revoked_by=(str(caller_id) if actor_id == revoked_id else None),
                    revoked_at=(created_at if actor_id == revoked_id else None),
                    revoked_reason=("test revoke" if actor_id == revoked_id else None),
                )
                for actor_id in [caller_id, *eligible_ids, inactive_id, revoked_id]
            ]
        )
        session.add(
            ActorIdentityLink(
                id=str(uuid4()),
                actor_profile_id=str(service_id),
                issuer=ISSUER,
                subject=f"candidate-service-{service_id}",
                subject_kind="service",
                status="active",
                linked_by=str(caller_id),
                last_verified_at=None,
            )
        )
        await session.commit()
        yield session, caller_id, eligible_ids, created_at, service_id


@pytest.mark.parametrize("after_first", [False, True], ids=["first-page", "cursor-page"])
async def test_contributor_candidate_query_filters_and_paginates_without_gaps(
    candidate_rows, after_first
):
    session, caller_id, eligible_ids, created_at, service_id = candidate_rows
    statements = []

    def record_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    engine = db_session.get_engine().sync_engine
    event.listen(engine, "before_cursor_execute", record_sql)
    try:
        rows = await ActorRepository(session).list_contributor_candidates(
            caller_actor_profile_id=caller_id,
            cursor=(created_at, eligible_ids[0]) if after_first else None,
            limit=1,
        )
    finally:
        event.remove(engine, "before_cursor_execute", record_sql)

    expected = eligible_ids[1:] if after_first else eligible_ids[:2]
    assert [row.id for row in rows] == [str(value) for value in expected]
    assert len(statements) == 1
    assert "count(" not in statements[0].lower()
    assert all(str(service_id) != row.id for row in rows)


def test_service_identity_lock_has_a_distinct_domain_without_changing_external_keys() -> None:
    issuer = "service_identity"
    subject = "workstream.artifact.verifier"
    framed = (
        len(issuer.encode()).to_bytes(4, "big")
        + issuer.encode()
        + len(subject.encode()).to_bytes(4, "big")
        + subject.encode()
    )
    historical_external_key = int.from_bytes(
        hashlib.sha256(framed).digest()[:8],
        "big",
        signed=True,
    )

    assert ActorRepository._advisory_key(issuer, subject) == historical_external_key
    assert ActorRepository._advisory_key(subject, domain=b"\x01") != historical_external_key


@pytest.mark.parametrize("missing", ["profile", "link"])
async def test_actor_timestamp_touch_fails_closed_before_writes_on_missing_rows(missing):
    original = resolved_actor(subject="timestamp-actor")
    profile, link = original.profile, original.identity_link
    repository = ActorRepository(object())
    calls = []

    async def get_profile(actor_id, *, for_update=False):
        calls.append(("profile", actor_id, for_update))
        assert (actor_id, for_update) == (profile.id, True)
        return None if missing == "profile" else profile

    async def get_link(link_id, *, for_update=False):
        calls.append(("link", link_id, for_update))
        assert (link_id, for_update) == (link.id, True)
        return None

    repository.get_actor_profile = get_profile
    repository.get_identity_link_by_id = get_link

    with pytest.raises(RuntimeError, match=f"{missing} disappeared"):
        await repository.touch_verified_actor(profile, link)

    expected = [("profile", profile.id, True)]
    if missing == "link":
        expected.append(("link", link.id, True))
    assert calls == expected
