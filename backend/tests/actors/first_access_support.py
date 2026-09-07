"""Real first-access scheduling and projections of persisted audit evidence."""

import asyncio
from uuid import uuid4

from sqlalchemy import text

from app.modules.actors.repository import ActorRepository
from app.modules.actors.service import ActorService
from auth_concurrency_support import wait_for_named_database_lock


class FirstAccessRace:
    """Coordinate real lookups and advisory locks without replacing their results."""

    def __init__(self, monkeypatch, database_url):
        suffix = uuid4().hex
        self.holder, self.contender = f"first-holder-{suffix}", f"first-contender-{suffix}"
        self.lookups = {self.holder: [], self.contender: []}
        self.pids = {}
        self.touches = []
        self.observed_exact_wait = False
        both_looked_up, held, contender_identified = (asyncio.Event() for _ in range(3))
        original_find = ActorService.find_verified_actor
        original_lock = ActorRepository.lock_external_identity
        original_touch = ActorService._touch_verified_actor

        async def find(service, token):
            name = asyncio.current_task().get_name()
            resolved = await original_find(service, token)
            self.lookups[name].append(resolved)
            if len(self.lookups[name]) == 1:
                if all(self.lookups.values()):
                    both_looked_up.set()
                await both_looked_up.wait()
            return resolved

        async def lock(repository, issuer, subject):
            name = asyncio.current_task().get_name()
            self.pids[name] = await repository._session.scalar(text("select pg_backend_pid()"))
            if name == self.holder:
                await original_lock(repository, issuer, subject)
                held.set()
                await contender_identified.wait()
                await wait_for_named_database_lock(
                    database_url,
                    self.contender,
                    expected_waiter_pid=self.pids[self.contender],
                    expected_blocker_pid=self.pids[self.holder],
                )
                self.observed_exact_wait = True
                return
            contender_identified.set()
            await held.wait()
            await repository._session.execute(
                text("select set_config('application_name', :name, true)"), {"name": name}
            )
            await original_lock(repository, issuer, subject)

        async def touch(service, resolved):
            self.touches.append(
                (asyncio.current_task().get_name(), resolved.profile.id, resolved.identity_link.id)
            )
            return await original_touch(service, resolved)

        monkeypatch.setattr(ActorService, "find_verified_actor", find)
        monkeypatch.setattr(ActorRepository, "lock_external_identity", lock)
        monkeypatch.setattr(ActorService, "_touch_verified_actor", touch)


EVENT_FIELDS = (
    "event_type",
    "request_id",
    "correlation_id",
    "actor_ref_kind",
    "actor_id",
    "target_actor_ref_kind",
    "target_actor_ref",
    "entity_type",
    "entity_id",
    "resource_type",
    "resource_id",
    "target_ref_kind",
    "target_ref_id",
    "reason",
    "after_facts",
    "idempotency_reference",
    "invalidation_cause_event_id",
)


def event_views(events):
    """Return observed fields only; expected values are independent test literals."""
    return sorted(
        ({key: getattr(event, key) for key in EVENT_FIELDS} for event in events),
        key=lambda row: row["event_type"],
    )


def expected_first_access_events(profile_id, link_id, request_id, correlation_id):
    """The two published first-access evidence shapes, independent of production builders."""
    common = {
        "request_id": str(request_id),
        "correlation_id": str(correlation_id),
        "actor_ref_kind": "actor_profile",
        "actor_id": profile_id,
        "target_actor_ref_kind": "actor_profile",
        "target_actor_ref": profile_id,
        "idempotency_reference": None,
        "invalidation_cause_event_id": None,
    }
    return [
        {
            **common,
            "event_type": "ActorIdentityLinked",
            "entity_type": "actor_identity_link",
            "entity_id": link_id,
            "resource_type": "actor_identity_link",
            "resource_id": link_id,
            "target_ref_kind": "actor_identity_link",
            "target_ref_id": link_id,
            "reason": "identity_lifecycle_change",
            "after_facts": {"status": "active", "subject_kind": "human"},
        },
        {
            **common,
            "event_type": "ActorProfileProvisioned",
            "entity_type": "actor_profile",
            "entity_id": profile_id,
            "resource_type": "actor_profile",
            "resource_id": profile_id,
            "target_ref_kind": "actor_profile",
            "target_ref_id": profile_id,
            "reason": "automatic_first_access",
            "after_facts": {
                "status": "active",
                "subject_kind": "human",
                "provisioning_method": "automatic_first_access",
            },
        },
    ]
