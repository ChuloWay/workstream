"""Built-binary proof of one-page, minimal system project catalogue reads."""

import json
from urllib.parse import parse_qs, urlsplit

from test_contributor_task_mutations import KEY, canonical_error
from test_http_boundary import PROJECT, TOKEN, assert_failure, http_fixture


def invoke(cli, origin, *flags, token=TOKEN, output="json"):
    return cli(origin, token, "-o", output, "project", "list", *flags)


def page(items, cursor=None):
    return {"items": items, "next_cursor": cursor}


def test_catalogue_reads_one_public_page_with_only_minimal_rows(cli):
    first = {"project_id": PROJECT, "name": "Project é\n\x1b[31m", "status": "draft"}
    second = {"project_id": KEY, "name": "Second", "status": "archived"}
    cursor = "opaque+/=é&next=not-another-parameter"
    with http_fixture() as (origin, response, requests):
        value = page([first, second], cursor)
        response["body"] = json.dumps(value, ensure_ascii=False).encode()
        result = invoke(cli, origin)
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert json.loads(result.stdout) == value
        assert requests == [("GET", "/api/v1/projects?limit=50", "Bearer " + TOKEN)]

        response["body"] = json.dumps(page([second])).encode()
        result = invoke(cli, origin, "--limit", "1", "--cursor", cursor)
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert json.loads(result.stdout) == page([second])
        assert len(requests) == 2  # No implicit traversal.
        request = urlsplit(requests[-1][1])
        assert request.path == "/api/v1/projects"
        assert parse_qs(request.query) == {"limit": ["1"], "cursor": [cursor]}

        response["body"] = json.dumps(value).encode()
        result = invoke(cli, origin, output="text")
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert result.stdout == (
            f"Project: {PROJECT}\nName: Project é\\u000A\\u001B[31m\nStatus: draft\n"
            f"Project: {KEY}\nName: Second\nStatus: archived\n"
            f"Next cursor: {cursor}\n"
        )
        assert "\x1b" not in result.stdout


def test_catalogue_rejects_invalid_page_flags_before_http(cli):
    with http_fixture() as (origin, _response, requests):
        for flags in (
            ("--limit", "0"),
            ("--limit", "101"),
            ("--limit", "not-a-number"),
            ("--cursor", ""),
            ("--cursor", "é" * 513),
            ("--cursor", b"\xff"),
            ("--project-id", PROJECT),
            ("unexpected-positional",),
        ):
            assert_failure(invoke(cli, origin, *flags), "invalid_arguments", 2)
        assert requests == []


def test_catalogue_rejects_malformed_success_without_partial_stdout(cli):
    row = {"project_id": PROJECT, "name": "Valid", "status": "active"}
    with http_fixture() as (origin, response, _requests):
        malformed = (
            None,
            [],
            {"items": [row]},
            {"items": None, "next_cursor": None},
            page([row | {"active_guide": "private"}]),
            page([{key: value for key, value in row.items() if key != "name"}]),
            page([row | {"project_id": None}]),
            page([row | {"project_id": "bad"}]),
            page([row | {"name": ""}]),
            page([row | {"status": "unknown"}]),
            page([row, row | {"project_id": PROJECT.replace("-", "")}]),
            page([], "next"),
            page([row], ""),
            page([row], "x" * 513),
            page([row]) | {"total": 1},
            page([row | {"name": TOKEN}]),
        )
        for value in malformed:
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin), "invalid_api_response")
        response["body"] = json.dumps(page([row, row | {"project_id": KEY}])).encode()
        assert_failure(invoke(cli, origin, "--limit", "1"), "invalid_api_response")
        response["body"] = b'{"items":[],"next_cursor":null,"items":[]}'
        assert_failure(invoke(cli, origin), "invalid_api_response")


def test_catalogue_preserves_backend_denial_and_cursor_error(cli):
    with http_fixture() as (origin, response, requests):
        response.update(
            status=403,
            body=json.dumps(canonical_error("project_catalogue_forbidden")).encode(),
        )
        result = invoke(cli, origin)
        assert_failure(result, "project_catalogue_forbidden")
        assert len(requests) == 1

        response.update(
            status=400, body=json.dumps(canonical_error("invalid_cursor")).encode()
        )
        result = invoke(cli, origin, "--cursor", "tampered")
        assert_failure(result, "invalid_cursor")
        assert len(requests) == 2
