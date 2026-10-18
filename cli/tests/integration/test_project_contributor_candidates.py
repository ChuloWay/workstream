"""Built-binary proof of exact-project, privacy-safe candidate discovery."""

import json
from urllib.parse import parse_qs, quote, urlsplit

from test_contributor_task_mutations import KEY, canonical_error
from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture


def invoke(cli, origin, *flags, project=PROJECT, token=TOKEN, output="json"):
    return cli(
        origin,
        token,
        "project",
        "role-grant",
        "candidates",
        project,
        *flags,
        "-o",
        output,
    )


def page(items, cursor=None):
    return {"items": items, "next_cursor": cursor}


def test_candidates_use_one_exact_public_get_and_preserve_nullable_projection(cli):
    row = {"actor_profile_id": ACTOR, "display_name": None}
    named = {"actor_profile_id": KEY, "display_name": "Ada é\n\x1b[31m"}
    with http_fixture() as (origin, response, requests):
        for spelling in (
            PROJECT,
            PROJECT.replace("-", ""),
            "{" + PROJECT + "}",
            "urn:uuid:" + PROJECT,
        ):
            value = page([row, named], "opaque+/=é&next=not-another-parameter")
            response["body"] = json.dumps(value).encode()
            before = len(requests)
            result = invoke(cli, origin, project=spelling)
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert json.loads(result.stdout) == value
            assert len(requests) == before + 1
            assert requests[-1] == (
                "GET",
                f"/api/v1/projects/{quote(spelling, safe=':')}/contributor-candidates?limit=50",
                "Bearer " + TOKEN,
            )
        cursor = "opaque+/=é&next=not-another-parameter"
        response["body"] = json.dumps(page([row], cursor)).encode()
        result = invoke(cli, origin, "--limit", "1", "--cursor", cursor)
        assert result.returncode == 0 and json.loads(result.stdout) == page(
            [row], cursor
        )
        request = urlsplit(requests[-1][1])
        assert request.path == f"/api/v1/projects/{PROJECT}/contributor-candidates"
        assert parse_qs(request.query) == {"limit": ["1"], "cursor": [cursor]}
        for value in (page([]), page([row, named])):
            response["body"] = json.dumps(value).encode()
            result = invoke(cli, origin, output="text")
            assert result.returncode == 0 and result.stderr == "", result.stderr
            fields = dict(line.split(": ", 1) for line in result.stdout.splitlines())
            assert {name: json.loads(data) for name, data in fields.items()} == {
                "Project": PROJECT,
                "Contributor candidates (not qualification or authority)": value[
                    "items"
                ],
                "Next cursor": None,
            }
            assert "\x1b" not in result.stdout and "\n\x1b" not in result.stdout


def test_candidates_reject_invalid_selectors_and_cursors_before_http(cli):
    with http_fixture() as (origin, _response, requests):
        for project in ("../other", "", "not-a-uuid"):
            assert_failure(invoke(cli, origin, project=project), "invalid_arguments", 2)
        for flags in (
            ("--limit", "0"),
            ("--limit", "101"),
            ("--cursor", ""),
            ("--cursor", "é" * 513),
            ("--cursor", b"\xff"),
        ):
            assert_failure(invoke(cli, origin, *flags), "invalid_arguments", 2)
        assert requests == []


def test_candidates_reject_malformed_duplicate_and_reflected_success(cli):
    row = {"actor_profile_id": ACTOR, "display_name": None}
    with http_fixture() as (origin, response, _requests):
        valid = page([row])
        response["body"] = json.dumps(valid).encode()
        assert invoke(cli, origin).returncode == 0
        malformed = (
            None,
            [],
            {"items": [row]},
            {"items": None, "next_cursor": None},
            page([row | {"contact_email": "private@example.test"}]),
            page([{key: value for key, value in row.items() if key != "display_name"}]),
            page([row | {"actor_profile_id": None}]),
            page([row | {"actor_profile_id": "bad"}]),
            page([row | {"display_name": 42}]),
            page([row, row | {"actor_profile_id": ACTOR.replace("-", "")}]),
            page([], "next"),
            page([row], ""),
            page([row], "x" * 513),
            page([row], None) | {"total": 1},
            page([row | {"display_name": TOKEN}]),
            page([row | {"actor_profile_id": TOKEN}]),
        )
        for value in malformed:
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        response["body"] = json.dumps(
            page([row, row | {"actor_profile_id": KEY}])
        ).encode()
        assert_failure(invoke(cli, origin, "--limit", "1"), "invalid_api_response")
        response["body"] = b'{"items":[],"next_cursor":null,"items":[]}'
        assert_failure(invoke(cli, origin), "invalid_api_response")


def test_candidates_preserve_backend_denial_without_disclosing_bearer(cli):
    with http_fixture() as (origin, response, requests):
        response.update(
            status=404,
            body=json.dumps(
                canonical_error("project_authorization_resource_not_found")
            ).encode(),
        )
        result = invoke(cli, origin, token=ACTOR.replace("-", ""))
        assert_failure(result, "project_authorization_resource_not_found")
        assert ACTOR.lower() not in result.stderr.lower()
        assert "outcome_unknown" not in json.loads(result.stderr)["error"]
        assert len(requests) == 1
        response.update(
            status=400, body=json.dumps(canonical_error("invalid_cursor")).encode()
        )
        result = invoke(cli, origin, "--cursor", "tampered")
        assert_failure(result, "invalid_cursor")
        assert len(requests) == 2
