"""Each fresh caller's disclosure serializes with its disabling transition."""

import pytest

from tests.authorization.admin_access.concurrency_support import read_against_transition
from tests.authorization.admin_access.read_support import READ_ACTIONS, read_path
from tests.authorization.admin_access.support import (
    AdminAccess,
    actor_observation,
    authority_events,
)


@pytest.mark.parametrize("surface", ["profile", "link"])
@pytest.mark.parametrize(
    "transition", ["suspended", "deactivated", "link_revoked", "grant_revoked"]
)
async def test_admin_read_blocks_exact_authority_transition(
    admin_access: AdminAccess,
    auth_database_env: str,
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
    transition: str,
) -> None:
    access = admin_access
    reader = await access.signed.actor("disclosure-reader")
    grant_id = await access.signed.grant(access.admin, reader, role="access_administrator")
    response, changed, custody = await read_against_transition(
        access,
        reader,
        grant_id,
        surface,
        transition,
        database_url=auth_database_env,
        monkeypatch=monkeypatch,
    )
    assert custody.observed
    assert response.status_code == 200, response.text
    assert response.json()["actor_profile_id"] == str(access.target.id)
    if transition == "grant_revoked":
        assert changed.status_code == 200, changed.text
    observed = await actor_observation(reader.id)
    action, _ = READ_ACTIONS[surface]
    events = await authority_events(action=action, event_type="SensitiveAuthorizationAllowed")
    assert len(events) == 1
    assert events[0].actor_id == str(reader.id)
    assert events[0].matched_grant_id == grant_id
    denied = await access.signed.client.get(
        read_path(access.target.id, surface), headers=reader.headers
    )
    assert denied.status_code == 403
    assert await actor_observation(reader.id) == observed
    after_events = await authority_events(action=action, event_type="SensitiveAuthorizationAllowed")
    assert [e.id for e in after_events] == [e.id for e in events]
