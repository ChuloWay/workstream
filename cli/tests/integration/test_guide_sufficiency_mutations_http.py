"""Built-process HTTP contracts for two human guide-sufficiency writes."""

import json

import pytest

from test_guide_inspection_http import GUIDE, GUIDE_PATH, REPORT, SNAPSHOT, WHEN, report
from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture

KEY = "018f0ebc-7966-7e8d-bc4d-1cae1e000029"
CREATE = ("project", "guide", "sufficiency", "create", PROJECT, GUIDE)
ACK = (
    "project", "guide", "sufficiency", "acknowledge-warnings", PROJECT, GUIDE, REPORT
)


def test_sufficiency_namespace_help_includes_the_human_writes(cli):
    result = cli("http://127.0.0.1:1", TOKEN, "project", "guide", "--help")
    assert result.returncode == 0 and result.stderr == "", result.stderr
    assert "Inspect reports, record human diagnostics, or acknowledge eligible warnings" in result.stdout
    assert "not approval or activation" in result.stdout


def input_file(tmp_path, body):
    path = tmp_path / "request.json"
    path.write_text(body, encoding="utf-8")
    return str(path)


def create_body():
    return {
        "source_snapshot_id": SNAPSHOT,
        "status": "passed_with_warnings",
        "findings": [
            {"severity": "warning", "code": "example", "message": "Check one example"}
        ],
        "summary": "Manual diagnostic",
    }


def manual_report():
    value = report()
    value.update(
        created_by=ACTOR,
        summary="Manual diagnostic",
        findings=[
            {"severity": "warning", "code": "example", "message": "Check one example", "location": None}
        ],
        setup_generation=None,
        agent_material_byte_count=None,
    )
    return value


def acknowledged_report(note):
    value = manual_report()
    value.update(
        warnings_acknowledged_by_role="project_manager",
        warnings_acknowledged_by_actor=ACTOR,
        warnings_acknowledged_at=WHEN,
        acknowledgement_note=note,
    )
    return value


@pytest.mark.parametrize(
    ("command", "path", "input_body", "response_body"),
    [
        (CREATE, GUIDE_PATH + "/sufficiency-reports", create_body(), manual_report()),
        (
            ACK,
            GUIDE_PATH + "/sufficiency-reports/" + REPORT + "/acknowledge-warnings",
            {"acknowledgement_note": "Acknowledged\n\x1b[31m"},
            acknowledged_report("Acknowledged\n\x1b[31m"),
        ),
        (ACK, GUIDE_PATH + "/sufficiency-reports/" + REPORT + "/acknowledge-warnings", {}, acknowledged_report(None)),
    ],
)
def test_exact_single_write_json_and_escaped_text(cli, tmp_path, command, path, input_body, response_body):
    request_bytes = json.dumps(input_body, ensure_ascii=False).encode()
    input_path = input_file(tmp_path, request_bytes.decode())
    with http_fixture() as (origin, response, requests):
        response.update(status=201 if command == CREATE else 200,
                        body=json.dumps(response_body, ensure_ascii=False).encode())
        result = cli(origin, TOKEN, *command, "--input", input_path, "--idempotency-key", KEY, "-o", "json")
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert json.loads(result.stdout) == response_body
        assert response["raw_commands"] == [request_bytes]
        assert requests == [("POST", path, "Bearer " + TOKEN)]
        headers = response["request_headers"][0]
        assert headers["Idempotency-Key"] == KEY
        assert headers["Content-Type"] == "application/json"
        text = cli(origin, TOKEN, *command, "--input", input_path, "--idempotency-key", KEY)
        assert text.returncode == 0 and text.stderr == "", text.stderr
        assert "\x1b" not in text.stdout and "\u202e" not in text.stdout
        assert len(requests) == 2


@pytest.mark.parametrize(
    ("command", "body"),
    [
        (CREATE, {"status": "passed", "findings": []}),
        (CREATE, {"source_snapshot_id": "bad", "status": "passed"}),
        (CREATE, {"source_snapshot_id": SNAPSHOT, "status": "approved"}),
        (CREATE, {"source_snapshot_id": SNAPSHOT, "status": "passed", "findings": None}),
        (CREATE, {"source_snapshot_id": SNAPSHOT, "status": "passed", "findings": [{}]}),
        (CREATE, {"source_snapshot_id": SNAPSHOT, "status": "passed", "agent_name": "fabricated"}),
        (ACK, {"acknowledgement_note": 42}),
        (ACK, {"acknowledgement_note": "x" * 1001}),
        (ACK, {"agent_name": "fabricated"}),
    ],
)
def test_invalid_input_never_sends_a_write(cli, tmp_path, command, body):
    with http_fixture() as (origin, response, requests):
        path = input_file(tmp_path, json.dumps(body))
        result = cli(origin, TOKEN, *command, "--input", path, "--idempotency-key", KEY, "-o", "json")
        assert_failure(result, "invalid_arguments", exit_code=2)
        assert requests == [] and response["commands"] == []


@pytest.mark.parametrize("command", [CREATE, ACK])
def test_invalid_selector_or_key_never_sends_write(cli, tmp_path, command):
    path = input_file(tmp_path, json.dumps(create_body() if command == CREATE else {}))
    with http_fixture() as (origin, response, requests):
        for args, key in ((command, "bad"), (command[:-1] + ("bad",), KEY)):
            result = cli(origin, TOKEN, *args, "--input", path, "--idempotency-key", key, "-o", "json")
            assert_failure(result, "invalid_arguments", exit_code=2)
        assert requests == [] and response["commands"] == []


def test_oversized_input_never_sends_write(cli, tmp_path):
    path = input_file(tmp_path, json.dumps(create_body()) + " " * (1024 * 1024))
    with http_fixture() as (origin, response, requests):
        result = cli(origin, TOKEN, *CREATE, "--input", path, "--idempotency-key", KEY, "-o", "json")
        assert_failure(result, "invalid_arguments", exit_code=2)
        assert requests == [] and response["commands"] == []


@pytest.mark.parametrize("command", [CREATE, ACK])
def test_mismatched_or_malformed_success_is_uncertain_without_replay(cli, tmp_path, command):
    body = create_body() if command == CREATE else {"acknowledgement_note": "Acknowledged"}
    path = input_file(tmp_path, json.dumps(body))
    valid = manual_report() if command == CREATE else acknowledged_report("Acknowledged")
    variants = [
        valid | {"project_id": ACTOR},
        valid | {"source_snapshot_id": ACTOR} if command == CREATE else valid | {"id": ACTOR},
        valid | {"findings": None},
        valid | {"summary": TOKEN},
    ]
    if command == ACK:
        variants.extend((valid | {"warnings_acknowledged_at": None}, valid | {"acknowledgement_note": "different"}))
    else:
        variants.extend((
            valid | {"status": "passed"},
            valid | {"project_setup_run_id": ACTOR},
            valid | {"findings": [{"severity": "warning", "code": "changed", "message": "Different"}]},
        ))
    with http_fixture() as (origin, response, requests):
        response["status"] = 201 if command == CREATE else 200
        for value in variants:
            response["body"] = json.dumps(value).encode()
            result = cli(origin, TOKEN, *command, "--input", path, "--idempotency-key", KEY, "-o", "json")
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == len(variants) and all(method == "POST" for method, *_ in requests)
        text = cli(origin, TOKEN, *command, "--input", path, "--idempotency-key", KEY)
        assert text.returncode == 1 and "manually replay" in text.stderr
        assert len(requests) == len(variants) + 1


def test_structured_backend_denial_is_not_a_local_authority_decision(cli, tmp_path):
    path = input_file(tmp_path, json.dumps(create_body()))
    with http_fixture() as (origin, response, requests):
        response.update(status=404, body=json.dumps({"error": {"code": "project_authorization_resource_not_found", "message": TOKEN}}).encode())
        result = cli(origin, TOKEN, *CREATE, "--input", path, "--idempotency-key", KEY, "-o", "json")
        assert_failure(result, "project_authorization_resource_not_found")
        assert TOKEN not in result.stderr
        assert requests == [("POST", GUIDE_PATH + "/sufficiency-reports", "Bearer " + TOKEN)]


def test_compiled_warning_refusal_is_forwarded_as_canonical_backend_conflict(cli, tmp_path):
    path = input_file(tmp_path, json.dumps({"acknowledgement_note": "Not an approval"}))
    with http_fixture() as (origin, response, requests):
        response.update(status=409, body=json.dumps({
            "error": {"code": "project_setup_run_context_mismatch", "message": "Setup custody disagrees"}
        }).encode())
        result = cli(origin, TOKEN, *ACK, "--input", path, "--idempotency-key", KEY, "-o", "json")
        assert_failure(result, "project_setup_run_context_mismatch")
        assert json.loads(result.stderr)["error"]["status"] == 409
        assert requests == [("POST", GUIDE_PATH + "/sufficiency-reports/" + REPORT +
                             "/acknowledge-warnings", "Bearer " + TOKEN)]
