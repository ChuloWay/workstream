"""Real public candidate reads inside the existing project-role API journey."""

import json

from sqlalchemy import text


def candidate_read(cli, origin, token, project, *flags, status=None):
    result = cli(
        origin,
        token,
        "project",
        "role-grant",
        "candidates",
        project.replace("-", ""),
        *flags,
        "-o",
        "json",
    )
    if status is not None:
        assert result.returncode == 1 and result.stdout == "", result.stderr
        error = json.loads(result.stderr)["error"]
        assert error["status"] == status and "outcome_unknown" not in error
        return error
    assert result.returncode == 0 and result.stderr == "", result.stderr
    return json.loads(result.stdout)


async def inspect_contributor_candidates(
    direct,
    cli,
    origin,
    scoped_token,
    system_manager_token,
    contributor_token,
    project,
    foreign_project,
    manager_id,
    target_id,
    factory,
):
    path = f"/api/v1/projects/{project}/contributor-candidates"
    routes = (await direct.get("/openapi.json")).json()["paths"]
    assert (
        routes["/api/v1/projects/{project_id}/contributor-candidates"]["get"][
            "x-workstream-action-id"
        ]
        == "project.contributor_candidate.list"
    )

    # Keep a narrow read-only state check; candidate discovery must not insert
    # qualification snapshots or project grants.
    async with factory() as session:
        before = (
            (
                await session.execute(text("SELECT count(*) FROM project_role_grants"))
            ).scalar_one(),
            (
                await session.execute(
                    text("SELECT count(*) FROM project_role_qualification_snapshots")
                )
            ).scalar_one(),
        )

    headers = {"Authorization": "Bearer " + scoped_token}
    expected = await direct.get(path, headers=headers)
    assert expected.status_code == 200, expected.text
    observed = candidate_read(cli, origin, scoped_token, project)
    assert observed == expected.json()
    ids = [row["actor_profile_id"] for row in observed["items"]]
    assert target_id in ids and manager_id not in ids
    assert all(
        set(row) == {"actor_profile_id", "display_name"} for row in observed["items"]
    )
    assert observed["next_cursor"] is None

    first = candidate_read(cli, origin, scoped_token, project, "--limit", "1")
    direct_first = await direct.get(path, headers=headers, params={"limit": 1})
    assert direct_first.status_code == 200 and first == direct_first.json()
    cursor = first["next_cursor"]
    assert len(first["items"]) == 1 and cursor
    continued = candidate_read(
        cli, origin, scoped_token, project, "--limit", "1", "--cursor", cursor
    )
    direct_next = await direct.get(
        path, headers=headers, params={"limit": 1, "cursor": cursor}
    )
    assert direct_next.status_code == 200 and continued == direct_next.json()
    assert (
        continued["items"][0]["actor_profile_id"]
        != first["items"][0]["actor_profile_id"]
    )

    for selected_project, token, flags, status, code in (
        (
            project,
            scoped_token,
            ("--limit", "2", "--cursor", cursor),
            400,
            "invalid_cursor",
        ),
        (
            foreign_project,
            system_manager_token,
            ("--limit", "1", "--cursor", cursor),
            400,
            "invalid_cursor",
        ),
        (
            foreign_project,
            scoped_token,
            (),
            404,
            "project_authorization_resource_not_found",
        ),
        (
            project,
            contributor_token,
            (),
            404,
            "project_authorization_resource_not_found",
        ),
    ):
        denied = candidate_read(
            cli, origin, token, selected_project, *flags, status=status
        )
        expected_denial = await direct.get(
            f"/api/v1/projects/{selected_project}/contributor-candidates",
            headers={"Authorization": "Bearer " + token},
            params={
                "limit": 2 if flags and flags[1] == "2" else 1,
                **({"cursor": cursor} if "--cursor" in flags else {}),
            }
            if flags
            else None,
        )
        assert expected_denial.status_code == status
        assert denied["code"] == expected_denial.json()["error"]["code"] == code

    async with factory() as session:
        after = (
            (
                await session.execute(text("SELECT count(*) FROM project_role_grants"))
            ).scalar_one(),
            (
                await session.execute(
                    text("SELECT count(*) FROM project_role_qualification_snapshots")
                )
            ).scalar_one(),
        )
    assert after == before
    return cursor


def deny_contributor_candidates(cli, origin, token, project, cursor):
    for flags in ((), ("--limit", "1", "--cursor", cursor)):
        error = candidate_read(cli, origin, token, project, *flags, status=404)
        assert error["code"] == "project_authorization_resource_not_found"
