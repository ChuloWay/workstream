"""Built-binary proof of the three distinct public Operator task contracts."""

from copy import deepcopy
import json
from urllib.parse import quote

from http2_fixture import goaway_fixture
from test_contributor_task_mutations import KEY, TASK_RESPONSE, canonical_error
from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture
from test_task_context_http import REVISION_LINEAGE
from test_task_http_boundary import TASK

SUMMARY = {
    "task_id": TASK,
    "project_id": PROJECT,
    "status": "claimed",
    "created_at": "2026-10-01T00:00:00Z",
    "updated_at": "2026-10-02T00:00:00Z",
}
CONTEXT = {"task_id": TASK, "project_id": PROJECT} | REVISION_LINEAGE
STARTED = TASK_RESPONSE | {"status": "in_progress"}


def invoke(cli, origin, *args, output="json"):
    return cli(origin, TOKEN, "-o", output, "operations", "task", *args)


def test_operator_reads_use_only_exact_restricted_routes_and_projection(cli):
    with http_fixture() as (origin, response, requests):
        page = {"project_id": PROJECT, "items": [SUMMARY], "next_cursor": "opaque-1"}
        response["body"] = json.dumps(page).encode()
        result = invoke(cli, origin, "list", PROJECT, "--limit", "1")
        assert result.returncode == 0 and json.loads(result.stdout) == page
        assert requests[-1] == (
            "GET",
            f"/api/v1/operations/projects/{PROJECT}/tasks?limit=1",
            "Bearer " + TOKEN,
        )
        result = invoke(
            cli,
            origin,
            "list",
            PROJECT,
            "--limit",
            "1",
            "--cursor",
            "opaque-1",
            output="text",
        )
        assert result.returncode == 0 and result.stderr == ""
        assert result.stdout == (
            f"Project: {PROJECT}\nOperator tasks: 1\nTask: {TASK}\nProject: {PROJECT}\n"
            "Status: claimed\nCreated: 2026-10-01T00:00:00Z\n"
            "Updated: 2026-10-02T00:00:00Z\n"
            "Next cursor (observation, not authority): opaque-1\n"
        )
        assert requests[-1] == (
            "GET",
            f"/api/v1/operations/projects/{PROJECT}/tasks?cursor=opaque-1&limit=1",
            "Bearer " + TOKEN,
        )
        response["body"] = json.dumps(CONTEXT).encode()
        for project, task in (
            (PROJECT, TASK),
            (PROJECT.replace("-", ""), "{" + TASK + "}"),
        ):
            result = invoke(cli, origin, "locked-context", project, task)
            assert result.returncode == 0 and result.stderr == ""
            assert json.loads(result.stdout) == CONTEXT
            assert requests[-1] == (
                "GET",
                f"/api/v1/operations/projects/{project}/tasks/{quote(task, safe=':')}/locked-context",
                "Bearer " + TOKEN,
            )
        result = invoke(cli, origin, "locked-context", PROJECT, TASK, output="text")
        assert result.returncode == 0 and result.stderr == ""
        assert result.stdout.startswith(
            "Operator locked context (references only; not start authority): {"
        )
        assert '"locked_post_submit_checker_policy_hash"' in result.stdout
        assert "policy_body" not in result.stdout
        assert len(requests) == 5  # One public request per invocation; no preflight.


def test_operator_reads_reject_substituted_or_malformed_success(cli):
    with http_fixture() as (origin, response, requests):
        page = {"project_id": PROJECT, "items": [SUMMARY], "next_cursor": None}
        bad_pages = [
            page | {"project_id": ACTOR},
            page | {"items": [SUMMARY, SUMMARY]},
            page | {"items": [SUMMARY | {"project_id": ACTOR}]},
            page | {"items": [SUMMARY | {"title": "manager-only"}]},
            page | {"items": [SUMMARY | {"status": "unknown"}]},
            page | {"items": [SUMMARY | {"updated_at": "bad"}]},
            page | {"items": [], "next_cursor": "opaque"},
            page | {"next_cursor": ""},
            page | {"extra": True},
        ]
        for field in SUMMARY:
            item = deepcopy(SUMMARY)
            del item[field]
            bad_pages.append(page | {"items": [item]})
        for body in bad_pages:
            response["body"] = json.dumps(body).encode()
            assert_failure(invoke(cli, origin, "list", PROJECT), "invalid_api_response")

        bad_contexts = [
            CONTEXT | {"project_id": ACTOR},
            CONTEXT | {"task_id": ACTOR},
            CONTEXT | {"locked_review_policy_generation": 0},
            CONTEXT | {"locked_review_policy_generation": -1},
            CONTEXT | {"locked_review_policy_generation": "1"},
            CONTEXT | {"locked_review_policy_generation": 1.5},
            CONTEXT | {"locked_revision_policy_generation": None},
            CONTEXT | {"locked_post_submit_checker_policy_hash": "bad"},
            CONTEXT | {"locked_contribution_policy_version_id": "bad"},
            CONTEXT | {"policy_body": {"private": True}},
        ]
        for field in CONTEXT:
            body = deepcopy(CONTEXT)
            del body[field]
            bad_contexts.append(body)
        for body in bad_contexts:
            response["body"] = json.dumps(body).encode()
            assert_failure(
                invoke(cli, origin, "locked-context", PROJECT, TASK),
                "invalid_api_response",
            )
        response["body"] = json.dumps(
            CONTEXT
            | {
                "locked_review_policy_generation": 2**100,
                "locked_revision_policy_generation": 2**100,
            }
        ).encode()
        accepted = invoke(cli, origin, "locked-context", PROJECT, TASK)
        assert accepted.returncode == 0, accepted.stderr
        assert json.loads(accepted.stdout)["locked_review_policy_generation"] == 2**100
        assert len(requests) == len(bad_pages) + len(bad_contexts) + 1


def test_operator_start_is_explicit_one_write_and_exact_manual_replay_shape(cli):
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(STARTED).encode()
        for selector in (TASK, TASK.replace("-", ""), "{" + TASK + "}"):
            result = invoke(
                cli,
                origin,
                "start",
                selector,
                "--reason",
                "Verified assignee",
                "--idempotency-key",
                KEY,
            )
            assert result.returncode == 0 and json.loads(result.stdout) == STARTED
            assert requests[-1] == (
                "POST",
                f"/api/v1/operations/tasks/{quote(selector, safe=':')}/start",
                "Bearer " + TOKEN,
            )
            assert response["commands"][-1] == (
                "application/json",
                [KEY],
                {"reason": "Verified assignee"},
            )
        result = invoke(
            cli,
            origin,
            "start",
            TASK,
            "--reason",
            "é" * 1000,
            "--idempotency-key",
            KEY,
            output="text",
        )
        assert result.returncode == 0 and "Status: in_progress\n" in result.stdout
        assert "\x1b" not in result.stdout
        assert len(requests) == 4


def test_operator_start_local_invalid_arguments_never_fall_back_or_send(cli):
    with http_fixture() as (origin, _response, requests):
        cases = (
            ("start", TASK, "--idempotency-key", KEY),
            ("start", TASK, "--reason", "ready"),
            ("start", TASK, "--reason", " ", "--idempotency-key", KEY),
            ("start", TASK, "--reason", "é" * 1001, "--idempotency-key", KEY),
            ("start", "bad", "--reason", "ready", "--idempotency-key", KEY),
            ("start", TASK, "--reason", "ready", "--idempotency-key", "bad"),
            ("list", "bad"),
            ("list", PROJECT, "--limit", "0"),
            ("list", PROJECT, "--cursor", ""),
            ("locked-context", "bad", TASK),
            ("locked-context", PROJECT, "bad"),
        )
        for args in cases:
            assert_failure(invoke(cli, origin, *args), "invalid_arguments", 2)
        assert requests == []


def test_operator_start_denial_replay_conflict_and_unknown_are_distinct(cli):
    with http_fixture() as (origin, response, requests):
        for status, code in (
            (403, "authorization_denied"),
            (409, "idempotency_mismatch"),
            (422, "validation_error"),
        ):
            response.update(
                status=status, body=json.dumps(canonical_error(code)).encode()
            )
            result = invoke(
                cli,
                origin,
                "start",
                TASK,
                "--reason",
                "Verified",
                "--idempotency-key",
                KEY,
            )
            assert result.returncode == 1 and result.stdout == ""
            assert (
                json.loads(result.stderr)["error"].get("outcome_unknown", False)
                is False
            )
            assert json.loads(result.stderr)["error"]["code"] == code
        response.update(status=200, body=json.dumps(STARTED | {"id": ACTOR}).encode())
        result = invoke(
            cli,
            origin,
            "start",
            TASK,
            "--reason",
            "Verified",
            "--idempotency-key",
            KEY,
            output="text",
        )
        assert (
            result.returncode == 1 and "Operator start outcome unknown" in result.stderr
        )
        response.update(
            status=200, body=json.dumps(STARTED | {"title": TOKEN}).encode()
        )
        reflected = invoke(
            cli, origin, "start", TASK, "--reason", "Verified", "--idempotency-key", KEY
        )
        assert_failure(reflected, "invalid_api_response")
        assert TOKEN not in reflected.stdout + reflected.stderr
        response.update(status=408, body=b"{}")
        result = invoke(
            cli, origin, "start", TASK, "--reason", "Verified", "--idempotency-key", KEY
        )
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        response.update(status=200, drop=True)
        result = invoke(
            cli, origin, "start", TASK, "--reason", "Verified", "--idempotency-key", KEY
        )
        assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert (
            len(requests) == 7
        )  # Never automatically retries or selects contributor start.
        assert all(
            path.startswith("/api/v1/operations/tasks/") for _, path, _ in requests
        )


def test_operator_start_http2_goaway_does_not_replay(cli, tmp_path):
    with goaway_fixture(tmp_path) as (origin, environment, bodies, connections):
        result = cli(
            origin,
            TOKEN,
            "operations",
            "task",
            "start",
            TASK,
            "--reason",
            "Verified",
            "--idempotency-key",
            KEY,
            "-o",
            "json",
            extra_env=environment,
        )
    assert result.returncode == 1 and result.stdout == ""
    assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
    assert connections == ["h2"] and bodies == [b'{"reason":"Verified"}']
