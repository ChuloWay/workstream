"""Bootstrap and signed-token authority at the real persistence boundary."""

from scripts.bootstrap_access_administrator import _run as run_bootstrap
from tests.authorization.admin_access.support import (
    AdminAccess,
    SignedAccess,
    actor_observation,
    authority_events,
    authority_snapshot,
)


async def test_token_role_cannot_read_authorization_catalogue(signed_access: SignedAccess) -> None:
    actor = await signed_access.actor("untrusted-admin-role", roles=("admin",))
    before = await authority_snapshot()
    response = await signed_access.client.get(
        "/api/v1/authorization/permissions", headers=actor.headers
    )
    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "permission_not_granted"
    after = await authority_snapshot()
    assert {k: v for k, v in after.items() if k != "audit_events"} == {
        k: v for k, v in before.items() if k != "audit_events"
    }
    assert (
        await authority_events(
            action="authorization.permission_catalogue.read",
            event_type="SensitiveAuthorizationAllowed",
        )
        == []
    )


async def test_bootstrap_dry_run_leaves_control_grants_and_events_unchanged(
    signed_access: SignedAccess,
) -> None:
    actor = await signed_access.actor("bootstrap-candidate")
    before = await authority_snapshot()
    observed = await actor_observation(actor.id)
    code, result = await run_bootstrap(actor.id, execute=False)
    assert code == 0
    assert result == {
        "result_code": "eligible",
        "actor_profile_id": str(actor.id),
        "would_change": True,
    }
    assert await authority_snapshot() == before
    assert await actor_observation(actor.id) == observed


async def test_later_bootstrap_returns_audited_original_grant_conflict(
    admin_access: AdminAccess,
) -> None:
    access = admin_access
    before = await authority_snapshot()
    code, result = await run_bootstrap(access.target.id, execute=True)
    assert code == 3
    assert result == {
        "result_code": "admin_role_grant_exists",
        "actor_profile_id": str(access.target.id),
        "grant_id": access.bootstrap_grant_id,
        "changed": False,
    }
    after = await authority_snapshot()
    assert {k: v for k, v in after.items() if k != "audit_events"} == {
        k: v for k, v in before.items() if k != "audit_events"
    }
    before_ids = {row["id"] for row in before["audit_events"]}
    added = [row for row in after["audit_events"] if row["id"] not in before_ids]
    assert len(added) == 1
    event = added[0]
    assert event["event_type"] == "AdminRoleGrantIssueDenied"
    assert event["actor_id"] == "workstream:system:bootstrap"
    assert event["entity_id"] == access.bootstrap_grant_id
    assert event["target_actor_ref"] == str(access.target.id)
    assert event["denial_code"] == "admin_role_grant_exists"
    assert len(await authority_events(event_type="InitialAccessAdministratorBootstrapped")) == 1
