"""Actual staged effects and fresh-session rollback, not label-only failures."""

from uuid import uuid4

import pytest

from tests.authorization.admin_access.fault_support import fail_admin_read, fail_next_commit
from tests.authorization.admin_access.read_support import READ_ACTIONS, read_path
from tests.authorization.admin_access.support import (
    AdminAccess,
    actor_observation,
    assert_unavailable,
    authority_snapshot,
    grant_body,
    seed_old_observation,
)


@pytest.mark.parametrize("surface", ["profile", "link"])
@pytest.mark.parametrize("stage", ["evidence", "lookup", "touch", "commit"])
async def test_admin_read_failure_rolls_back_staged_effects(
    admin_access: AdminAccess,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
    stage: str,
) -> None:
    access = admin_access
    before_actor = await seed_old_observation(access.admin.id)
    before = await authority_snapshot()
    probe = fail_admin_read(monkeypatch, access.admin.id, surface, stage)
    response = await access.signed.client.get(
        read_path(access.target.id, surface), headers=access.admin.headers
    )
    assert_unavailable(response)
    assert probe.rows is not None, "failure must reach the claimed transaction stage"
    action, _ = READ_ACTIONS[surface]
    staged = [e for e in probe.rows["audit_events"] if e["action_id"] == action]
    assert len(staged) == (0 if stage == "evidence" else 1)
    if staged:
        assert staged[0]["event_type"] == "SensitiveAuthorizationAllowed"
        assert staged[0]["resource_id"] == str(access.target.id)
    assert probe.actor is not None
    if stage == "commit":
        assert probe.actor.last_seen_at > before_actor.last_seen_at
        assert probe.actor.last_verified_at > before_actor.last_verified_at
    else:
        assert probe.actor == before_actor
    assert await authority_snapshot() == before
    assert await actor_observation(access.admin.id) == before_actor


async def test_catalogue_read_commit_failure_rolls_back_observation(
    admin_access: AdminAccess,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = admin_access
    before_actor = await seed_old_observation(access.admin.id)
    before = await authority_snapshot()
    probe = fail_next_commit(monkeypatch, access.admin.id)
    response = await access.signed.client.get(
        "/api/v1/authorization/permissions", headers=access.admin.headers
    )
    assert_unavailable(response)
    assert probe.actor is not None
    assert probe.actor.last_seen_at > before_actor.last_seen_at
    assert probe.actor.last_verified_at > before_actor.last_verified_at
    assert probe.rows is not None
    assert any(
        e["action_id"] == "authorization.permission_catalogue.read"
        and e["event_type"] == "SensitiveAuthorizationAllowed"
        for e in probe.rows["audit_events"]
    )
    assert await authority_snapshot() == before
    assert await actor_observation(access.admin.id) == before_actor


async def test_admin_self_patch_commit_failure_rolls_back(
    admin_access: AdminAccess,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = admin_access
    before_actor = await seed_old_observation(access.admin.id)
    before = await authority_snapshot()
    probe = fail_next_commit(monkeypatch, access.admin.id)
    response = await access.signed.client.patch(
        "/api/v1/actors/me",
        headers=access.admin.headers,
        json={"display_name": "Must roll back"},
    )
    assert_unavailable(response)
    assert probe.actor is not None
    assert probe.actor.display_name == "Must roll back"
    assert probe.actor.last_seen_at > before_actor.last_seen_at
    assert probe.actor.last_verified_at > before_actor.last_verified_at
    assert probe.rows is not None
    assert any(e["action_id"] == "actor.profile.update_self" for e in probe.rows["audit_events"])
    assert await authority_snapshot() == before
    assert await actor_observation(access.admin.id) == before_actor


@pytest.mark.parametrize("operation", ["issue", "revoke"])
async def test_grant_mutation_commit_failure_rolls_back(
    admin_access: AdminAccess,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    access = admin_access
    body = grant_body(access.target.id)
    grant_id = (
        await access.signed.grant(access.admin, access.target) if operation == "revoke" else None
    )
    before_actor = await seed_old_observation(access.admin.id)
    before = await authority_snapshot()
    key = str(uuid4())
    probe = fail_next_commit(monkeypatch, access.admin.id, grant_operation=operation)
    if operation == "issue":
        response = await access.signed.issue(access.admin, body, key=key)
    else:
        response = await access.signed.revoke(access.admin, grant_id, key=key)
    assert_unavailable(response)
    assert probe.rows is not None
    grants = [
        r
        for r in probe.rows["admin_role_grants"]
        if r["target_actor_profile_id"] == str(access.target.id)
    ]
    assert len(grants) == 1
    assert grants[0]["status"] == ("active" if operation == "issue" else "revoked")
    assert grants[0]["version"] == (1 if operation == "issue" else 2)
    events = [
        e
        for e in probe.rows["audit_events"]
        if e["entity_id"] == str(grants[0]["id"])
        and e["event_type"]
        == ("AdminRoleGrantIssued" if operation == "issue" else "AdminRoleGrantRevoked")
    ]
    assert len(events) == 1
    assert (
        sum(
            e["invalidation_cause_event_id"] == str(events[0]["id"])
            for e in probe.rows["audit_events"]
        )
        == 1
    )
    assert probe.actor is not None
    assert probe.actor.last_seen_at > before_actor.last_seen_at
    assert probe.actor.last_verified_at > before_actor.last_verified_at
    assert await authority_snapshot() == before
    assert await actor_observation(access.admin.id) == before_actor
    if operation == "issue":
        retried = await access.signed.issue(access.admin, body, key=key)
    else:
        retried = await access.signed.revoke(access.admin, grant_id, key=key)
    assert retried.status_code == (201 if operation == "issue" else 200), retried.text
