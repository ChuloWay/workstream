"""Process-level contracts for explicit AUTH project-role decisions."""

from copy import deepcopy
import json
from urllib.parse import quote

from http2_fixture import goaway_fixture
from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture
from test_contributor_task_mutations import KEY, POLICY, canonical_error

QUALIFICATION = {
    "skills_snapshot": {
        "availability": "available",
        "reference_ids": ["skill:analysis"],
        "unavailable_reason": None,
    },
    "reputation_snapshot": {
        "availability": "unavailable",
        "reference_ids": [],
        "unavailable_reason": "no_record",
    },
    "prior_project_work_refs": [PROJECT],
    "external_expertise_refs": ["expertise:research"],
}
INPUT = {
    "target_actor_profile_id": ACTOR,
    "role": "submitter",
    "qualification": QUALIFICATION,
    "reason": "Explicit project decision",
}


def receipt(action):
    return {
        "id": KEY,
        "qualification_snapshot_id": POLICY,
        "project_id": PROJECT,
        "actor_profile_id": ACTOR,
        "role": "submitter",
        "status": "active" if action == "issue" else "revoked",
        "version": 1 if action == "issue" else 2,
    }


def invoke(
    cli,
    origin,
    action,
    file,
    *,
    project=PROJECT,
    grant=KEY,
    key=KEY,
    token=TOKEN,
    output="json",
    extra_env=None,
):
    selectors = (project,) if action == "issue" else (project, grant)
    return cli(
        origin,
        token,
        "project",
        "role-grant",
        action,
        *selectors,
        "--input",
        str(file),
        "--idempotency-key",
        key,
        "-o",
        output,
        extra_env=extra_env,
    )


def test_project_role_exact_wire_explicit_qualification_and_uuid_identity(
    cli, tmp_path
):
    file = tmp_path / "role.json"
    with http_fixture() as (origin, response, requests):
        for action in ("issue", "revoke"):
            body = INPUT if action == "issue" else {"reason": INPUT["reason"]}
            wire = json.dumps(body, indent=2).encode() + b"\n"
            file.write_bytes(wire)
            response.update(
                status=201 if action == "issue" else 200,
                body=json.dumps(receipt(action)).encode(),
            )
            for spelling in (
                PROJECT,
                PROJECT.replace("-", ""),
                "{" + PROJECT + "}",
                "urn:uuid:" + PROJECT,
            ):
                result = invoke(
                    cli,
                    origin,
                    action,
                    file,
                    project=spelling,
                    grant=KEY.replace("-", ""),
                    key=KEY.replace("-", ""),
                )
                assert result.returncode == 0 and result.stderr == "", result.stderr
                assert json.loads(result.stdout) == receipt(action)
                path = f"/api/v1/projects/{quote(spelling, safe=':')}/role-grants"
                if action == "revoke":
                    path += "/" + KEY.replace("-", "") + "/revoke"
                assert requests[-1] == ("POST", path, "Bearer " + TOKEN)
                assert response["raw_commands"][-1] == wire
                assert response["commands"][-1] == (
                    "application/json",
                    [KEY.replace("-", "")],
                    body,
                )
            text = invoke(cli, origin, action, file, output="text")
            assert text.returncode == 0 and "not cached authority" in text.stdout
        body = deepcopy(INPUT)
        body["role"] = "reviewer"
        body["target_actor_profile_id"] = ACTOR.replace("-", "")
        file.write_text(json.dumps(body))
        response.update(
            status=201,
            body=json.dumps(receipt("issue") | {"role": "reviewer"}).encode(),
        )
        assert invoke(cli, origin, "issue", file).returncode == 0


def test_project_role_invalid_decisions_send_no_request(cli, tmp_path):
    file = tmp_path / "role.json"
    with http_fixture() as (origin, _, requests):
        invalid = [
            b"null",
            b"[]",
            b"{}",
            b" " * (1024 * 1024 + 1),
            json.dumps(INPUT | {"extra": 1}).encode(),
            json.dumps(INPUT | {"role": "project_manager"}).encode(),
            json.dumps(INPUT | {"target_actor_profile_id": "bad"}).encode(),
            json.dumps(INPUT | {"reason": " leading"}).encode(),
            json.dumps(INPUT | {"reason": "é" * 251}).encode(),
            json.dumps(INPUT | {"reason": "bad\u001b"}).encode(),
            b'{"reason":"first",' + json.dumps(INPUT)[1:].encode(),
        ]
        for key in INPUT:
            invalid += [
                json.dumps({k: v for k, v in INPUT.items() if k != key}).encode(),
                json.dumps(INPUT | {key: None}).encode(),
            ]
        for key in QUALIFICATION:
            for value in (None, [None] if key.endswith("refs") else {}):
                invalid.append(
                    json.dumps(
                        INPUT | {"qualification": QUALIFICATION | {key: value}}
                    ).encode()
                )
        for change in (
            {"reference_ids": []},
            {"reference_ids": [None]},
            {"reference_ids": ["https://private"]},
            {"reference_ids": ["x"] * 21},
            {"unavailable_reason": "no_record"},
            {"availability": "invented"},
        ):
            q = deepcopy(QUALIFICATION)
            q["skills_snapshot"].update(change)
            invalid.append(json.dumps(INPUT | {"qualification": q}).encode())
        q = deepcopy(QUALIFICATION)
        del q["skills_snapshot"]["unavailable_reason"]
        invalid.append(json.dumps(INPUT | {"qualification": q}).encode())
        for change in (
            {"unavailable_reason": None},
            {"reference_ids": ["skill:x"]},
            {"unavailable_reason": "invented"},
        ):
            q = deepcopy(QUALIFICATION)
            q["reputation_snapshot"].update(change)
            invalid.append(json.dumps(INPUT | {"qualification": q}).encode())
        for body in invalid:
            file.write_bytes(body)
            result = invoke(cli, origin, "issue", file)
            assert result.returncode == 2 and result.stdout == "", result.stderr
        for body in ({}, {"reason": None}, {"reason": ""}, INPUT):
            file.write_text(json.dumps(body))
            assert invoke(cli, origin, "revoke", file).returncode == 2
        for action in ("issue", "revoke"):
            file.write_text(
                json.dumps(INPUT if action == "issue" else {"reason": "Revoke"})
            )
            for override in ({"project": "../other"}, {"key": "bad"}):
                assert invoke(cli, origin, action, file, **override).returncode == 2
        assert invoke(cli, origin, "revoke", file, grant="bad").returncode == 2
        assert requests == []


def test_project_role_receipt_binding_rejects_otherwise_valid_substitution(
    cli, tmp_path
):
    file = tmp_path / "role.json"
    with http_fixture() as (origin, response, requests):
        for action in ("issue", "revoke"):
            file.write_text(
                json.dumps(INPUT if action == "issue" else {"reason": "Revoke"})
            )
            good = receipt(action)
            response.update(
                status=201 if action == "issue" else 200, body=json.dumps(good).encode()
            )
            assert invoke(cli, origin, action, file).returncode == 0
            variants = [
                good | {"project_id": POLICY},
                good | {"id": "bad"},
                good | {"actor_profile_id": "bad"},
                good | {"qualification_snapshot_id": "bad"},
                good | {"role": "manager"},
                good | {"status": "wrong"},
                good | {"version": 2 if action == "issue" else 1},
                good | {"extra": 1},
            ]
            variants += (
                [good | {"actor_profile_id": POLICY}, good | {"role": "reviewer"}]
                if action == "issue"
                else [good | {"id": POLICY}]
            )
            for key in good:
                variants += [
                    {k: v for k, v in good.items() if k != key},
                    good | {key: None},
                ]
            for value in variants:
                response["body"] = json.dumps(value).encode()
                before = len(requests)
                result = invoke(cli, origin, action, file)
                assert_failure(result, "invalid_api_response")
                assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
                assert len(requests) == before + 1


def test_project_role_denial_credential_safety_unknown_outcome_and_one_http2_post(
    cli, tmp_path
):
    file = tmp_path / "role.json"
    for action in ("issue", "revoke"):
        file.write_text(
            json.dumps(INPUT if action == "issue" else {"reason": "Revoke"})
        )
        with http_fixture() as (origin, response, requests):
            response.update(status=403, body=json.dumps(canonical_error()).encode())
            denied = invoke(cli, origin, action, file)
            assert_failure(denied, "authorization_denied")
            assert "outcome_unknown" not in json.loads(denied.stderr)["error"]
            for status, body in (
                (403, {"error": {"code": "denied"}}),
                (500, canonical_error()),
                (
                    201 if action == "issue" else 200,
                    receipt(action) | {"qualification_snapshot_id": POLICY},
                ),
            ):
                response.update(status=status, body=json.dumps(body).encode())
                before = len(requests)
                # A UUID-shaped bearer is valid response metadata, not safe to print.
                result = invoke(cli, origin, action, file, token=POLICY)
                assert result.returncode == 1 and result.stdout == ""
                assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
                assert len(requests) == before + 1
            text = invoke(cli, origin, action, file, output="text", token=POLICY)
            assert text.returncode == 1 and "unchanged" in text.stderr
        with goaway_fixture(tmp_path) as (origin, env, requests, _):
            result = invoke(cli, origin, action, file, extra_env=env)
            assert result.returncode == 1 and result.stdout == ""
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
            assert len(requests) == 1
