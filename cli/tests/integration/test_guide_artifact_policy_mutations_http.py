"""Built-binary HTTP proof for the two manual artifact-policy draft writes."""

import json

import pytest

from test_guide_inspection_http import (
    GUIDE,
    GUIDE_PATH,
    HASH,
    POLICY,
    SNAPSHOT,
    artifact_policy,
)
from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture

KEY = "018f0ebc-7966-7e8d-bc4d-1cae1e000030"
SUCCESSOR = "018f0ebc-7966-7e8d-bc4d-1cae1e000031"
CREATE = ("project", "guide", "artifact-policy", "create", PROJECT, GUIDE)
UPDATE = ("project", "guide", "artifact-policy", "update", PROJECT, GUIDE, POLICY)


def create_input():
    return {
        "source_snapshot_id": SNAPSHOT,
        "policy_version": "manual-v1",
        "policy_body": {
            "manifest_required": True,
            "required_artifacts": [
                {"key": "answer", "path": "outputs/answer.md", "hash_required": True},
            ],
        },
        "change_summary": "A human draft",
    }


def update_input():
    return {
        "expected_policy_hash": HASH,
        "successor_policy_version": "manual-v2",
        "change_summary": "A successor draft",
    }


def manual_response(update=False):
    value = artifact_policy()
    value.update(
        id=SUCCESSOR if update else POLICY,
        policy_version="manual-v2" if update else "manual-v1",
        lifecycle_status="draft",
        policy_body=create_input()["policy_body"],
        derivation_source="manual_admin_derivation",
        source_material_refs=[],
        created_by=ACTOR,
        approved_by_role=None,
        approved_by_actor=None,
        approved_at=None,
        supersedes_policy_id=POLICY if update else None,
        change_summary="A successor draft" if update else "A human draft",
    )
    return value


def write_input(tmp_path, body):
    path = tmp_path / "policy.json"
    path.write_text(body, encoding="utf-8")
    return str(path)


@pytest.mark.parametrize(
    ("command", "method", "route", "request_body", "response", "status"),
    [
        (
            CREATE,
            "POST",
            GUIDE_PATH + "/submission-artifact-policies",
            create_input(),
            manual_response(),
            201,
        ),
        (
            UPDATE,
            "PATCH",
            GUIDE_PATH + "/submission-artifact-policies/" + POLICY,
            update_input(),
            manual_response(True),
            200,
        ),
    ],
)
def test_exact_write_and_safe_output(
    cli, tmp_path, command, method, route, request_body, response, status
):
    request_bytes = json.dumps(request_body, ensure_ascii=False).encode()
    path = write_input(tmp_path, request_bytes.decode())
    response["change_summary"] += "\n\x1b[31m\u202e"
    if method == "POST":
        response["change_summary"] = request_body["change_summary"]
        response["policy_body"]["attestation_terms"] = ["\n\x1b[31m\u202e"]
    else:
        request_body["change_summary"] = response["change_summary"]
        request_bytes = json.dumps(request_body, ensure_ascii=False).encode()
        path = write_input(tmp_path, request_bytes.decode())
    with http_fixture() as (origin, fixture, requests):
        fixture.update(status=status, body=json.dumps(response).encode())
        result = cli(
            origin,
            TOKEN,
            *command,
            "--input",
            path,
            "--idempotency-key",
            KEY,
            "-o",
            "json",
        )
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert json.loads(result.stdout) == response
        assert requests == [(method, route, "Bearer " + TOKEN)]
        assert fixture["raw_commands"] == [request_bytes]
        assert fixture["request_headers"][0]["Idempotency-Key"] == KEY
        text = cli(origin, TOKEN, *command, "--input", path, "--idempotency-key", KEY)
        assert text.returncode == 0 and text.stderr == "", text.stderr
        assert "\x1b" not in text.stdout and "\u202e" not in text.stdout
        assert len(requests) == 2


@pytest.mark.parametrize(
    ("command", "body"),
    [
        (CREATE, create_input() | {"source_snapshot_id": "bad"}),
        (CREATE, create_input() | {"policy_version": "agent-forged"}),
        (CREATE, create_input() | {"policy_version": "\u001cmanual-v1"}),
        (CREATE, create_input() | {"policy_body": None}),
        (CREATE, create_input() | {"policy_body": []}),
        (CREATE, create_input() | {"approval": True}),
        (UPDATE, update_input() | {"expected_policy_hash": "bad"}),
        (UPDATE, update_input() | {"successor_policy_version": "agent-forged"}),
        (UPDATE, update_input() | {"successor_policy_version": "\u001cmanual-v2"}),
        (UPDATE, update_input() | {"policy_body": []}),
        (UPDATE, update_input() | {"approval": True}),
    ],
)
def test_invalid_input_never_writes(cli, tmp_path, command, body):
    path = write_input(tmp_path, json.dumps(body))
    with http_fixture() as (origin, fixture, requests):
        result = cli(
            origin,
            TOKEN,
            *command,
            "--input",
            path,
            "--idempotency-key",
            KEY,
            "-o",
            "json",
        )
        assert_failure(result, "invalid_arguments", exit_code=2)
        assert requests == [] and fixture["commands"] == [] and fixture["updates"] == []


@pytest.mark.parametrize("command", [CREATE, UPDATE])
def test_invalid_selector_key_and_oversized_body_never_write(cli, tmp_path, command):
    body = create_input() if command == CREATE else update_input()
    path = write_input(tmp_path, json.dumps(body))
    with http_fixture() as (origin, fixture, requests):
        for args, key in ((command, "bad"), (command[:-1] + ("bad",), KEY)):
            result = cli(
                origin,
                TOKEN,
                *args,
                "--input",
                path,
                "--idempotency-key",
                key,
                "-o",
                "json",
            )
            assert_failure(result, "invalid_arguments", exit_code=2)
        huge = write_input(tmp_path, json.dumps(body) + " " * (1024 * 1024))
        result = cli(
            origin,
            TOKEN,
            *command,
            "--input",
            huge,
            "--idempotency-key",
            KEY,
            "-o",
            "json",
        )
        assert_failure(result, "invalid_arguments", exit_code=2)
        assert requests == [] and fixture["commands"] == [] and fixture["updates"] == []


@pytest.mark.parametrize("command", [CREATE, UPDATE])
def test_malformed_or_mismatched_success_is_uncertain_without_retry(
    cli, tmp_path, command
):
    create = command == CREATE
    path = write_input(
        tmp_path, json.dumps(create_input() if create else update_input())
    )
    valid = manual_response(not create)
    variants = [
        valid | {"project_id": ACTOR},
        valid | {"guide_id": ACTOR},
        valid | {"source_snapshot_id": ACTOR}
        if create
        else valid | {"supersedes_policy_id": ACTOR},
        valid | {"policy_version": "different"},
        valid | {"derivation_source": "unified_compilation"},
        valid | {"lifecycle_status": "approved"},
        valid | {"approved_by_actor": ACTOR},
        valid | {"policy_hash": "bad"},
        valid | {"change_summary": TOKEN},
    ]
    with http_fixture() as (origin, fixture, requests):
        fixture["status"] = 201 if create else 200
        for value in variants:
            fixture["body"] = json.dumps(value).encode()
            result = cli(
                origin,
                TOKEN,
                *command,
                "--input",
                path,
                "--idempotency-key",
                KEY,
                "-o",
                "json",
            )
            assert_failure(result, "invalid_api_response")
            error = json.loads(result.stderr)["error"]
            assert error["outcome_unknown"] is True
        assert len(requests) == len(variants)
        fixture["body"] = json.dumps(variants[0]).encode()
        text = cli(origin, TOKEN, *command, "--input", path, "--idempotency-key", KEY)
        assert text.returncode == 1 and "manually replay" in text.stderr
        assert len(requests) == len(variants) + 1


@pytest.mark.parametrize("command", [CREATE, UPDATE])
def test_explicit_policy_body_mismatch_is_uncertain(cli, tmp_path, command):
    create = command == CREATE
    request = (
        create_input()
        if create
        else update_input() | {"policy_body": create_input()["policy_body"]}
    )
    path = write_input(tmp_path, json.dumps(request))
    valid = manual_response(not create)
    substitutions = [
        valid | {"policy_body": valid["policy_body"] | {"manifest_required": False}},
        valid
        | {
            "policy_body": valid["policy_body"]
            | {
                "required_artifacts": [
                    {"key": "answer", "path": "different.md", "hash_required": True}
                ]
            }
        },
    ]
    with http_fixture() as (origin, fixture, requests):
        fixture["status"] = 201 if create else 200
        for substituted in substitutions:
            fixture["body"] = json.dumps(substituted).encode()
            result = cli(
                origin,
                TOKEN,
                *command,
                "--input",
                path,
                "--idempotency-key",
                KEY,
                "-o",
                "json",
            )
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == len(substitutions)


def test_explicit_null_update_body_is_forwarded(cli, tmp_path):
    request = update_input() | {"policy_body": None}
    raw = json.dumps(request).encode()
    path = write_input(tmp_path, raw.decode())
    with http_fixture() as (origin, fixture, requests):
        fixture.update(status=200, body=json.dumps(manual_response(True)).encode())
        result = cli(
            origin,
            TOKEN,
            *UPDATE,
            "--input",
            path,
            "--idempotency-key",
            KEY,
            "-o",
            "json",
        )
        assert result.returncode == 0, result.stderr
        assert fixture["raw_commands"] == [raw]
        assert requests == [
            (
                "PATCH",
                GUIDE_PATH + "/submission-artifact-policies/" + POLICY,
                "Bearer " + TOKEN,
            )
        ]


@pytest.mark.parametrize("command", [CREATE, UPDATE])
def test_numeric_policy_body_normalization_is_valid_receipt(cli, tmp_path, command):
    create = command == CREATE
    request = create_input() if create else update_input()
    request["policy_body"] = create_input()["policy_body"] | {
        "maximum_file_size_bytes": 1000
    }
    raw = (
        json.dumps(request)
        .replace('"maximum_file_size_bytes": 1000', '"maximum_file_size_bytes": 1e3')
        .encode()
    )
    assert b'"maximum_file_size_bytes": 1e3' in raw
    path = write_input(tmp_path, raw.decode())
    response = manual_response(not create)
    response["policy_body"]["maximum_file_size_bytes"] = 1000
    with http_fixture() as (origin, fixture, requests):
        fixture.update(
            status=201 if create else 200, body=json.dumps(response).encode()
        )
        result = cli(
            origin,
            TOKEN,
            *command,
            "--input",
            path,
            "--idempotency-key",
            KEY,
            "-o",
            "json",
        )
        assert result.returncode == 0, result.stderr
        assert fixture["raw_commands"] == [raw]
        assert len(requests) == 1


@pytest.mark.parametrize("command", [CREATE, UPDATE])
def test_backend_denial_and_conflict_remain_backend_decisions(cli, tmp_path, command):
    path = write_input(
        tmp_path, json.dumps(create_input() if command == CREATE else update_input())
    )
    with http_fixture() as (origin, fixture, requests):
        for status, code in (
            (404, "project_authorization_resource_not_found"),
            (409, "submission_policy_precondition_failed"),
        ):
            fixture.update(
                status=status,
                body=json.dumps(
                    {
                        "error": {
                            "code": code,
                            "message": TOKEN,
                            "details": {},
                            "correlation_id": KEY,
                            "retryable": False,
                        }
                    }
                ).encode(),
            )
            result = cli(
                origin,
                TOKEN,
                *command,
                "--input",
                path,
                "--idempotency-key",
                KEY,
                "-o",
                "json",
            )
            assert_failure(result, code)
            assert TOKEN not in result.stderr
            if command == UPDATE:
                assert not json.loads(result.stderr)["error"].get(
                    "outcome_unknown", False
                )
        assert len(requests) == 2


@pytest.mark.parametrize("content_type", ["application/json", "text/html"])
def test_incomplete_patch_denial_is_uncertain(cli, tmp_path, content_type):
    path = write_input(tmp_path, json.dumps(update_input()))
    with http_fixture() as (origin, fixture, requests):
        fixture.update(
            status=409,
            body=b'{"error":{"code":"submission_policy_precondition_failed"}}',
        )
        fixture["headers"] = {"Content-Type": content_type}
        result = cli(
            origin,
            TOKEN,
            *UPDATE,
            "--input",
            path,
            "--idempotency-key",
            KEY,
            "-o",
            "json",
        )
        assert result.returncode == 1
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == 1
