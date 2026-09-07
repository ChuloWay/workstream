"""Grant commands: real operation recovery, eligibility and caller isolation."""

from uuid import uuid4

import pytest

from tests.authorization.admin_access.read_support import seed_read_target
from tests.authorization.admin_access.support import (
    AdminAccess,
    actor_observation,
    authority_snapshot,
    concealed_error,
    create_project,
    grant_body,
    seed_old_observation,
)


@pytest.mark.parametrize(
    "operation,role,project_scoped",
    [
        ("issue", "operator", False),
        ("issue", "project_manager", True),
        ("issue", "audit_authority", True),
        ("issue", "audit_authority", False),
        ("issue", "access_administrator", False),
        ("revoke", "operator", False),
    ],
)
async def test_grant_mutation_exact_replay_has_one_effect(
    admin_access: AdminAccess,
    operation: str,
    role: str,
    project_scoped: bool,
) -> None:
    access = admin_access
    project = await create_project("Grant recovery") if project_scoped else None
    body = grant_body(access.target.id, role=role, project_id=project)
    grant_id = (
        await access.signed.grant(access.admin, access.target) if operation == "revoke" else None
    )
    before_actor = await seed_old_observation(access.admin.id)
    before = await authority_snapshot()
    key = str(uuid4())
    if operation == "issue":
        first = await access.signed.issue(access.admin, body, key=key)
        replay = await access.signed.issue(access.admin, body, key=key)
    else:
        assert grant_id is not None
        first = await access.signed.revoke(access.admin, grant_id, key=key)
        replay = await access.signed.revoke(access.admin, grant_id, key=key)
    assert first.status_code == replay.status_code == (201 if operation == "issue" else 200)
    assert first.json() == replay.json()
    assert first.json()["version"] == (1 if operation == "issue" else 2)
    after_actor = await actor_observation(access.admin.id)
    assert after_actor.last_seen_at > before_actor.last_seen_at
    assert after_actor.last_verified_at > before_actor.last_verified_at
    after = await authority_snapshot()
    records = [
        r for r in after["authority_idempotency_records"] if str(r["idempotency_key"]) == key
    ]
    assert len(records) == 1
    assert records[0]["operation"] == f"admin_role_grant.{operation}"
    assert records[0]["status"] == "committed"
    assert str(records[0]["response_resource_id"]) == first.json()["resource_id"]
    assert records[0]["response_resource_version"] == first.json()["version"]
    old_events = {r["id"] for r in before["audit_events"]}
    events = [r for r in after["audit_events"] if r["id"] not in old_events]
    success = [
        e
        for e in events
        if e["event_type"]
        == ("AdminRoleGrantIssued" if operation == "issue" else "AdminRoleGrantRevoked")
    ]
    assert len(success) == 1
    assert success[0]["entity_id"] == first.json()["resource_id"]
    assert success[0]["actor_id"] == str(access.admin.id)
    assert str(success[0]["idempotency_reference"]) == str(records[0]["id"])
    invalidations = [e for e in events if e["event_type"] == "AuthorityInvalidationRequested"]
    assert len(invalidations) == 1
    assert invalidations[0]["invalidation_cause_event_id"] == success[0]["id"]
    assert len(after["admin_role_grants"]) == len(before["admin_role_grants"]) + (
        operation == "issue"
    )


async def test_same_caller_key_is_isolated_by_grant_operation(admin_access: AdminAccess) -> None:
    access = admin_access
    key = str(uuid4())
    issued = await access.signed.issue(access.admin, grant_body(access.target.id), key=key)
    assert issued.status_code == 201, issued.text
    grant_id = issued.json()["resource_id"]
    revoked = await access.signed.revoke(access.admin, grant_id, key=key)
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["resource_id"] == grant_id
    assert revoked.json()["version"] == 2
    rows = await authority_snapshot()
    records = [r for r in rows["authority_idempotency_records"] if str(r["idempotency_key"]) == key]
    assert len(records) == 2
    assert {
        (r["actor_ref"], r["operation"], r["response_resource_version"], r["response_http_status"])
        for r in records
    } == {
        (str(access.admin.id), "admin_role_grant.issue", 1, 201),
        (str(access.admin.id), "admin_role_grant.revoke", 2, 200),
    }
    assert {str(r["response_resource_id"]) for r in records} == {grant_id}
    assert {r["status"] for r in records} == {"committed"}
    for record in records:
        events = [
            e for e in rows["audit_events"] if str(e["idempotency_reference"]) == str(record["id"])
        ]
        event_type = (
            "AdminRoleGrantIssued"
            if record["operation"].endswith("issue")
            else "AdminRoleGrantRevoked"
        )
        success = [e for e in events if e["event_type"] == event_type]
        assert len(success) == 1
        assert success[0]["entity_id"] == grant_id
        assert sum(e["invalidation_cause_event_id"] == success[0]["id"] for e in events) == 1
    grant = next(r for r in rows["admin_role_grants"] if str(r["id"]) == grant_id)
    assert (grant["status"], grant["version"]) == ("revoked", 2)


@pytest.mark.parametrize("operation", ["issue", "revoke"])
async def test_grant_mutation_mismatch_preserves_product_state(
    admin_access: AdminAccess,
    operation: str,
) -> None:
    access = admin_access
    key = str(uuid4())
    if operation == "issue":
        first = await access.signed.issue(access.admin, grant_body(access.target.id), key=key)
    else:
        grant_id = await access.signed.grant(access.admin, access.target)
        first = await access.signed.revoke(access.admin, grant_id, key=key)
    assert first.status_code == (201 if operation == "issue" else 200)
    before = await authority_snapshot()
    if operation == "issue":
        response = await access.signed.issue(
            access.admin,
            grant_body(access.target.id) | {"reason": "Changed request"},
            key=key,
        )
    else:
        response = await access.signed.revoke(
            access.admin,
            first.json()["resource_id"],
            key=key,
            reason="Changed request",
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_mismatch"
    after = await authority_snapshot()
    assert {k: v for k, v in after.items() if k != "audit_events"} == {
        k: v for k, v in before.items() if k != "audit_events"
    }
    prior = {e["id"] for e in before["audit_events"]}
    added = [e for e in after["audit_events"] if e["id"] not in prior]
    assert len(added) == 1
    assert added[0]["event_type"] == "SensitiveAuthorizationDenied"
    assert added[0]["denial_code"] == "idempotency_mismatch"
    assert added[0]["actor_id"] == str(access.admin.id)
    assert added[0]["action_id"] == f"admin_role_grant.{operation}"


async def test_distinct_operation_duplicate_grant_is_conflict(admin_access: AdminAccess) -> None:
    access = admin_access
    await access.signed.grant(access.admin, access.target)
    before = await authority_snapshot()
    response = await access.signed.issue(access.admin, grant_body(access.target.id))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "admin_role_grant_exists"
    after = await authority_snapshot()
    assert after["admin_role_grants"] == before["admin_role_grants"]
    assert after["authority_idempotency_records"] == before["authority_idempotency_records"]
    assert not any(
        e["event_type"] == "AdminRoleGrantIssued" and e not in before["audit_events"]
        for e in after["audit_events"]
    )


@pytest.mark.parametrize("kind", ["service", "suspended", "revoked_link"])
async def test_ineligible_grant_targets_share_missing_response(
    admin_access: AdminAccess,
    kind: str,
) -> None:
    access = admin_access
    target = await seed_read_target(access, kind)
    before = await authority_snapshot()
    absent = await access.signed.issue(access.admin, grant_body(uuid4()))
    ineligible = await access.signed.issue(access.admin, grant_body(target.id))
    assert absent.status_code == ineligible.status_code == 404
    assert concealed_error(absent) == concealed_error(ineligible)
    assert ineligible.json()["error"]["code"] == "actor_not_found"
    error = ineligible.json()
    assert (error["detail"], error["error"]["message"], error["error"]["retryable"]) == (
        "Actor not found",
        "Actor not found",
        False,
    )
    after = await authority_snapshot()
    assert after["authority_control"] == before["authority_control"]
    assert after["admin_role_grants"] == before["admin_role_grants"]
    assert after["authority_idempotency_records"] == before["authority_idempotency_records"]


async def test_self_admin_grant_is_denied_without_grant(admin_access: AdminAccess) -> None:
    access = admin_access
    before = await authority_snapshot()
    response = await access.signed.issue(access.admin, grant_body(access.admin.id))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "self_grant_forbidden"
    after = await authority_snapshot()
    assert after["admin_role_grants"] == before["admin_role_grants"]
    assert after["authority_idempotency_records"] == before["authority_idempotency_records"]


async def test_self_admin_revoke_preserves_grant(admin_access: AdminAccess) -> None:
    access = admin_access
    before = await authority_snapshot()
    response = await access.signed.revoke(access.admin, access.bootstrap_grant_id)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "self_role_revoke_forbidden"
    after = await authority_snapshot()
    assert after["admin_role_grants"] == before["admin_role_grants"]
    assert after["authority_idempotency_records"] == before["authority_idempotency_records"]


async def test_revoked_and_absent_grants_share_concealed_revoke_response(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    grant_id = await access.signed.grant(access.admin, access.target)
    first = await access.signed.revoke(access.admin, grant_id)
    assert first.status_code == 200
    before = await authority_snapshot()
    revoked = await access.signed.revoke(access.admin, grant_id)
    absent = await access.signed.revoke(access.admin, str(uuid4()))
    assert revoked.status_code == absent.status_code == 404
    assert concealed_error(revoked) == concealed_error(absent)
    assert revoked.json()["error"]["code"] == "grant_not_found"
    after = await authority_snapshot()
    assert after["admin_role_grants"] == before["admin_role_grants"]
    assert after["authority_idempotency_records"] == before["authority_idempotency_records"]
    assert [e for e in after["audit_events"] if e["event_type"] == "AdminRoleGrantRevoked"] == [
        e for e in before["audit_events"] if e["event_type"] == "AdminRoleGrantRevoked"
    ]


async def test_target_role_projection_does_not_grant_catalogue_access(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    project = await create_project("Role projection")
    await access.signed.grant(
        access.admin, access.target, role="project_manager", project_id=project
    )
    operator = await access.signed.grant(access.admin, access.target)
    own = await access.signed.client.get("/api/v1/actors/me", headers=access.target.headers)
    assert own.status_code == 200
    assert own.json()["admin_roles"] == ["operator", "project_manager"]
    definitions = await access.signed.client.get(
        "/api/v1/authorization/admin-role-definitions",
        headers=access.target.headers,
    )
    assert definitions.status_code == 403
    assert definitions.json()["error"]["code"] == "permission_not_granted"
    revoked = await access.signed.revoke(access.admin, operator)
    assert revoked.status_code == 200
    own = await access.signed.client.get("/api/v1/actors/me", headers=access.target.headers)
    assert own.status_code == 200
    assert own.json()["admin_roles"] == ["project_manager"]
