"""Real public contributor reads over canonical approved-guide prerequisites.

Only upstream guide inference/storage are scripted fixtures. Task, assignment,
grant and lifecycle operations exercise the real API with no route overrides.
"""

from contextlib import AsyncExitStack
import json
from uuid import uuid4

from api_contract_e2e import flow_settings, issue_flow_token
from tests.projects.guide_activation.pg_support import activation_case
from tests.authorization.guide_activation.pg_support import activate


async def exercise_contributor_task_reads(
    direct, cli, origin, tokens, profiles, env, qualification
):
    manager = {"Authorization": f"Bearer {tokens['cli-manager']}"}
    admin = {"Authorization": f"Bearer {tokens['cli-admin']}"}
    token = tokens["cli-outsider"]
    issuer, audience, secret = flow_settings(env)

    async def post(path, body, headers=manager):
        response = await direct.post(
            path, headers=headers | {"Idempotency-Key": str(uuid4())}, json=body
        )
        assert response.status_code in (200, 201), response.text
        return response.json()

    def read(command, presented=token, status=None):
        result = cli(origin, presented, "task", *command, "-o", "json")
        if status is not None:
            assert result.returncode == 1 and result.stdout == "", result.stderr
            assert json.loads(result.stderr)["error"]["status"] == status
            return None
        assert result.returncode == 0 and result.stderr == "", result.stderr
        return json.loads(result.stdout)

    async def grant(project, actor, role="submitter"):
        return await post(
            f"/api/v1/projects/{project}/role-grants",
            {
                "target_actor_profile_id": actor,
                "role": role,
                "qualification": qualification,
                "reason": "CLI contributor read proof",
            },
        )

    peer_profiles = {}
    peer_tokens = {}
    for name in ("cli-task-peer", "cli-task-reviewer"):
        peer_tokens[name] = issue_flow_token(
            name, [], issuer=issuer, audience=audience, secret=secret
        )
        admitted = await direct.get(
            "/api/v1/actors/me",
            headers={"Authorization": f"Bearer {peer_tokens[name]}"},
        )
        assert admitted.status_code == 200, admitted.text
        peer_profiles[name] = admitted.json()["actor_profile_id"]

    async with AsyncExitStack() as stack:
        projects = []
        for _ in range(2):
            factory, command, actor, *_rest = await stack.enter_async_context(
                activation_case(env["WORKSTREAM_DATABASE_URL"])
            )
            await activate(factory, actor, command)
            projects.append(str(command.target.proposal.project_id))
        project, foreign_project = projects
        ready_ids = []
        for selected_project, count in ((project, 3), (foreign_project, 1)):
            for index in range(count):
                created = await post(
                    f"/api/v1/projects/{selected_project}/tasks",
                    {
                        "title": f"Contributor work {index}",
                        "description": "Inspect the supplied evidence.",
                        "task_type": "evaluation",
                        "difficulty": "medium",
                        "skill_tags": ["analysis"],
                        "estimated_time_minutes": 17,
                        "acceptance_criteria": "Evidence is complete.",
                        "rejection_criteria": "Evidence is missing.",
                        "source_ref": "manager-private-source",
                    },
                )
                task_id = created["id"]
                for operation in ("screen", "release"):
                    transitioned = await post(
                        f"/api/v1/tasks/{task_id}/{operation}",
                        {"reason": "Prepare contributor discovery"},
                    )
                assert transitioned["status"] == "ready"
                if selected_project == project:
                    ready_ids.append(task_id)
                else:
                    foreign_task_id = task_id
        draft = await post(
            f"/api/v1/projects/{project}/tasks",
            {"title": "Not released", "description": "Draft control"},
        )
        actor_id = profiles["cli-outsider"]["actor_profile_id"]

        # Stored ready resources exist, but no matching grant permits either read.
        read(("ready", project), status=404)
        read(("show", ready_ids[0]), status=404)
        first_grant = await grant(project, actor_id)
        await grant(project, peer_profiles["cli-task-peer"])
        await grant(project, peer_profiles["cli-task-reviewer"], role="reviewer")
        for command in (("ready", project), ("show", ready_ids[0])):
            read(command, peer_tokens["cli-task-reviewer"], status=404)

        cursor = None
        observed = []
        first_cursor = None
        for index in range(3):
            flags = () if cursor is None else ("--cursor", cursor)
            page = read(("ready", project.replace("-", ""), "--limit", "1", *flags))
            params = {"limit": "1"} | ({} if cursor is None else {"cursor": cursor})
            expected = await direct.get(
                f"/api/v1/projects/{project}/tasks/ready",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            assert expected.status_code == 200 and page == expected.json()
            assert len(page["items"]) == 1
            assert set(page["items"][0]) == {
                "task_id",
                "project_id",
                "title",
                "task_type",
                "difficulty",
                "skill_tags",
                "estimated_time_minutes",
                "created_at",
            }
            observed.append(page["items"][0]["task_id"])
            cursor = page["next_cursor"]
            if index == 0:
                first_cursor = cursor
                assert first_cursor is not None
        assert observed == ready_ids and cursor is None and draft["id"] not in observed

        async def detail(task_id, presented=token):
            value = read(("show", task_id.replace("-", "")), presented)
            expected = await direct.get(
                f"/api/v1/tasks/{task_id}",
                headers={"Authorization": f"Bearer {presented}"},
            )
            assert expected.status_code == 200 and value == expected.json()
            assert value["task_id"] == task_id and value["project_id"] == project
            assert (
                "source_ref" not in value
                and "assigned_to" not in value
                and "created_by" not in value
            )
            return value

        await detail(ready_ids[0])
        await detail(ready_ids[0], peer_tokens["cli-task-peer"])
        read(("show", draft["id"]), status=404)
        read(("ready", foreign_project), status=404)
        read(("show", foreign_task_id), status=404)
        # Each cursor substitution retains authority before testing the codec.
        await grant(foreign_project, actor_id)
        read(("ready", foreign_project))
        read(("show", foreign_task_id))
        read(
            ("ready", foreign_project, "--limit", "1", "--cursor", first_cursor),
            status=422,
        )
        read(("ready", project, "--limit", "2", "--cursor", first_cursor), status=422)
        await post(
            "/api/v1/admin-role-grants",
            {
                "target_actor_profile_id": actor_id,
                "role": "project_manager",
                "scope_type": "project",
                "scope_project_id": project,
                "reason": "Independent authorized cursor action control",
            },
            admin,
        )
        management_control = cli(
            origin, token, "project", "tasks", project, "--limit", "1", "-o", "json"
        )
        assert management_control.returncode == 0 and management_control.stderr == ""
        assert (
            json.loads(management_control.stdout)["items"][0]["task_id"] == ready_ids[0]
        )
        management = cli(
            origin,
            token,
            "project",
            "tasks",
            project,
            "--limit",
            "1",
            "--cursor",
            first_cursor,
            "-o",
            "json",
        )
        assert management.returncode == 1 and management.stdout == ""
        assert json.loads(management.stderr)["error"]["status"] == 422

        claimed = await post(
            f"/api/v1/tasks/{ready_ids[0]}/claim",
            {"reason": "Assignment visibility control"},
            {"Authorization": f"Bearer {token}"},
        )
        assert claimed["assignment"]["contributor_id"] == actor_id
        assert (await detail(ready_ids[0]))["status"] == "claimed"
        # Same-project authority was demonstrated before and after this ownership change.
        read(("show", ready_ids[0]), peer_tokens["cli-task-peer"], status=404)
        await detail(ready_ids[1], peer_tokens["cli-task-peer"])
        for presented in (token, peer_tokens["cli-task-peer"]):
            page = read(("ready", project), presented)
            assert {item["task_id"] for item in page["items"]} == set(ready_ids[1:])

        await post(
            f"/api/v1/projects/{project}/role-grants/{first_grant['id']}/revoke",
            {"reason": "Discovery must reauthorize"},
        )
        read(("ready", project, "--limit", "1", "--cursor", first_cursor), status=404)
        read(("show", ready_ids[1]), status=404)
        # Manager authority cannot substitute for a revoked Submitter grant.
        await grant(project, actor_id)
        read(("ready", project, "--limit", "1", "--cursor", first_cursor))
        await detail(ready_ids[1])
        # The same freshly authorized actor is suspended: stale revocation cannot
        # masquerade as lifecycle denial. Restore it for the outer journey.
        await post(
            f"/api/v1/actors/{actor_id}/suspend",
            {"reason": "CLI live contributor lifecycle control"},
            admin,
        )
        read(("ready", project), status=404)
        read(("show", ready_ids[1]), status=404)
        await post(
            f"/api/v1/actors/{actor_id}/reactivate",
            {"reason": "Continue independent CLI proof"},
            admin,
        )
        read(("ready", project))
        await detail(ready_ids[1])
