"""Actual reservation/control contention and serialized authority outcomes."""

from uuid import uuid4

import pytest

from scripts.bootstrap_access_administrator import _run as run_bootstrap
from app.modules.authorization.repository import AdminAuthorizationRepository
from tests.authorization.admin_access.concurrency_support import (
    control_owner_without_row_lock,
    ordered_owner_calls,
)
from tests.authorization.admin_access.support import (
    AdminAccess,
    SignedAccess,
    authority_snapshot,
    create_project,
    grant_body,
)


async def test_concurrent_bootstrap_has_one_persisted_winner(
    signed_access: SignedAccess,
    auth_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = await signed_access.actor("bootstrap-first")
    second = await signed_access.actor("bootstrap-second")
    won, lost, custody = await ordered_owner_calls(
        lambda: run_bootstrap(first.id, execute=True),
        lambda: run_bootstrap(second.id, execute=True),
        boundary="control",
        database_url=auth_database_env,
        monkeypatch=monkeypatch,
    )
    assert custody.observed
    assert (won[0], lost[0]) == (0, 3)
    assert lost[1]["grant_id"] == won[1]["grant_id"]
    rows = await authority_snapshot()
    assert len(rows["admin_role_grants"]) == 1
    grant = rows["admin_role_grants"][0]
    assert str(grant["id"]) == won[1]["grant_id"]
    assert grant["target_actor_profile_id"] == str(first.id)
    assert (grant["status"], grant["version"]) == ("active", 1)
    assert len(rows["authority_control"]) == 1
    assert rows["authority_control"][0]["bootstrap_completed"] is True
    events = [
        e
        for e in rows["audit_events"]
        if e["event_type"] == "InitialAccessAdministratorBootstrapped"
    ]
    assert len(events) == 1
    assert events[0]["entity_id"] == won[1]["grant_id"]
    conflicts = [e for e in rows["audit_events"] if e["event_type"] == "AdminRoleGrantIssueDenied"]
    assert len(conflicts) == 1
    assert conflicts[0]["target_actor_ref"] == str(second.id)


async def test_bootstrap_race_proof_rejects_missing_owner_lock(
    signed_access: SignedAccess,
    auth_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken_owner = control_owner_without_row_lock()
    with monkeypatch.context() as patch:
        patch.setattr(AdminAuthorizationRepository, "lock_control", broken_owner)
        with pytest.raises(AssertionError, match="actual owner lock observation failed") as failure:
            await test_concurrent_bootstrap_has_one_persisted_winner(
                signed_access,
                auth_database_env,
                monkeypatch,
            )
    assert isinstance(failure.value.__cause__, AssertionError)
    assert (
        str(failure.value.__cause__) == "ordered lifecycle request never reached the database lock"
    )


async def test_concurrent_same_key_grant_returns_one_result(
    admin_access: AdminAccess,
    auth_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = admin_access
    key = str(uuid4())
    body = grant_body(access.target.id)
    first, second, custody = await ordered_owner_calls(
        lambda: access.signed.issue(access.admin, body, key=key),
        lambda: access.signed.issue(access.admin, body, key=key),
        boundary="reservation",
        database_url=auth_database_env,
        monkeypatch=monkeypatch,
    )
    assert custody.observed
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    rows = await authority_snapshot()
    grants = [
        r
        for r in rows["admin_role_grants"]
        if r["target_actor_profile_id"] == str(access.target.id)
    ]
    assert len(grants) == 1
    assert str(grants[0]["id"]) == first.json()["resource_id"]
    records = [r for r in rows["authority_idempotency_records"] if str(r["idempotency_key"]) == key]
    assert len(records) == 1
    events = [
        e for e in rows["audit_events"] if str(e["idempotency_reference"]) == str(records[0]["id"])
    ]
    success = [e for e in events if e["event_type"] == "AdminRoleGrantIssued"]
    assert len(success) == 1
    assert sum(e["invalidation_cause_event_id"] == success[0]["id"] for e in events) == 1


async def test_concurrent_distinct_keys_create_one_active_grant(
    admin_access: AdminAccess,
    auth_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = admin_access
    body = grant_body(access.target.id)
    first_key, second_key = str(uuid4()), str(uuid4())
    first, second, custody = await ordered_owner_calls(
        lambda: access.signed.issue(access.admin, body, key=first_key),
        lambda: access.signed.issue(access.admin, body, key=second_key),
        boundary="control",
        database_url=auth_database_env,
        monkeypatch=monkeypatch,
    )
    assert custody.observed
    assert (first.status_code, second.status_code) == (201, 409)
    assert second.json()["error"]["code"] == "admin_role_grant_exists"
    rows = await authority_snapshot()
    grants = [
        r
        for r in rows["admin_role_grants"]
        if r["target_actor_profile_id"] == str(access.target.id)
    ]
    assert len(grants) == 1
    assert (grants[0]["status"], grants[0]["version"]) == ("active", 1)
    records = [
        r
        for r in rows["authority_idempotency_records"]
        if str(r["idempotency_key"]) in {first_key, second_key}
    ]
    assert [str(r["idempotency_key"]) for r in records] == [first_key]
    assert sum(e["event_type"] == "AdminRoleGrantIssued" for e in rows["audit_events"]) == 1
    assert sum(e["event_type"] == "AdminRoleGrantIssueDenied" for e in rows["audit_events"]) == 1


async def test_cross_revoke_retains_one_effective_admin(
    admin_access: AdminAccess,
    auth_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access = admin_access
    second_grant = await access.signed.grant(
        access.admin, access.target, role="access_administrator"
    )
    first, second, custody = await ordered_owner_calls(
        lambda: access.signed.revoke(access.admin, second_grant),
        lambda: access.signed.revoke(access.target, access.bootstrap_grant_id),
        boundary="control",
        database_url=auth_database_env,
        monkeypatch=monkeypatch,
    )
    assert custody.observed
    assert (first.status_code, second.status_code) == (200, 403)
    assert second.json()["error"]["code"] == "permission_not_granted"
    rows = await authority_snapshot()
    active = [
        r
        for r in rows["admin_role_grants"]
        if r["role"] == "access_administrator" and r["status"] == "active"
    ]
    assert [str(r["id"]) for r in active] == [access.bootstrap_grant_id]
    events = [e for e in rows["audit_events"] if e["event_type"] == "AdminRoleGrantRevoked"]
    assert len(events) == 1
    assert events[0]["entity_id"] == second_grant
    assert (
        sum(e["invalidation_cause_event_id"] == events[0]["id"] for e in rows["audit_events"]) == 1
    )


@pytest.mark.parametrize("first_operation", ["issue", "revoke"])
async def test_issue_against_revocation_obeys_lock_order(
    admin_access: AdminAccess,
    auth_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
    first_operation: str,
) -> None:
    access = admin_access
    second_grant = await access.signed.grant(
        access.admin, access.target, role="access_administrator"
    )
    recipient = await access.signed.actor("project-manager-recipient")
    project = await create_project("Serialized project authority")
    issue_key, revoke_key = str(uuid4()), str(uuid4())
    calls = {
        "issue": lambda: access.signed.issue(
            access.target,
            grant_body(recipient.id, role="project_manager", project_id=project),
            key=issue_key,
        ),
        "revoke": lambda: access.signed.revoke(access.admin, second_grant, key=revoke_key),
    }
    second_operation = "revoke" if first_operation == "issue" else "issue"
    first, second, custody = await ordered_owner_calls(
        calls[first_operation],
        calls[second_operation],
        boundary="control",
        database_url=auth_database_env,
        monkeypatch=monkeypatch,
    )
    assert custody.observed
    responses = {first_operation: first, second_operation: second}
    assert responses["revoke"].status_code == 200
    assert responses["issue"].status_code == (201 if first_operation == "issue" else 403)
    if first_operation == "revoke":
        assert responses["issue"].json()["error"]["code"] == "permission_not_granted"
    rows = await authority_snapshot()
    grants = [
        r for r in rows["admin_role_grants"] if r["target_actor_profile_id"] == str(recipient.id)
    ]
    assert len(grants) == (1 if first_operation == "issue" else 0)
    events = [
        e
        for e in rows["audit_events"]
        if e["event_type"] == "AdminRoleGrantIssued" and e["target_actor_ref"] == str(recipient.id)
    ]
    assert len(events) == len(grants)
    records = [
        r for r in rows["authority_idempotency_records"] if str(r["idempotency_key"]) == issue_key
    ]
    assert len(records) == len(grants)
    if events:
        assert events[0]["entity_id"] == str(grants[0]["id"])
        assert (
            sum(e["invalidation_cause_event_id"] == events[0]["id"] for e in rows["audit_events"])
            == 1
        )
    revoked = next(r for r in rows["admin_role_grants"] if str(r["id"]) == second_grant)
    assert revoked["status"] == "revoked"
    revoke_events = [
        e
        for e in rows["audit_events"]
        if e["event_type"] == "AdminRoleGrantRevoked" and e["entity_id"] == second_grant
    ]
    assert len(revoke_events) == 1
    assert (
        sum(
            e["invalidation_cause_event_id"] == revoke_events[0]["id"] for e in rows["audit_events"]
        )
        == 1
    )
    if first_operation == "revoke":
        denied = [
            e
            for e in rows["audit_events"]
            if e["event_type"] == "SensitiveAuthorizationDenied"
            and e["action_id"] == "admin_role_grant.issue"
            and e["resource_id"] == str(recipient.id)
        ]
        assert len(denied) == 1
        assert not any(
            e["event_type"] == "AuthorityInvalidationRequested"
            and e["invalidation_target_ref"] == str(recipient.id)
            for e in rows["audit_events"]
        )
