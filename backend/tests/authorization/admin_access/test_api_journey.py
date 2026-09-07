"""One connected signed API journey, not every validation variation."""

from scripts.bootstrap_access_administrator import _run as run_bootstrap
from tests.authorization.admin_access.support import SignedAccess


async def test_signed_admin_grant_journey(signed_access: SignedAccess) -> None:
    admin = await signed_access.actor("administrator", roles=("viewer",))
    target = await signed_access.actor("target", roles=("admin",))
    code, bootstrap = await run_bootstrap(admin.id, execute=True)
    assert code == 0, bootstrap
    grant_id = await signed_access.grant(admin, target)
    assigned = await signed_access.client.get("/api/v1/actors/me", headers=target.headers)
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["admin_roles"] == ["operator"]
    revoked = await signed_access.revoke(admin, grant_id)
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["version"] == 2
    observed = await signed_access.client.get("/api/v1/actors/me", headers=target.headers)
    assert observed.status_code == 200, observed.text
    assert observed.json()["admin_roles"] == []
