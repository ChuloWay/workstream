"""Shared isolated PostgreSQL fixtures for compensation adapter-binding tests."""

from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime
from uuid import UUID
from app.core.identifiers import new_record_id

import pytest

from app.core.config import get_settings
from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.compensation.models import CompensationAdapterBindingLifecycleEvent
from tests.project_create_fixtures import insert_historical_project

BindingSeed = Callable[[], Awaitable[tuple[UUID, UUID, UUID]]]


def created_binding_events(
    project_id: str, actor_profile_id: str, *binding_ids: UUID
) -> list[CompensationAdapterBindingLifecycleEvent]:
    """Build canonical created events for pre-existing test binding seeds."""
    return [
        CompensationAdapterBindingLifecycleEvent(
            id=new_record_id(), operation_id=new_record_id(), request_digest="sha256:" + "0" * 64,
            project_id=project_id, adapter_binding_id=binding_id,
            event_type="created", actor_profile_id=actor_profile_id,
            from_status=None, to_status="active",
            from_lifecycle_version=0, to_lifecycle_version=1,
        )
        for binding_id in binding_ids
    ]






@pytest.fixture
def compensation_database_env(
    monkeypatch: pytest.MonkeyPatch, clean_postgres_database: str
) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    get_settings.cache_clear()
    yield clean_postgres_database
    get_settings.cache_clear()


@pytest.fixture
def binding_seed() -> BindingSeed:
    async def seed() -> tuple[UUID, UUID, UUID]:
        project_id, adapter_id, actor_id = new_record_id(), new_record_id(), new_record_id()
        async with db_session.get_session_factory()() as session:
            session.add_all(
                (
                    ActorProfile(
                        id=str(actor_id), actor_kind="human", status="active",
                        provisioning_method="automatic_first_access", created_by=str(actor_id),
                    ),
                    ActorProfile(
                        id=str(adapter_id), actor_kind="human", status="active",
                        provisioning_method="automatic_first_access",
                        # Neutral FK row only. The separate CP02 marker simulates
                        # the future ACTORS-owned positive eligibility decision.
                        created_by=str(actor_id),
                    ),
                )
            )
            await session.flush()
            session.add_all(
                (
                    ActorIdentityLink(
                        id=str(new_record_id()), actor_profile_id=str(actor_id),
                        issuer="https://compensation.test", subject=f"creator-{actor_id}",
                        subject_kind="human", status="active", linked_by=str(actor_id),
                        last_verified_at=datetime.now(UTC),
                    ),
                    ActorIdentityLink(
                        id=str(new_record_id()), actor_profile_id=str(adapter_id),
                        issuer="https://compensation.test", subject=f"adapter-{adapter_id}",
                        subject_kind="human", status="active", linked_by=str(actor_id),
                        last_verified_at=datetime.now(UTC),
                    ),
                )
            )
            await insert_historical_project(
                session, project_id=str(project_id), name="Compensation project",
                slug=f"compensation-{str(project_id)[:8]}",
            )
            await session.commit()
        return project_id, adapter_id, actor_id

    return seed
