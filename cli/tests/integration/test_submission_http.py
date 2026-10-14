"""Submission commands through the built process and hostile HTTP peers."""

import copy
import json
from urllib.parse import parse_qs, urlsplit

from test_http_boundary import TOKEN, assert_failure, http_fixture
from http2_fixture import goaway_fixture

TASK = "018f0ebc-7966-7e8d-bc4d-1cae1e000010"
ASSIGNMENT = "018f0ebc-7966-7e8d-bc4d-1cae1e000011"
KEY = "018f0ebc-7966-7e8d-bc4d-1cae1e000012"
PUT = "018f0ebc-7966-7e8d-bc4d-1cae1e000013"
ADMISSION = "018f0ebc-7966-7e8d-bc4d-1cae1e000014"
SUBMISSION = "018f0ebc-7966-7e8d-bc4d-1cae1e000015"
RUN = "018f0ebc-7966-7e8d-bc4d-1cae1e000016"
RECEIPT = {"submission_id": SUBMISSION, "submission_version": 1,
           "admission_id": ADMISSION, "evaluation_request_id": RUN}
HISTORY = {
    "id": SUBMISSION, "task_id": TASK, "version": 1, "status": "submitted",
    "summary": "Work complete", "submitted_at": "2026-10-14T10:00:00Z",
    "locked_at": None, "supersedes_submission_id": None, "evidence_items": [],
}
CHECKER = {
    "id": RUN, "task_id": TASK, "submission_id": SUBMISSION,
    "submission_version": 1, "status": "completed", "attempt_number": 1,
    "supersedes_checker_run_id": None, "is_current_for_submission": True,
    "created_at": "2026-10-14T10:00:00Z", "completed_at": "2026-10-14T10:01:00Z",
    "results": [{"id": KEY, "checker_name": "quality", "status": "failed",
                 "severity": "error", "worker_message": "Fix \u202eunsafe\x1b text",
                 "worker_suggested_fix": "Correct the output"}],
}


def prepare_args(path):
    return ("task", "prepare", TASK, "--assignment", ASSIGNMENT, "--file", str(path),
            "--idempotency-key", KEY, "-o", "json")


def submit_args():
    return ("task", "submit", TASK, "--assignment", ASSIGNMENT,
            "--admission", ADMISSION, "-o", "json")


def preparation(status="stored_pending_verification"):
    return {"put_attempt_id": PUT, "admission_id": ADMISSION if status == "ready" else None,
            "submission_bundle_preparation_status": status, "replayed": status == "ready"}


def respond(response, value, status=200):
    response.update(status=status, body=json.dumps(value, ensure_ascii=False).encode())


def test_explicit_prepare_replay_then_create_preserves_packet_and_bytes(cli, tmp_path):
    path = tmp_path / "submission.zip"
    path.write_bytes(b"PK\x03\x04exact-archive")
    packet = ("--summary", "Completed work", "--attestation", "")
    with http_fixture() as (origin, response, requests):
        for status in ("stored_pending_verification", "ready"):
            respond(response, preparation(status), 202)
            result = cli(origin, TOKEN, *prepare_args(path), *packet)
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout) == preparation(status)
        assert len(requests) == 2
        assert response["raw_commands"] == [path.read_bytes()] * 2
        for headers in response["request_headers"]:
            assert headers["X-Task-Assignment-Id"] == ASSIGNMENT
            assert headers["X-Submission-Summary"] == "Completed work"
            assert headers["X-Contributor-Attestation"] == ""
            assert headers["Idempotency-Key"] == KEY
            assert headers["Content-Type"] == "application/zip"
        respond(response, RECEIPT, 201)
        for _ in range(2):
            result = cli(origin, TOKEN, *submit_args(), *packet)
            assert result.returncode == 0 and json.loads(result.stdout) == RECEIPT
        assert len(requests) == 4  # Caller explicitly replayed; CLI never did.
        assert response["commands"][-1] == ("application/json", None, {
            "assignment_id": ASSIGNMENT, "admission_id": ADMISSION,
            "summary": "Completed work", "contributor_attestation": "",
        })
        assert requests[-1] == ("POST", f"/api/v1/tasks/{TASK}/submissions", "Bearer " + TOKEN)


def test_prepare_rejects_untransportable_packet_before_request(cli, tmp_path):
    path = tmp_path / "submission.zip"
    path.write_bytes(b"zip")
    with http_fixture() as (origin, _, requests):
        for summary in ("é", "line\nbreak", " leading", "trailing ", "x" * 65537):
            result = cli(origin, TOKEN, *prepare_args(path), "--summary", summary)
            assert_failure(result, "invalid_arguments", 2)
        assert requests == []


def test_prepare_detects_file_change_and_never_confirms_success(cli, tmp_path):
    path = tmp_path / "submission.zip"
    for changed in (b"original-appended", b"modified"):
        path.write_bytes(b"original")
        with http_fixture() as (origin, response, requests):
            respond(response, preparation(), 202)
            response["after_body"] = lambda: path.write_bytes(changed)
            result = cli(origin, TOKEN, *prepare_args(path))
            assert_failure(result, "submission_source_changed")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
            assert len(requests) == 1


def test_submission_uncertain_responses_are_not_retried(cli, tmp_path):
    path = tmp_path / "submission.zip"
    path.write_bytes(b"zip")
    with http_fixture() as (origin, response, requests):
        for args in (prepare_args(path), submit_args()):
            for drop, status, body in ((True, 200, {}), (False, 503, {}), (False, 409, {
                "error": {"code": "conflict", "message": "conflict", "details": None,
                          "correlation_id": RUN, "retryable": False},
            })):
                response["drop"] = drop
                respond(response, body, status)
                before = len(requests)
                result = cli(origin, TOKEN, *args)
                assert result.returncode == 1 and result.stdout == ""
                failure = json.loads(result.stderr)["error"]
                assert failure["outcome_unknown"] is True
                assert len(requests) == before + 1


def test_submission_receipts_fail_closed_but_preserve_uuid_identity_and_large_versions(cli):
    with http_fixture() as (origin, response, requests):
        valid = RECEIPT | {"admission_id": ADMISSION.replace("-", ""), "submission_version": 2**80}
        respond(response, valid, 201)
        result = cli(origin, TOKEN, *submit_args())
        assert result.returncode == 0 and json.loads(result.stdout) == valid
        for change in ({"admission_id": KEY}, {"submission_version": None},
                       {"submission_version": 0}, {"submission_id": "bad"},
                       {"evaluation_request_id": None}, {"internal_url": "private"}):
            respond(response, RECEIPT | change, 201)
            result = cli(origin, TOKEN, *submit_args())
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == 7


def test_submission_posts_are_not_replayed_after_http2_goaway(cli, tmp_path):
    path = tmp_path / "submission.zip"
    path.write_bytes(b"zip-bytes")
    for args, expected in ((prepare_args(path), path.read_bytes()), (submit_args(), None)):
        with goaway_fixture(tmp_path) as (origin, env, bodies, connections):
            result = cli(origin, TOKEN, *args, extra_env=env)
            assert_failure(result, "service_unavailable")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
            assert connections == ["h2"] and len(bodies) == 1
            if expected is not None:
                assert bodies == [expected]
            else:
                assert json.loads(bodies[0]) == {"assignment_id": ASSIGNMENT, "admission_id": ADMISSION}


def test_preparation_feedback_is_closed_safe_and_not_a_submission(cli, tmp_path):
    path = tmp_path / "submission.zip"
    path.write_bytes(b"zip")
    details = {"status": "failed", "eligible_to_submit": False, "results": [{
        "source": "project_external_checker", "requirement_id": "quality",
        "registry_entry_id": RUN, "registry_entry_digest": "sha256:" + "a" * 64,
        "status": "failed", "findings": [{"code": "quality", "level": "error",
            "message": "Fix \u202eunsafe\x1b text", "path": "../../not-a-local-file"}],
    }]}
    envelope = {"error": {"code": "pre_submission_checker_failed", "message": "blocked",
        "details": details, "correlation_id": RUN, "retryable": False}}
    with http_fixture() as (origin, response, requests):
        respond(response, envelope, 422)
        result = cli(origin, TOKEN, *prepare_args(path))
        assert_failure(result, "pre_submission_checker_failed")
        error = json.loads(result.stderr)["error"]
        assert error["details"] == details and not error.get("outcome_unknown", False)
        assert "\u202e" not in result.stderr and "\x1b" not in result.stderr
        for invalid in (details | {"storage_key": "secret"}, details | {"results": [None]},
                        details | {"eligible_to_submit": True}):
            respond(response, {"error": envelope["error"] | {"details": invalid}}, 422)
            assert_failure(cli(origin, TOKEN, *prepare_args(path)), "invalid_api_response")
        reflected = copy.deepcopy(envelope)
        reflected["error"]["details"]["results"][0]["findings"][0]["message"] = TOKEN
        respond(response, reflected, 422)
        assert_failure(cli(origin, TOKEN, *prepare_args(path)), "invalid_api_response")
        assert len(requests) == 5


def test_submission_history_and_findings_are_bounded_and_preserve_evidence(cli):
    with http_fixture() as (origin, response, requests):
        respond(response, HISTORY)
        result = cli(origin, TOKEN, "submission", "show", SUBMISSION, "-o", "json")
        assert result.returncode == 0 and json.loads(result.stdout) == HISTORY
        page = {"items": [HISTORY], "next_cursor": "next-page"}
        respond(response, page)
        result = cli(origin, TOKEN, "task", "submissions", TASK, "--limit", "1", "-o", "json")
        assert result.returncode == 0 and json.loads(result.stdout) == page
        respond(response, {"items": [CHECKER], "next_cursor": None})
        result = cli(origin, TOKEN, "submission", "findings", SUBMISSION,
                     "--limit", "1", "--cursor", "previous", "-o", "json")
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["items"] == [CHECKER]
        assert "\u202e" not in result.stdout and "\x1b" not in result.stdout
        assert parse_qs(urlsplit(requests[-1][1]).query) == {"limit": ["1"], "cursor": ["previous"]}
        respond(response, CHECKER)
        result = cli(origin, TOKEN, "submission", "findings", SUBMISSION, "--run", RUN, "-o", "json")
        assert result.returncode == 0 and json.loads(result.stdout) == CHECKER
        assert requests[-1][1] == f"/api/v1/submissions/{SUBMISSION}/checker-runs/{RUN}"
        assert len(requests) == 4


def test_submission_reads_reject_substitution_private_fields_and_duplicate_identity(cli):
    with http_fixture() as (origin, response, _):
        for change in ({"id": KEY}, {"task_id": "bad"}, {"evidence_items": [None]},
                       {"locked_at": "bad"}, {"storage_key": "private"}):
            respond(response, HISTORY | change)
            assert_failure(cli(origin, TOKEN, "submission", "show", SUBMISSION, "-o", "json"), "invalid_api_response")
        for items in ([HISTORY, HISTORY | {"id": SUBMISSION.replace("-", "")}],
                      [HISTORY | {"task_id": KEY}]):
            respond(response, {"items": items, "next_cursor": None})
            assert_failure(cli(origin, TOKEN, "task", "submissions", TASK, "-o", "json"), "invalid_api_response")
        for change in ({"submission_id": KEY}, {"id": KEY}, {"results": [None]},
                       {"attempt_number": None}, {"raw_output": "private"}):
            respond(response, CHECKER | change)
            assert_failure(cli(origin, TOKEN, "submission", "findings", SUBMISSION, "--run", RUN, "-o", "json"), "invalid_api_response")
