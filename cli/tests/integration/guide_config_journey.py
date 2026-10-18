"""Guide configuration through the real public socket and PostgreSQL owners."""

import json
from uuid import uuid4


async def exercise_guide_configuration(
    direct, cli, origin, tokens, project_id, guide_id, foreign_id, tmp_path
):
    specification = (await direct.get("/openapi.json", timeout=60)).json()
    prefix = "/api/v1/projects/{project_id}/guides/{guide_id}"
    assert "patch" in specification["paths"][prefix]
    assert "put" in specification["paths"][prefix + "/review-policy"]
    assert "put" in specification["paths"][prefix + "/revision-policy"]

    token = tokens["cli-project-manager"]
    caller = {"Authorization": "Bearer " + token}
    path = tmp_path / "guide-configuration.json"
    root = f"/api/v1/projects/{project_id}/guides/{guide_id}"

    def write(action, body, key, *, match=None, presented=token, project=project_id):
        path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        command = [
            "-o",
            "json",
            "project",
            "guide",
            action,
            project,
            guide_id,
            "--input",
            str(path),
            "--idempotency-key",
            key,
        ]
        if match is not None:
            command += ["--if-match", match]
        return cli(origin, presented, *command)

    def success(result):
        assert result.returncode == 0 and result.stderr == "", result.stderr
        return json.loads(result.stdout)

    def denied(result, status, code=None):
        assert result.returncode == 1 and result.stdout == "", result.stderr
        error = json.loads(result.stderr)["error"]
        statuses = status if isinstance(status, tuple) else (status,)
        assert error["status"] in statuses and not error.get("outcome_unknown", False)
        if code:
            assert error["code"] == code

    edit_body = {"change_summary": "Configured é\n"}
    review_body = {
        "review_preference_window_seconds": 3600,
        "review_lease_duration_seconds": 1800,
        "human_review_required": False,
        "minimum_finding_fields": ["issue", "required_fix"],
    }
    revision_body = {
        "max_revision_rounds": 7,
        "revision_deadline_hours": 48,
        "reviewer_reassignment_rule": None,
    }
    for action, body, match in (
        ("edit", edit_body, None),
        ("set-review-policy", review_body, '"no-current-policy"'),
        ("set-revision-policy", revision_body, '"no-current-policy"'),
    ):
        denied(
            write(
                action,
                body,
                str(uuid4()),
                match=match,
                presented=tokens["cli-outsider"],
            ),
            (403, 404),
        )
        denied(write(action, body, str(uuid4()), match=match, project=foreign_id), 404)

    edit_key = str(uuid4())
    edited = success(write("edit", edit_body, edit_key))
    assert edited["id"] == guide_id and edited["project_id"] == project_id
    assert (
        edited["status"] == "draft"
        and edited["change_summary"] == edit_body["change_summary"]
    )
    assert success(write("edit", edit_body, edit_key)) == edited
    denied(
        write("edit", {"change_summary": "Different"}, edit_key),
        409,
        "idempotency_mismatch",
    )
    cleared = success(write("edit", {"change_summary": None}, str(uuid4())))
    assert cleared["change_summary"] is None
    omitted = success(write("edit", {}, str(uuid4())))
    assert omitted["change_summary"] is None

    first_key = str(uuid4())
    first = success(
        write("set-review-policy", review_body, first_key, match='"no-current-policy"')
    )
    assert first["project_id"] == project_id and first["policy_generation"] == 1
    assert (
        first["human_review_required"] is False
        and first["supersedes_policy_id"] is None
    )
    selected = await direct.get(root, headers=caller)
    assert selected.status_code == 200, selected.text
    assert selected.json()["review_policy"]["policy_id"] == first["id"]
    assert selected.json()["review_policy"]["human_review_required"] is False
    denied(
        write(
            "set-review-policy", review_body, str(uuid4()), match='"no-current-policy"'
        ),
        409,
        "policy_precondition_failed",
    )
    denied(
        write(
            "set-review-policy",
            review_body | {"human_review_required": True},
            first_key,
            match='"no-current-policy"',
        ),
        409,
        "idempotency_mismatch",
    )
    selector = f'"{first["id"]}.{first["policy_generation"]}.{first["policy_hash"].removeprefix("sha256:")}"'
    successor_body = {
        "review_preference_window_seconds": 7200,
        "review_lease_duration_seconds": 2400,
        # Omission carries the prior false mode; CLI must not fill a default true.
    }
    successor = success(
        write("set-review-policy", successor_body, str(uuid4()), match=selector)
    )
    assert successor["policy_generation"] == 2
    assert successor["supersedes_policy_id"] == first["id"]
    assert successor["human_review_required"] is False
    assert (
        success(
            write(
                "set-review-policy", review_body, first_key, match='"no-current-policy"'
            )
        )
        == first
    )

    revision_key = str(uuid4())
    revision = success(
        write(
            "set-revision-policy",
            revision_body,
            revision_key,
            match='"no-current-policy"',
        )
    )
    assert revision["project_id"] == project_id
    assert revision["policy_generation"] == 1
    assert revision["reviewer_reassignment_rule"] is None
    denied(
        write(
            "set-revision-policy",
            revision_body | {"max_revision_rounds": 8},
            revision_key,
            match='"no-current-policy"',
        ),
        409,
        "idempotency_mismatch",
    )
    denied(
        write(
            "set-revision-policy",
            revision_body,
            str(uuid4()),
            match='"no-current-policy"',
        ),
        409,
        "policy_precondition_failed",
    )
    selected = await direct.get(root, headers=caller)
    assert selected.status_code == 200, selected.text
    assert selected.json()["review_policy"]["policy_id"] == successor["id"]
    assert selected.json()["revision_policy"]["policy_id"] == revision["id"]
    assert selected.json()["guide"]["change_summary"] is None

    # The parent journey revokes its exact manager grant immediately afterward.
    # Retain exact committed requests so that revoked-grant replay is separately
    # distinguished from fresh-key denial at the public API boundary.
    successor_selector = f'"{successor["id"]}.{successor["policy_generation"]}.{successor["policy_hash"].removeprefix("sha256:")}"'
    revision_selector = f'"{revision["id"]}.{revision["policy_generation"]}.{revision["policy_hash"].removeprefix("sha256:")}"'
    return (
        write,
        denied,
        (
            ("edit", edit_body, edit_key, None, None),
            (
                "set-review-policy",
                review_body,
                first_key,
                '"no-current-policy"',
                successor_selector,
            ),
            (
                "set-revision-policy",
                revision_body,
                revision_key,
                '"no-current-policy"',
                revision_selector,
            ),
        ),
    )
