"""Built-binary proof of the two exact public Audit Authority task reads."""

import json
from urllib.parse import parse_qs, urlsplit

from test_http_boundary import PROJECT, TOKEN, assert_failure, http_fixture

TASK = "018f0ebc-7966-7e8d-bc4d-1cae1e000003"
EVENT = "018f0ebc-7966-7e8d-bc4d-1cae1e000004"
DECISION = "018f0ebc-7966-7e8d-bc4d-1cae1e000005"
TIME = "2026-10-01T00:00:00Z"
HASH = "sha256:" + "a" * 64
BASE = f"/api/v1/audit/projects/{PROJECT}/tasks/{TASK}"

LOCKED = {
    "task_id": TASK,
    "project_id": PROJECT,
    "locked_guide_version": "v1",
    "locked_guide_source_snapshot_id": EVENT,
    "locked_guide_source_snapshot_hash": HASH,
    "locked_effective_project_submission_artifact_policy_id": EVENT,
    "locked_effective_project_submission_artifact_policy_hash": HASH,
    "locked_pre_submit_checker_policy_id": EVENT,
    "locked_pre_submit_checker_bundle_hash": HASH,
    "locked_post_submit_checker_policy_id": EVENT,
    "locked_post_submit_checker_policy_version": "v1",
    "locked_post_submit_checker_policy_hash": HASH,
    "locked_review_policy_id": EVENT,
    "locked_review_policy_generation": 2**80,
    "locked_review_policy_hash": HASH,
    "locked_revision_policy_id": EVENT,
    "locked_revision_policy_generation": 1,
    "locked_revision_policy_hash": HASH,
    "locked_contribution_policy_version_id": EVENT,
}
ITEM = {
    "event_id": EVENT,
    "event_type": "TaskCreated",
    "from_status": None,
    "to_status": "draft",
    "actor_id": "actor-\u202e\x1b[31m",
    "created_at": TIME,
    "assignment_id": None,
    "authorization_decision_id": DECISION,
}
CURSOR = {"project_id": PROJECT, "task_id": TASK, "created_at": TIME, "event_id": EVENT}
PAGE = {"project_id": PROJECT, "task_id": TASK, "items": [ITEM], "next_cursor": CURSOR}


def locked(cli, origin, output="json"):
    return cli(origin, TOKEN, "audit", "task", "locked-context", PROJECT, TASK, "-o", output)


def evidence(cli, origin, *flags, output="json"):
    return cli(origin, TOKEN, "audit", "task", "evidence", PROJECT, TASK, *flags, "-o", output)


def test_audit_reads_use_exact_routes_and_safe_complete_output(cli):
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(LOCKED).encode()
        result = locked(cli, origin)
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert json.loads(result.stdout) == LOCKED
        assert str(2**80) in result.stdout
        assert requests == [("GET", BASE + "/locked-context", "Bearer " + TOKEN)]

        response["body"] = json.dumps(PAGE, ensure_ascii=False).encode()
        result = evidence(cli, origin, "--limit", "1")
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert json.loads(result.stdout) == PAGE
        assert "\u202e" not in result.stdout and "\\u202e" in result.stdout
        assert requests[-1] == ("GET", BASE + "/evidence?limit=1", "Bearer " + TOKEN)

        text = evidence(cli, origin, output="text")
        assert text.returncode == 0 and text.stderr == "", text.stderr
        assert "Event: " in text.stdout and "Next cursor: " in text.stdout
        assert "\u202e" not in text.stdout and "\\u202e" in text.stdout.lower()
        assert "\x1b" not in text.stdout

        selected = json.dumps(CURSOR, separators=(",", ":"))
        response["body"] = json.dumps(PAGE | {"items": [], "next_cursor": None}).encode()
        continued = evidence(cli, origin, "--limit", "1", "--cursor", selected)
        assert continued.returncode == 0 and continued.stderr == "", continued.stderr
        assert json.loads(continued.stdout)["items"] == []
        parts = urlsplit(requests[-1][1])
        assert parts.path == BASE + "/evidence"
        assert parse_qs(parts.query) == {"limit": ["1"], "cursor": [selected]}


def test_audit_context_rejects_non_audit_or_malformed_projection(cli):
    malformed = (
        LOCKED | {"project_id": TASK},
        LOCKED | {"task_id": PROJECT},
        LOCKED | {"locked_guide_version": " "},
        LOCKED | {"locked_review_policy_generation": 0},
        LOCKED | {"locked_revision_policy_generation": -1},
        LOCKED | {"locked_review_policy_generation": 1.5},
        LOCKED | {"locked_review_policy_generation": None},
        LOCKED | {"locked_pre_submit_checker_bundle_hash": "sha256:wrong"},
        LOCKED | {"locked_guide_source_snapshot_id": "not-a-uuid"},
        LOCKED | {"locked_post_submit_checker_policy_body_summary": {}},
        LOCKED | {"locked_guide_version": TOKEN},
        {key: value for key, value in LOCKED.items() if key != "locked_review_policy_hash"},
    )
    with http_fixture() as (origin, response, _requests):
        for value in malformed:
            response["body"] = json.dumps(value).encode()
            assert_failure(locked(cli, origin), "invalid_api_response")


def test_audit_evidence_rejects_malformed_scope_events_and_cursor(cli):
    malformed = (
        PAGE | {"project_id": TASK},
        PAGE | {"task_id": PROJECT},
        PAGE | {"items": None},
        PAGE | {"items": [ITEM | {"event_id": "bad"}]},
        PAGE | {"items": [ITEM | {"created_at": "not-aware"}]},
        PAGE | {"items": [ITEM | {"assignment_id": EVENT}]},
        PAGE | {"items": [ITEM | {"authorization_decision_id": None}]},
        PAGE | {"items": [ITEM | {"from_status": 1}]},
        PAGE | {"items": [{key: value for key, value in ITEM.items() if key != "to_status"}]},
        PAGE | {"items": [ITEM, ITEM]},
        PAGE | {"items": [], "next_cursor": CURSOR},
        PAGE | {"next_cursor": CURSOR | {"task_id": PROJECT}},
        PAGE | {"next_cursor": CURSOR | {"event_id": DECISION}},
        PAGE | {"next_cursor": CURSOR | {"created_at": "2026-10-02T00:00:00Z"}},
        PAGE | {"next_cursor": CURSOR | {"extra": "private"}},
        PAGE | {"next_cursor": "opaque"},
        PAGE | {"items": [ITEM | {"actor_id": TOKEN}]},
        {key: value for key, value in PAGE.items() if key != "next_cursor"},
    )
    with http_fixture() as (origin, response, _requests):
        for value in malformed:
            response["body"] = json.dumps(value).encode()
            assert_failure(evidence(cli, origin), "invalid_api_response")
        response["body"] = json.dumps(PAGE).encode()
        assert_failure(evidence(cli, origin, "--limit", "0"), "invalid_arguments", 2)
        assert_failure(evidence(cli, origin, "--limit", "101"), "invalid_arguments", 2)


def test_audit_cursor_is_exact_scoped_json_and_bad_inputs_never_dispatch(cli):
    bad = (
        "",
        "opaque",
        json.dumps(CURSOR | {"project_id": TASK}),
        json.dumps(CURSOR | {"task_id": PROJECT}),
        json.dumps(CURSOR | {"created_at": "2026-10-01"}),
        json.dumps(CURSOR | {"event_id": "bad"}),
        json.dumps(CURSOR | {"extra": "private"}),
        '{"project_id":"%s","project_id":"%s","task_id":"%s","created_at":"%s","event_id":"%s"}'
        % (PROJECT, PROJECT, TASK, TIME, EVENT),
        "x" * 513,
    )
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(PAGE).encode()
        for cursor in bad:
            assert_failure(evidence(cli, origin, "--cursor", cursor), "invalid_arguments", 2)
        assert requests == []
        bad_project = cli(origin, TOKEN, "audit", "task", "evidence", TASK, "bad", "-o", "json")
        assert_failure(bad_project, "invalid_arguments", 2)
        assert requests == []


def test_audit_denial_and_body_limit_do_not_disclose_or_partially_print(cli):
    with http_fixture() as (origin, response, _requests):
        response["status"] = 404
        response["body"] = b'{"error":{"code":"project_authorization_resource_not_found"}}'
        for call in (locked, evidence):
            result = call(cli, origin)
            assert_failure(result, "project_authorization_resource_not_found")
            assert result.stdout == "" and TOKEN not in result.stderr
        response["status"] = 200
        response["body"] = b" " * (2 * 1024 * 1024 + 1)
        for call in (locked, evidence):
            assert_failure(call(cli, origin), "invalid_api_response")
