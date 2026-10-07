"""Public creation and replay on the existing isolated real API journey."""

from __future__ import annotations

import json
from uuid import uuid4


async def exercise_project_creation(direct, cli, origin, tokens, profiles, project_id):
    admin_headers = {"Authorization": f"Bearer {tokens['cli-admin']}"}
    manager_headers = {"Authorization": f"Bearer {tokens['cli-manager']}"}
    actor = profiles["cli-project-manager"]["actor_profile_id"]
    token = tokens["cli-project-manager"]
    body = {"name": "CLI project é", "slug": f"cli-created-{uuid4().hex}"}
    key = str(uuid4())

    def create(caller, fields, replay_key):
        flags = ["--name", fields["name"], "--slug", fields["slug"]]
        if "description" in fields:
            flags += ["--description", fields["description"]]
        return cli(
            origin,
            caller,
            "-o",
            "json",
            "project",
            "create",
            "--idempotency-key",
            replay_key,
            *flags,
        )

    def denied(result, status, code=None):
        assert result.returncode == 1 and result.stdout == "", result.stderr
        error = json.loads(result.stderr)["error"]
        assert error["status"] == status and "outcome_unknown" not in error
        if code is not None:
            assert error["code"] == code

    async def grant(scope):
        payload = {
            "target_actor_profile_id": actor,
            "role": "project_manager",
            "scope_type": scope,
            "reason": "CLI creation requires system authority, not project scope",
        }
        if scope == "project":
            payload["scope_project_id"] = project_id
        result = await direct.post(
            "/api/v1/admin-role-grants",
            headers=admin_headers | {"Idempotency-Key": str(uuid4())},
            json=payload,
        )
        assert result.status_code == 201, result.text
        return result.json()["resource_id"]

    async def revoke(grant_id):
        result = await direct.post(
            f"/api/v1/admin-role-grants/{grant_id}/revoke",
            headers=admin_headers | {"Idempotency-Key": str(uuid4())},
            json={"reason": "CLI creation authority proof and fixture restoration"},
        )
        assert result.status_code == 200, result.text

    async def lifecycle(transition):
        result = await direct.post(
            f"/api/v1/actors/{actor}/{transition}",
            headers=admin_headers | {"Idempotency-Key": str(uuid4())},
            json={"reason": "CLI creation lifecycle proof with active system grant"},
        )
        assert result.status_code == 200, result.text

    # Neither first admission nor the access-admin trust root creates projects.
    for caller in (tokens["cli-outsider"], tokens["cli-admin"], token):
        denied(create(caller, body, str(uuid4())), 403)
    scoped_grant = await grant("project")
    denied(create(token, body, str(uuid4())), 403)
    system_grant = await grant("system")

    result = create(token, body, key.replace("-", ""))
    assert result.returncode == 0 and result.stderr == "", result.stderr
    created = json.loads(result.stdout)
    assert set(created) == {
        "id",
        "name",
        "slug",
        "description",
        "status",
        "created_at",
        "updated_at",
    }
    assert created["name"] == body["name"] and created["slug"] == body["slug"]
    assert created["status"] == "draft" and created["description"] is None
    saved = await direct.get(
        f"/api/v1/projects/{created['id']}", headers=manager_headers
    )
    assert saved.status_code == 200 and saved.json() == created
    # Compare to direct POST recovery as well as the persisted GET projection.
    expected = await direct.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key},
        json=body,
    )
    assert expected.status_code == 201 and expected.json() == created
    replay = create(token, body, key)
    assert replay.returncode == 0 and json.loads(replay.stdout) == created
    denied(create(token, body | {"description": ""}, key), 409, "idempotency_mismatch")
    denied(
        create(token, body | {"name": "Must not overwrite"}, str(uuid4())),
        409,
        "project_slug_conflict",
    )
    unchanged = await direct.get(
        f"/api/v1/projects/{created['id']}", headers=manager_headers
    )
    assert unchanged.status_code == 200 and unchanged.json() == created

    await revoke(system_grant)
    # Existing ProjectCreateService recovers committed writes before fresh PREP.
    # TASK replay has different current-authority semantics; don't copy them here.
    replay = create(token, body, key)
    assert replay.returncode == 0 and json.loads(replay.stdout) == created
    denied(
        create(token, body | {"slug": f"cli-revoked-{uuid4().hex}"}, str(uuid4())), 403
    )

    system_grant = await grant("system")
    complete = body | {
        "slug": f"cli-described-{uuid4().hex}",
        "description": "Full description é\n",
    }
    positive = create(token, complete, str(uuid4()))
    assert positive.returncode == 0 and positive.stderr == "", positive.stderr
    second = json.loads(positive.stdout)
    assert second["id"] != created["id"]
    assert all(second[field] == value for field, value in complete.items())
    saved = await direct.get(
        f"/api/v1/projects/{second['id']}", headers=manager_headers
    )
    assert saved.status_code == 200 and saved.json() == second
    await lifecycle("suspend")
    # Profile reads and creation PREP expose different canonical denial codes.
    denied(cli(origin, token, "-o", "json", "whoami"), 403, "actor_suspended")
    denied(
        create(token, body | {"slug": f"cli-suspended-{uuid4().hex}"}, str(uuid4())),
        403,
        "permission_not_granted",
    )
    # Preserve the original manager/task fixture's active, ungranted baseline.
    await lifecycle("reactivate")
    await revoke(system_grant)
    await revoke(scoped_grant)
