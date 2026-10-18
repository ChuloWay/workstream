"""Built-binary HTTP proof for explicit Operator checker operations."""

from copy import deepcopy
import json
from urllib.parse import parse_qs, urlsplit

from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture
from test_contributor_task_mutations import KEY, canonical_error

ENTRY = "018f0ebc-7966-7e8d-bc4d-1cae1e000030"
RUN = "018f0ebc-7966-7e8d-bc4d-1cae1e000031"
REQUEST = "018f0ebc-7966-7e8d-bc4d-1cae1e000032"
RESULT = "018f0ebc-7966-7e8d-bc4d-1cae1e000033"
EVIDENCE = "018f0ebc-7966-7e8d-bc4d-1cae1e000034"
TASK = "018f0ebc-7966-7e8d-bc4d-1cae1e000035"
SUBMISSION = "018f0ebc-7966-7e8d-bc4d-1cae1e000036"
NEXT_REQUEST = "018f0ebc-7966-7e8d-bc4d-1cae1e000040"
NEXT_RUN = "018f0ebc-7966-7e8d-bc4d-1cae1e000041"
NEXT_RESULT = "018f0ebc-7966-7e8d-bc4d-1cae1e000042"
SHA = "sha256:" + "a" * 64


def schema(name):
    return {
        "schema_id": name,
        "schema_version": "v1",
        "document": {"type": "object", "description": "é"},
        "schema_sha256": SHA,
    }


def spec(phase="pre_submit"):
    return {
        "capability_id": "acme.safe_archive",
        "capability_version": "v1.2.3",
        "phase": phase,
        "image_digest": SHA,
        "configuration_schema": schema("acme.safe_archive.configuration"),
        "input_schema": schema(f"external_checker_{phase}_input"),
        "output_schema": schema("external_checker_result"),
        "resources": {
            "cpu_millis": 500,
            "memory_bytes": 134217728,
            "deadline_ms": 30000,
            "maximum_output_bytes": 32768,
        },
    }


def entry(value):
    return value | {
        "registry_entry_id": ENTRY,
        "entry_digest": SHA,
        "registration_operation_id": KEY,
        "registered_by_actor_profile_id": ACTOR,
        "authorization_decision_event_id": REQUEST,
        "created_at": "2026-10-18T10:00:00Z",
    }


def source():
    return {
        "project_id": PROJECT,
        "task_id": TASK,
        "submission_id": SUBMISSION,
        "submission_version": 1,
        "source_run_id": RUN,
        "source_request_id": REQUEST,
        "source_request_digest": SHA,
        "source_result_id": RESULT,
        "source_result_digest": SHA,
        "source_finalize_evidence_id": EVIDENCE,
        "source_generation": 1,
        "failure_code": "external_checker_unavailable",
    }


def successor():
    return {
        "request_id": NEXT_REQUEST,
        "request_digest": SHA,
        "run_id": NEXT_RUN,
        "result_id": NEXT_RESULT,
        "generation": 2,
        "event_id": TASK,
        "audit_event_id": SUBMISSION,
    }


def receipt():
    return {
        "receipt_id": EVIDENCE,
        "source": source(),
        "successor": successor(),
        "authorization_decision_id": ACTOR,
    }


def invoke(cli, origin, *args, output="json"):
    return cli(origin, TOKEN, "-o", output, "operations", "checker", *args)


def test_registry_registration_and_read_exact_wire_and_closed_entry(cli, tmp_path):
    path = tmp_path / "checker.json"
    with http_fixture() as (origin, response, requests):
        for phase in ("pre_submit", "post_submit"):
            value = spec(phase)
            path.write_text(json.dumps(value, ensure_ascii=False))
            response.update(status=201, body=json.dumps(entry(value)).encode())
            result = invoke(
                cli, origin, "registry", "register", "--input", str(path),
                "--idempotency-key", KEY,
            )
            assert result.returncode == 0 and json.loads(result.stdout) == entry(value), result.stderr
            assert requests[-1] == (
                "POST", "/api/v1/operations/external-checker-registry", "Bearer " + TOKEN,
            )
            assert response["commands"][-1] == ("application/json", [KEY], value)
            assert response["raw_commands"][-1] == path.read_bytes()

            response["status"] = 200
            read = invoke(cli, origin, "registry", "read", ENTRY.replace("-", ""))
            assert read.returncode == 0 and json.loads(read.stdout) == entry(value), read.stderr
            assert requests[-1] == (
                "GET", "/api/v1/operations/external-checker-registry/" + ENTRY.replace("-", ""),
                "Bearer " + TOKEN,
            )


def test_registry_refuses_local_invalid_and_response_substitution(cli, tmp_path):
    path = tmp_path / "checker.json"
    with http_fixture() as (origin, response, requests):
        for changed in (
            {"phase": "unknown"},
            {"input_schema": schema("wrong_input")},
            {"image_digest": "latest"},
            {"resources": spec()["resources"] | {"memory_bytes": 1}},
        ):
            path.write_text(json.dumps(spec() | changed))
            assert_failure(
                invoke(cli, origin, "registry", "register", "--input", str(path), "--idempotency-key", KEY),
                "invalid_arguments", 2,
            )
        assert requests == []

        value = spec()
        path.write_text(json.dumps(value))
        response.update(status=201)
        for bad in (
            entry(value) | {"registration_operation_id": ACTOR},
            entry(value) | {"image_digest": "sha256:" + "b" * 64},
            entry(value) | {"input_schema": value["input_schema"] | {"schema_sha256": "sha256:" + "b" * 64}},
            entry(value) | {"input_schema": value["input_schema"] | {"document": {"type": "array"}}},
            entry(value) | {"registry_entry_id": "00000000-0000-4000-8000-000000000001"},
            entry(value) | {"entry_digest": "latest"},
            entry(value) | {"extra": "unexpected"},
        ):
            response["body"] = json.dumps(bad).encode()
            result = invoke(cli, origin, "registry", "register", "--input", str(path), "--idempotency-key", KEY)
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
            assert "manually replay" in invoke(
                cli, origin, "registry", "register", "--input", str(path),
                "--idempotency-key", KEY, output="text",
            ).stderr

        response.update(status=200, body=json.dumps(entry(value) | {"registry_entry_id": ACTOR}).encode())
        assert_failure(invoke(cli, origin, "registry", "read", ENTRY), "invalid_api_response")


def test_registry_large_response_safe_text_and_bearer_reflection(cli, tmp_path):
    value = spec()
    for name in ("configuration_schema", "input_schema", "output_schema"):
        value[name]["document"]["description"] = "x" * 25_000 + "\u202e\u2028\u2029"
    path = tmp_path / "large-checker.json"
    path.write_text(json.dumps(value, ensure_ascii=False))
    with http_fixture() as (origin, response, requests):
        response.update(status=201, body=json.dumps(entry(value), ensure_ascii=False).encode())
        assert len(response["body"]) > 64 * 1024
        registered = invoke(
            cli, origin, "registry", "register", "--input", str(path),
            "--idempotency-key", KEY, output="text",
        )
        assert registered.returncode == 0 and registered.stderr == "", registered.stderr
        assert "\u202e" not in registered.stdout and "\\u202E" in registered.stdout
        assert len(requests) == 1

        machine = invoke(
            cli, origin, "registry", "register", "--input", str(path),
            "--idempotency-key", KEY,
        )
        assert machine.returncode == 0 and machine.stderr == "", machine.stderr
        assert json.loads(machine.stdout) == entry(value)
        assert machine.stdout.count("\n") == 1
        assert "\u2028" not in machine.stdout and "\u2029" not in machine.stdout
        assert "\\u2028" in machine.stdout and "\\u2029" in machine.stdout

        response["status"] = 200
        response["body"] = json.dumps(
            entry(value) | {"input_schema": value["input_schema"] | {
                "document": {"type": "object", "description": TOKEN},
            }},
        ).encode()
        assert_failure(invoke(cli, origin, "registry", "read", ENTRY), "invalid_api_response")


def test_registration_compares_postgres_normalized_numbers_without_integer_collapse(cli, tmp_path):
    value = spec()
    value["configuration_schema"]["document"] = {
        "type": "object", "examples": [9007199254740993, -0.0, 1e20],
    }
    path = tmp_path / "numbered-checker.json"
    path.write_text(json.dumps(value))
    with http_fixture() as (origin, response, requests):
        normalized = deepcopy(entry(value))
        normalized["configuration_schema"]["document"]["examples"] = [
            9007199254740993, 0, 100000000000000000000,
        ]
        response.update(status=201, body=json.dumps(normalized).encode())
        same_value = invoke(
            cli, origin, "registry", "register", "--input", str(path),
            "--idempotency-key", KEY,
        )
        assert same_value.returncode == 0, same_value.stderr

        changed = deepcopy(normalized)
        changed["configuration_schema"]["document"]["examples"][0] = 9007199254740992
        response["body"] = json.dumps(changed).encode()
        substituted = invoke(
            cli, origin, "registry", "register", "--input", str(path),
            "--idempotency-key", KEY,
        )
        assert_failure(substituted, "invalid_api_response")
        assert json.loads(substituted.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == 2


def test_retry_lineage_rejects_relational_substitutions_on_receipts_and_history(cli):
    historical = {
        "project_id": PROJECT,
        "items": [{
            "source": source(), "recovery_state": "retried",
            "created_at": "2026-10-18T10:00:00Z",
            "completed_at": "2026-10-18T10:01:00Z",
            "retry_receipt_id": EVIDENCE,
            "successor": successor(),
        }],
        "next_cursor": None,
    }
    with http_fixture() as (origin, response, _requests):
        response["body"] = json.dumps(historical).encode()
        assert invoke(cli, origin, "retry-sources", PROJECT).returncode == 0
        for successor_change in (
            {"generation": 1},
            {"generation": 3},
            {"request_id": REQUEST},
            {"run_id": RUN},
            {"result_id": RESULT},
            {"request_id": NEXT_RUN},
            {"run_id": RESULT},
        ):
            bad_history = deepcopy(historical)
            bad_history["items"][0]["successor"].update(successor_change)
            response["body"] = json.dumps(bad_history).encode()
            assert_failure(invoke(cli, origin, "retry-sources", PROJECT), "invalid_api_response")

            bad_receipt = receipt()
            bad_receipt["successor"].update(successor_change)
            response.update(status=201, body=json.dumps(bad_receipt).encode())
            result = invoke(cli, origin, "retry", PROJECT, RUN, "--reason", "fixed", "--idempotency-key", KEY)
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True
            response["status"] = 200


def test_retry_source_page_and_exact_reason_bound_receipt(cli):
    item = {
        "source": source(),
        "recovery_state": "eligible",
        "created_at": "2026-10-18T10:00:00Z",
        "completed_at": "2026-10-18T10:01:00Z",
        "retry_receipt_id": None,
        "successor": None,
    }
    page = {"project_id": PROJECT, "items": [item], "next_cursor": "opaque+/="}
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(page).encode()
        result = invoke(cli, origin, "retry-sources", PROJECT, "--limit", "1", "--cursor", "a+/=")
        assert result.returncode == 0 and json.loads(result.stdout) == page, result.stderr
        request = urlsplit(requests[-1][1])
        assert request.path == f"/api/v1/operations/projects/{PROJECT}/checker-retry-sources"
        assert parse_qs(request.query) == {"limit": ["1"], "cursor": ["a+/="]}
        assert requests[-1][0] == "GET"

        response.update(status=201, body=json.dumps(receipt()).encode())
        for _ in range(2):
            result = invoke(
                cli, origin, "retry", PROJECT, RUN, "--reason", "Fixed runtime é",
                "--idempotency-key", KEY,
            )
            assert result.returncode == 0 and json.loads(result.stdout) == receipt(), result.stderr
            assert requests[-1] == (
                "POST", f"/api/v1/operations/projects/{PROJECT}/checker-runs/{RUN}/retry",
                "Bearer " + TOKEN,
            )
            assert response["commands"][-1] == (
                "application/json", [KEY], {"reason": "Fixed runtime é"},
            )
        assert len(requests) == 3


def test_retry_refuses_invalid_inputs_foreign_pages_and_unknown_writes(cli):
    with http_fixture() as (origin, response, requests):
        for args in (
            ("retry-sources", "wrong"),
            ("retry-sources", PROJECT, "--limit", "0"),
            ("retry-sources", PROJECT, "--cursor", "x" * 513),
            ("retry", PROJECT, RUN, "--reason", " ", "--idempotency-key", KEY),
            ("retry", PROJECT, RUN, "--reason", "bad\nreason", "--idempotency-key", KEY),
            ("retry", PROJECT, RUN, "--reason", "x" * 501, "--idempotency-key", KEY),
            ("retry", PROJECT, RUN, "--reason", "valid", "--idempotency-key", "wrong"),
        ):
            assert_failure(invoke(cli, origin, *args), "invalid_arguments", 2)
        assert requests == []

        base = {
            "project_id": PROJECT,
            "items": [{
                "source": source(), "recovery_state": "eligible",
                "created_at": "2026-10-18T10:00:00Z", "completed_at": "2026-10-18T10:01:00Z",
                "retry_receipt_id": None, "successor": None,
            }],
            "next_cursor": None,
        }
        for bad in (
            base | {"project_id": ACTOR},
            base | {"items": [base["items"][0] | {"source": source() | {"project_id": ACTOR}}]},
            base | {"items": [base["items"][0] | {"recovery_state": "retried"}]},
            base | {"items": [base["items"][0]] * 2},
        ):
            response["body"] = json.dumps(bad).encode()
            assert_failure(invoke(cli, origin, "retry-sources", PROJECT), "invalid_api_response")

        response.update(status=201)
        for bad in (
            receipt() | {"source": source() | {"source_run_id": ACTOR}},
            receipt() | {"source": source() | {"project_id": ACTOR}},
            receipt() | {"successor": successor() | {"request_digest": "latest"}},
        ):
            response["body"] = json.dumps(bad).encode()
            result = invoke(cli, origin, "retry", PROJECT, RUN, "--reason", "fixed", "--idempotency-key", KEY)
            assert_failure(result, "invalid_api_response")
            assert json.loads(result.stderr)["error"]["outcome_unknown"] is True

        response.update(status=403, body=json.dumps(canonical_error()).encode())
        denied = invoke(cli, origin, "retry", PROJECT, RUN, "--reason", "fixed", "--idempotency-key", KEY)
        assert_failure(denied, "authorization_denied")
        assert "outcome_unknown" not in json.loads(denied.stderr)["error"]
        before = len(requests)
        response["drop"] = True
        lost = invoke(cli, origin, "retry", PROJECT, RUN, "--reason", "fixed", "--idempotency-key", KEY)
        assert_failure(lost, "service_unavailable")
        assert json.loads(lost.stderr)["error"]["outcome_unknown"] is True
        assert len(requests) == before + 1
