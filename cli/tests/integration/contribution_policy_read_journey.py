"""CLI Finance reads inside the retained real public guide-activation journey."""

import json
from uuid import uuid4

from sqlalchemy import text

from tests.contributions.public_policy.support import UNPAID


async def publish_with_policy_reads(
    direct,
    cli,
    origin,
    factory,
    project,
    foreign_project,
    finance_token,
    finance_id,
    finance_grant,
    manager_token,
    other_token,
    foreign_finance_token,
    admin,
):
    root = f"/api/v1/projects/{project}/contribution-policies"
    finance = {"Authorization": "Bearer " + finance_token}
    tables = (
        "contribution_policies",
        "contribution_policy_versions",
        "contribution_rules",
        "contribution_award_definitions",
        "project_compensation_units",
        "iso_4217_currency_codes",
        "contribution_policy_transition_custody",
        "contribution_policy_lifecycle_events",
        "project_guides",
        "projects",
    )

    async def stored():
        async with factory() as session:
            return {
                table: [
                    dict(row)
                    for row in (
                        await session.execute(text(f"SELECT * FROM {table} ORDER BY 1"))
                    ).mappings()
                ]
                for table in tables
            }

    async def write(method, path, body, headers=finance):
        response = await direct.request(
            method, path, headers=headers | {"Idempotency-Key": str(uuid4())}, json=body
        )
        assert response.status_code in (200, 201), response.text
        return response.json()

    def call(
        action,
        *,
        policy=None,
        version=None,
        selected_project=project,
        token=finance_token,
        status=None,
    ):
        args = (str(selected_project).replace("-", ""),)
        if action == "show":
            args += (str(policy).replace("-", ""),)
        if version is not None:
            args += ("--version", str(version).replace("-", ""))
        result = cli(
            origin, token, "project", "contribution-policy", action, *args, "-o", "json"
        )
        if status is not None:
            assert result.returncode == 1 and result.stdout == "", result.stderr
            error = json.loads(result.stderr)["error"]
            assert error["status"] == status and "outcome_unknown" not in error, error
            if status == 404:
                assert error["code"] == "contribution_policy_not_found"
            return error
        assert result.returncode == 0 and result.stderr == "", result.stderr
        return json.loads(result.stdout)

    async def inspect(
        receipt, published_id, draft_id, *, explicit=None, expected_status=None
    ):
        before = await stored()
        current = call("current")
        assert current == {
            "project_id": str(project),
            "contribution_policy_id": receipt["contribution_policy_id"],
            "current_published_version_id": published_id,
            "open_draft_version_id": draft_id,
        }
        expected = await direct.get(root + "/current", headers=finance)
        assert expected.status_code == 200 and current == expected.json()
        viewed = call(
            "show", policy=receipt["contribution_policy_id"], version=explicit
        )
        expected = await direct.get(
            root + "/" + receipt["contribution_policy_id"],
            headers=finance,
            params={} if explicit is None else {"version_id": explicit},
        )
        assert expected.status_code == 200 and viewed == expected.json()
        if explicit is not None:
            assert viewed["contribution_policy_version_id"] == explicit
        if expected_status is not None:
            assert viewed["version_status"] == expected_status
        assert (
            await stored() == before
        )  # AUTH read evidence is intentionally outside these tables.
        return viewed

    spec = (await direct.get("/openapi.json")).json()["paths"]
    for route in (
        "/api/v1/projects/{project_id}/contribution-policies/current",
        "/api/v1/projects/{project_id}/contribution-policies/{policy_id}",
    ):
        assert (
            spec[route]["get"]["x-workstream-action-id"] == "contribution.policy.read"
        )
    first = await write("POST", root + "/drafts", {"name": "Governed project policy"})
    first_id = first["contribution_policy_version_id"]
    version_path = root + f"/{first['contribution_policy_id']}/versions/{first_id}"
    empty = await inspect(
        first, None, first_id, explicit=first_id, expected_status="draft"
    )
    assert empty["rules"] == [] and empty["version_number"] == 1
    await write("PUT", version_path, UNPAID)
    published = await write("POST", version_path + "/publication", {})
    view = await inspect(first, first_id, None, expected_status="published")
    assert {rule["contribution_type"] for rule in view["rules"]} == {
        "accepted_submission",
        "completed_review",
    }
    assert all(
        rule["compensation_mode"] == "unpaid" and rule["definitions"] == []
        for rule in view["rules"]
    )
    successor = await write(
        "POST", root + "/drafts", {"name": "Governed project policy"}
    )
    next_id = successor["contribution_policy_version_id"]
    default = await inspect(first, first_id, next_id, expected_status="published")
    assert default["contribution_policy_version_id"] == first_id
    next_view = await inspect(
        first, first_id, next_id, explicit=next_id, expected_status="draft"
    )
    assert next_view["rules"] == [] and next_view["version_number"] == 2
    version_path = root + f"/{first['contribution_policy_id']}/versions/{next_id}"
    await write("PUT", version_path, UNPAID)
    published = await write("POST", version_path + "/publication", {})
    old = await inspect(
        first, next_id, None, explicit=first_id, expected_status="retired"
    )
    assert old["policy_status"] == "active" and old["rules"] == view["rules"]
    await inspect(first, next_id, None, expected_status="published")

    # Stored foreign aggregate/version, created by real foreign-project Finance.
    foreign = await write(
        "POST",
        f"/api/v1/projects/{foreign_project}/contribution-policies/drafts",
        {"name": "Foreign policy"},
        {"Authorization": "Bearer " + foreign_finance_token},
    )
    before = await stored()
    for presented in (manager_token, other_token, foreign_finance_token):
        call("current", token=presented, status=404)
        call(
            "show",
            policy=first["contribution_policy_id"],
            version=next_id,
            token=presented,
            status=404,
        )
    call(
        "show",
        policy=foreign["contribution_policy_id"],
        version=foreign["contribution_policy_version_id"],
        status=404,
    )
    call(
        "show",
        policy=first["contribution_policy_id"],
        version=foreign["contribution_policy_version_id"],
        status=404,
    )
    call("current", selected_project=foreign_project, status=404)
    call(
        "show",
        selected_project=foreign_project,
        policy=foreign["contribution_policy_id"],
        status=404,
    )
    call("current", token="invalid-token", status=401)
    assert await stored() == before

    async def denied():
        before = await stored()
        call("current", status=404)
        call(
            "show", policy=first["contribution_policy_id"], version=next_id, status=404
        )
        assert await stored() == before

    await write(
        "POST",
        f"/api/v1/actors/{finance_id}/suspend",
        {"reason": "Finance read admission proof"},
        admin,
    )
    await denied()
    await write(
        "POST",
        f"/api/v1/actors/{finance_id}/reactivate",
        {"reason": "Restore Finance read admission"},
        admin,
    )
    await inspect(first, next_id, None, expected_status="published")
    await write(
        "POST",
        f"/api/v1/admin-role-grants/{finance_grant}/revoke",
        {"reason": "Finance read current authority proof"},
        admin,
    )
    await denied()
    await write(
        "POST",
        "/api/v1/admin-role-grants",
        {
            "target_actor_profile_id": str(finance_id),
            "role": "finance_authority",
            "scope_type": "project",
            "scope_project_id": str(project),
            "reason": "Restore exact-project Finance authority",
        },
        admin,
    )
    await inspect(first, next_id, None, expected_status="published")

    async def inspect_retired():
        before = await stored()
        historical = call(
            "show", policy=first["contribution_policy_id"], version=next_id
        )
        expected = await direct.get(
            root + "/" + first["contribution_policy_id"],
            headers=finance,
            params={"version_id": next_id},
        )
        assert expected.status_code == 200 and historical == expected.json()
        assert (historical["policy_status"], historical["version_status"]) == (
            "retired",
            "retired",
        )
        call("current", status=404)
        assert await stored() == before

    return published, version_path, inspect_retired
