"""Built-binary grant history reads; no client-side authority decisions."""

from copy import deepcopy
import json
from urllib.parse import parse_qs, quote, urlsplit

from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture
from test_contributor_task_mutations import KEY, POLICY, canonical_error
from test_project_role_mutations import QUALIFICATION

STAMP = "2026-10-01T00:00:00Z"


def grant(*, revoked=False):
    return {
        "id": KEY,
        "project_id": PROJECT,
        "actor_profile_id": ACTOR,
        "role": "submitter",
        "status": "revoked" if revoked else "active",
        "version": 2 if revoked else 1,
        "grant_method": "manual",
        "qualification_snapshot": QUALIFICATION
        | {
            "id": POLICY,
            "requested_role": "submitter",
            "captured_by_actor_profile_id": ACTOR,
            "captured_by_admin_role_grant_id": KEY,
            "captured_at": STAMP,
        },
        "granted_by_actor_profile_id": ACTOR,
        "granted_by_admin_role_grant_id": KEY,
        "granted_at": STAMP,
        "grant_reason": "Explicit qualification decision",
        "revoked_by_actor_profile_id": ACTOR if revoked else None,
        "revoked_at": STAMP if revoked else None,
        "revoked_reason": "Participation ended" if revoked else None,
    }


def invoke(
    cli,
    origin,
    action,
    *flags,
    project=PROJECT,
    selected=KEY,
    token=TOKEN,
    output="json",
):
    selectors = (project,) if action == "list" else (project, selected)
    return cli(
        origin, token, "project", "role-grant", action, *selectors, *flags, "-o", output
    )


def test_grant_reads_exact_projection_filters_cursor_and_uuid_spellings(cli):
    with http_fixture() as (origin, response, requests):
        for spelling in (
            PROJECT,
            PROJECT.replace("-", ""),
            "{" + PROJECT + "}",
            "urn:uuid:" + PROJECT,
        ):
            value = grant(revoked=True)
            response["body"] = json.dumps(value).encode()
            result = invoke(
                cli, origin, "show", project=spelling, selected=KEY.replace("-", "")
            )
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert json.loads(result.stdout) == value
            assert requests[-1] == (
                "GET",
                f"/api/v1/projects/{quote(spelling, safe=':')}/role-grants/{KEY.replace('-', '')}",
                "Bearer " + TOKEN,
            )
        cursor = "opaque+/=é&next=not-another-parameter"
        page = {"items": [value], "next_cursor": cursor}
        response["body"] = json.dumps(page).encode()
        before = len(requests)
        result = invoke(
            cli,
            origin,
            "list",
            "--limit",
            "1",
            "--status",
            "revoked",
            "--role",
            "submitter",
            "--cursor",
            cursor,
        )
        assert result.returncode == 0 and json.loads(result.stdout) == page
        assert len(requests) == before + 1  # no automatic continuation
        request = urlsplit(requests[-1][1])
        assert parse_qs(request.query) == {
            "limit": ["1"],
            "status": ["revoked"],
            "role": ["submitter"],
            "cursor": [cursor],
        }
        for value in (
            {"items": [], "next_cursor": None},
            {
                "items": [grant(), grant(revoked=True) | {"id": ACTOR}],
                "next_cursor": None,
            },
        ):
            response["body"] = json.dumps(value).encode()
            result = invoke(cli, origin, "list")
            assert result.returncode == 0 and json.loads(result.stdout) == value
            assert parse_qs(urlsplit(requests[-1][1]).query) == {"limit": ["50"]}
        for revoked in (False, True):
            value = grant(revoked=revoked)
            response["body"] = json.dumps(value).encode()
            text = invoke(cli, origin, "show", output="text")
            assert text.returncode == 0 and text.stderr == ""
            assert (
                json.loads(text.stdout.removeprefix("Grant history (not authority): "))
                == value
            )
            page = {"items": [value], "next_cursor": "opaque-next"}
            response["body"] = json.dumps(page).encode()
            text = invoke(cli, origin, "list", output="text")
            assert text.returncode == 0 and text.stderr == ""
            fields = dict(line.split(": ", 1) for line in text.stdout.splitlines())
            assert {key: json.loads(value) for key, value in fields.items()} == {
                "Project": PROJECT,
                "Grant history (not authority)": page["items"],
                "Next cursor": page["next_cursor"],
            }
        # Qualification-heavy pages legitimately exceed the default 64 KiB.
        value = grant()
        for name in ("skills_snapshot", "reputation_snapshot"):
            value["qualification_snapshot"][name] = {
                "availability": "available",
                "reference_ids": ["x" * 120] * 20,
                "unavailable_reason": None,
            }
        page = {
            "items": [
                value | {"id": f"018f0ebc-7966-7e8d-bc4d-{index:012x}"}
                for index in range(100)
            ],
            "next_cursor": None,
        }
        response["body"] = json.dumps(page).encode()
        assert len(response["body"]) > 64 * 1024
        assert invoke(cli, origin, "list", "--limit", "100").returncode == 0
        response["body"] = json.dumps(
            {"items": [grant()], "next_cursor": "next\u202e\u001b"}
        ).encode()
        text = invoke(cli, origin, "list", output="text")
        assert text.returncode == 0 and "not authority" in text.stdout
        assert "\u202e" not in text.stdout and "\u001b" not in text.stdout
        response["body"] = json.dumps(grant()).encode()
        assert invoke(cli, origin, "show", output="text").returncode == 0


def test_grant_denial_never_discloses_uuid_bearer_alias_in_either_header(cli):
    with http_fixture() as (origin, response, requests):
        response.update(status=403, body=json.dumps(canonical_error()).encode())
        for action in ("list", "show"):
            for headers, expected in (
                ({"X-Correlation-ID": KEY}, KEY),
                ({"X-Correlation-ID": ACTOR, "X-Request-ID": KEY}, KEY),
                ({"X-Correlation-ID": "invalid", "X-Request-ID": ACTOR}, None),
                ({"X-Correlation-ID": ACTOR.upper(), "X-Request-ID": ACTOR}, None),
            ):
                response["headers"] = {"Content-Type": "application/json"} | headers
                before = len(requests)
                result = invoke(cli, origin, action, token=ACTOR.replace("-", ""))
                assert_failure(result, "authorization_denied")
                assert ACTOR.lower() not in result.stderr.lower()
                error = json.loads(result.stderr)["error"]
                assert error.get("correlation_id") == expected
                assert "outcome_unknown" not in error and len(requests) == before + 1
                text = invoke(
                    cli, origin, action, token=ACTOR.replace("-", ""), output="text"
                )
                assert text.returncode == 1 and text.stdout == ""
                assert ACTOR.lower() not in text.stderr.lower()


def test_grant_read_invalid_selectors_filters_and_wire_cursors_do_not_send(cli):
    with http_fixture() as (origin, _, requests):
        for action in ("list", "show"):
            assert invoke(cli, origin, action, project="../other").returncode == 2
        assert invoke(cli, origin, "show", selected="bad").returncode == 2
        for flags in (
            ("--limit", "0"),
            ("--limit", "101"),
            ("--status", ""),
            ("--status", "all"),
            ("--role", ""),
            ("--role", "project_manager"),
            ("--cursor", ""),
            ("--cursor", "é" * 513),
            ("--cursor", b"\xff"),
        ):
            result = invoke(cli, origin, "list", *flags)
            assert result.returncode == 2 and result.stdout == "", result.stderr
        assert requests == []


def test_grant_read_nested_validation_lifecycle_and_identity_substitution(cli):
    good = grant()
    variants = [
        good | {"project_id": POLICY},
        good | {"id": ACTOR},
        good | {"role": "manager"},
        good | {"version": 2},
        good | {"grant_method": "inferred"},
        good | {"granted_at": "bad"},
        good | {"revoked_at": STAMP},
        good | {"private": 1},
    ]
    for key in good:
        variants.append({k: v for k, v in good.items() if k != key})
        if not key.startswith("revoked_"):
            variants.append(good | {key: None})
    for key in (
        "actor_profile_id",
        "granted_by_actor_profile_id",
        "granted_by_admin_role_grant_id",
    ):
        variants.append(good | {key: "not-uuid"})
    snapshot = good["qualification_snapshot"]
    for key in snapshot:
        variants += [
            good
            | {
                "qualification_snapshot": {
                    k: v for k, v in snapshot.items() if k != key
                }
            },
            good | {"qualification_snapshot": snapshot | {key: None}},
        ]
    for update in (
        {"id": "bad"},
        {"requested_role": "reviewer"},
        {"captured_by_actor_profile_id": POLICY},
        {"captured_by_admin_role_grant_id": POLICY},
        {"captured_at": "bad"},
        {"extra": 1},
        {"prior_project_work_refs": [None]},
        {"external_expertise_refs": [None]},
        {"prior_project_work_refs": ["bad"]},
    ):
        variants.append(good | {"qualification_snapshot": snapshot | update})
    for name in ("skills_snapshot", "reputation_snapshot"):
        for update in (
            {"reference_ids": [None]},
            {"reference_ids": ["https://private"]},
            {"reference_ids": ["x"] * 21},
            {"availability": "unknown"},
            {"unavailable_reason": "wrong"},
            {"extra": 1},
        ):
            item = deepcopy(good)
            item["qualification_snapshot"][name].update(update)
            variants.append(item)
    revoked = grant(revoked=True)
    variants += [
        revoked | {"version": 1},
        revoked | {"revoked_at": "bad"},
        revoked | {"revoked_by_actor_profile_id": "bad"},
        revoked | {"revoked_reason": ""},
    ]
    for key in ("revoked_by_actor_profile_id", "revoked_at", "revoked_reason"):
        variants.append(revoked | {key: None})
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(good).encode()
        assert invoke(cli, origin, "show").returncode == 0
        for value in variants:
            response["body"] = json.dumps(value).encode()
            before = len(requests)
            assert_failure(invoke(cli, origin, "show"), "invalid_api_response")
            assert len(requests) == before + 1
        for value in (
            b'{"id":"' + KEY.encode() + b'",' + json.dumps(good)[1:].encode(),
            b'{"qualification_snapshot":null,' + json.dumps(good)[1:].encode(),
        ):
            response["body"] = value
            assert_failure(invoke(cli, origin, "show"), "invalid_api_response")


def test_grant_pages_normalized_duplicates_filter_binding_safety_and_denial(cli):
    good = {"items": [grant()], "next_cursor": None}
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(good).encode()
        assert invoke(cli, origin, "list").returncode == 0
        duplicate = grant() | {"id": KEY.replace("-", "")}
        malformed = [
            good | {"items": None},
            good | {"items": [None]},
            good | {"items": [grant() | {"project_id": POLICY}]},
            good | {"items": [grant(), duplicate]},
            good | {"items": [], "next_cursor": "next"},
            good | {"next_cursor": ""},
            good | {"next_cursor": "x" * 513},
            {"items": []},
            good | {"total": 1},
        ]
        for value in malformed:
            response["body"] = json.dumps(value).encode()
            assert_failure(invoke(cli, origin, "list"), "invalid_api_response")
        response["body"] = json.dumps(good).encode()
        for flags in (("--status", "revoked"), ("--role", "reviewer")):
            assert_failure(invoke(cli, origin, "list", *flags), "invalid_api_response")
        response["body"] = json.dumps(
            good | {"items": [grant(), grant() | {"id": ACTOR}]}
        ).encode()
        assert_failure(
            invoke(cli, origin, "list", "--limit", "1"), "invalid_api_response"
        )
        for action in ("list", "show"):
            value = good if action == "list" else grant()
            response["body"] = json.dumps(value).encode()
            reflected = invoke(cli, origin, action, token=POLICY.replace("-", ""))
            assert_failure(reflected, "invalid_api_response")
            response["body"] = b" " * (2 * 1024 * 1024 + 1)
            assert_failure(invoke(cli, origin, action), "invalid_api_response")
            response.update(
                status=404,
                body=json.dumps(
                    canonical_error()
                    | {
                        "error": canonical_error()["error"]
                        | {"code": "project_authorization_resource_not_found"}
                    }
                ).encode(),
            )
            denied = invoke(cli, origin, action)
            assert_failure(denied, "project_authorization_resource_not_found")
            assert "outcome_unknown" not in json.loads(denied.stderr)["error"]
            response["status"] = 200
        response.update(
            status=400,
            body=json.dumps(
                canonical_error()
                | {"error": canonical_error()["error"] | {"code": "invalid_cursor"}}
            ).encode(),
        )
        before = len(requests)
        assert_failure(
            invoke(cli, origin, "list", "--cursor", "forged"), "invalid_cursor"
        )
        assert len(requests) == before + 1
