"""Installed project-create process: wire contract, uncertainty and no replay."""

from copy import deepcopy
import json

from http2_fixture import goaway_fixture
from test_contributor_task_mutations import KEY, canonical_error
from test_http_boundary import PROFILE, PROJECT, TOKEN, assert_failure, http_fixture

CREATED = {
    "id": PROJECT,
    "name": "Project é\n\x1b[31m",
    "slug": "slug\n\u202e",
    "description": "Description\n\x1b[32m",
    "status": "draft",
    "created_at": PROFILE["created_at"],
    "updated_at": PROFILE["updated_at"],
}


def invoke(cli, origin, *flags, key=KEY, output="json", token=TOKEN):
    return cli(
        origin,
        token,
        "-o",
        output,
        "project",
        "create",
        "--name",
        "Project é",
        "--slug",
        " slug ",
        "--idempotency-key",
        key,
        *flags,
    )


def test_project_create_preserves_fields_key_and_exact_full_response(cli):
    with http_fixture() as (origin, response, requests):
        response.update(status=201, body=json.dumps(CREATED).encode())
        for key in (KEY, KEY.replace("-", ""), "{" + KEY + "}", "urn:uuid:" + KEY):
            for flags, expected in (
                ((), {"name": "Project é", "slug": " slug "}),
                (
                    ("--description", ""),
                    {"name": "Project é", "slug": " slug ", "description": ""},
                ),
                (
                    ("--description", "Evidence é\n"),
                    {
                        "name": "Project é",
                        "slug": " slug ",
                        "description": "Evidence é\n",
                    },
                ),
            ):
                result = invoke(cli, origin, *flags, key=key)
                assert result.returncode == 0 and result.stderr == "", result.stderr
                assert result.stdout.strip().encode() == response["body"]
                assert requests[-1] == ("POST", "/api/v1/projects", "Bearer " + TOKEN)
                assert response["commands"][-1] == ("application/json", [key], expected)
        # A committed recovery may return a project which has since progressed.
        response["body"] = json.dumps(CREATED | {"status": "active"}).encode()
        assert invoke(cli, origin).returncode == 0
        assert len(requests) == len(response["commands"]) == 13


def test_project_create_text_and_nullable_description(cli):
    with http_fixture() as (origin, response, requests):
        response.update(status=201, body=json.dumps(CREATED).encode())
        result = invoke(cli, origin, output="text")
        assert result.returncode == 0 and result.stderr == ""
        assert result.stdout == (
            f"Project: {PROJECT}\nName: Project é\\u000A\\u001B[31m\nStatus: draft\n"
            "Slug: slug\\u000A\\u202E\nDescription: Description\\u000A\\u001B[32m\n"
            f"Created: {PROFILE['created_at']}\nUpdated: {PROFILE['updated_at']}\n"
        )
        for description in (None, ""):
            response["body"] = json.dumps(
                CREATED | {"description": description}
            ).encode()
            result = invoke(cli, origin)
            assert result.returncode == 0 and result.stderr == ""
            assert result.stdout.strip().encode() == response["body"]
        assert len(requests) == 3


def test_project_create_text_and_encoded_size_boundaries(cli):
    with http_fixture() as (origin, response, requests):
        response.update(status=201, body=json.dumps(CREATED).encode())
        for name, slug in (("", ""), ("é" * 200, "é" * 120)):
            result = invoke(cli, origin, "--name", name, "--slug", slug)
            assert result.returncode == 0 and result.stderr == ""
            assert response["commands"][-1][2] == {"name": name, "slug": slug}
        empty = {"name": "x", "slug": "x", "description": ""}
        description = "d" * (8192 - len(json.dumps(empty, separators=(",", ":"))))
        result = invoke(
            cli, origin, "--name", "x", "--slug", "x", "--description", description
        )
        assert result.returncode == 0 and result.stderr == ""
        assert response["commands"][-1][2] == empty | {"description": description}
        assert_failure(
            invoke(
                cli,
                origin,
                "--name",
                "x",
                "--slug",
                "x",
                "--description",
                description + "d",
            ),
            "invalid_arguments",
            2,
        )
        assert len(requests) == 3


def test_project_create_invalid_input_never_dispatches(cli):
    with http_fixture() as (origin, _response, requests):
        for flags in (
            ("--name", "é" * 201),
            ("--slug", "é" * 121),
            ("--name", b"invalid-\xff"),
            ("--slug", b"invalid-\xff"),
            ("--description", b"invalid-\xff"),
            ("--description", "d" * 8192),
            ("--idempotency-key", "not-uuid"),
            ("--idempotency-key", ""),
            ("--actor-id", PROJECT),
            ("--endpoint", "/private"),
            ("unexpected-positional",),
        ):
            assert_failure(invoke(cli, origin, *flags), "invalid_arguments", 2)
        for flags in (
            (),
            ("--name", "x", "--idempotency-key", KEY),
            ("--slug", "x", "--idempotency-key", KEY),
            ("--name", "x", "--slug", "x"),
        ):
            assert_failure(
                cli(origin, TOKEN, "-o", "json", "project", "create", *flags),
                "invalid_arguments",
                2,
            )
        assert requests == []


def test_project_create_malformed_success_is_unknown(cli):
    with http_fixture() as (origin, response, requests):
        response["status"] = 201
        values = [
            CREATED | {key: None}
            for key in ("id", "name", "slug", "status", "created_at", "updated_at")
        ]
        values += [
            CREATED | delta
            for delta in (
                {"id": "bad"},
                {"created_at": "bad"},
                {"updated_at": "bad"},
                {"description": 123},
                {"private": "secret"},
            )
        ]
        values += [
            {key: value for key, value in CREATED.items() if key != missing}
            for missing in CREATED
        ]
        values.append({key: CREATED[key] for key in ("id", "name", "status")})
        malformed = [json.dumps(value).encode() for value in values]
        malformed += [
            b"null",
            b"[]",
            b"{}",
            b"not-json",
            json.dumps(CREATED)
            .encode()
            .replace(b'"id":', b'"id": "' + PROJECT.encode() + b'", "id":', 1),
        ]
        for body in malformed:
            response["body"] = body
            result = invoke(cli, origin)
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == len(malformed)


def test_project_create_denial_uncertainty_and_no_retry(cli):
    with http_fixture() as (origin, response, requests):
        null_details = deepcopy(canonical_error())
        null_details["error"]["details"] = None
        cases = (
            (403, canonical_error(), "application/json", False),
            (409, canonical_error("idempotency_mismatch"), "application/json", False),
            (422, canonical_error("validation_error"), "application/json", False),
            (403, null_details, "application/json", True),
            (403, {"error": {"code": "denied"}}, "application/json", True),
            (403, canonical_error(), "text/html", True),
            (403, canonical_error() | {"unknown": True}, "application/json", True),
            (503, canonical_error(), "application/json", True),
            (302, {}, "application/json", True),
            (200, CREATED, "application/json", True),
            (202, CREATED, "application/json", True),
            (201, CREATED, "text/html", True),
        )
        for status, value, content_type, unknown in cases:
            response.update(
                status=status,
                body=json.dumps(value).encode(),
                headers={"Content-Type": content_type, "Location": origin + "/private"},
            )
            result = invoke(cli, origin)
            assert result.returncode == 1 and result.stdout == ""
            assert (
                json.loads(result.stderr)["error"].get("outcome_unknown", False)
                is unknown
            )
        response.update(
            status=201, body=b" " * 65537, headers={"Content-Type": "application/json"}
        )
        result = invoke(cli, origin)
        assert_failure(result, "invalid_api_response")
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        response["drop"] = True
        result = invoke(cli, origin, output="text")
        assert result.returncode == 1 and result.stdout == ""
        assert "project creation outcome unknown" in result.stderr
        assert "unchanged name, slug, description and idempotency key" in result.stderr
        assert "whoami" not in result.stderr
        assert len(requests) == len(response["commands"]) == len(cases) + 2


def test_project_create_reflected_error_metadata_does_not_leak_bearer(cli):
    with http_fixture() as (origin, response, requests):
        for token in ("credential_canary_AAA", KEY):
            response.update(
                status=403,
                body=json.dumps(canonical_error(token)).encode(),
                headers={"Content-Type": "application/json", "X-Correlation-ID": token},
            )
            result = invoke(cli, origin, token=token)
            assert_failure(result, "api_error")
            assert "outcome_unknown" not in json.loads(result.stderr)["error"]
            assert "correlation_id" not in json.loads(result.stderr)["error"]
        assert len(requests) == 2


def test_project_create_is_not_replayed_after_http2_goaway(cli, tmp_path):
    with goaway_fixture(tmp_path) as (origin, env, bodies, connections):
        result = cli(
            origin,
            TOKEN,
            "-o",
            "json",
            "project",
            "create",
            "--name",
            "Received before GOAWAY",
            "--slug",
            "one-shot",
            "--idempotency-key",
            KEY,
            extra_env=env,
        )
        assert_failure(result, "service_unavailable")
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert connections == ["h2"]
        assert [json.loads(value) for value in bodies] == [
            {"name": "Received before GOAWAY", "slug": "one-shot"}
        ]
