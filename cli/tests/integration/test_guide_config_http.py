"""Built CLI process proof for draft-guide and exact policy writes."""

import json

from http2_fixture import goaway_fixture
from test_contributor_task_mutations import KEY, canonical_error
from test_guide_create_http import GUIDE, receipt
from test_http_boundary import PROFILE, PROJECT, TOKEN, assert_failure, http_fixture

POLICY = "018f0ebc-7966-7e8d-bc4d-1cae1e000030"
HASH = "sha256:" + "a" * 64
LARGE = 2**80 + 17


def guide_reply(summary=None):
    value = receipt()
    del value["documents"]
    del value["setup"]
    value["change_summary"] = summary
    return value


def review_body():
    return {
        "review_preference_window_seconds": LARGE,
        "review_lease_duration_seconds": 1800,
        "human_review_required": False,
        "minimum_finding_fields": ["issue", "required_fix"],
    }


def review_reply(body=None, generation=1, predecessor=None):
    body = body or review_body()
    return {
        "id": POLICY,
        "project_id": PROJECT,
        "guide_version": receipt()["version"],
        "policy_generation": generation,
        "policy_hash": HASH,
        "human_review_required": body.get("human_review_required", True),
        "semantics_format": "v2",
        "semantics_status": "complete",
        "supersedes_policy_id": predecessor,
        "review_preference_window_seconds": body["review_preference_window_seconds"],
        "review_lease_duration_seconds": body["review_lease_duration_seconds"],
        "max_active_review_leases_per_reviewer": body.get(
            "max_active_review_leases_per_reviewer", 1
        ),
        "self_review_allowed": body.get("self_review_allowed", False),
        "reject_policy": body.get("reject_policy", "close_task"),
        "finding_evidence_requirement": body.get(
            "finding_evidence_requirement", "optional"
        ),
        "requires_second_review": body.get("requires_second_review", False),
        "allowed_decisions": body.get(
            "allowed_decisions", ["accept", "needs_revision", "reject"]
        ),
        "minimum_finding_fields": body.get("minimum_finding_fields", []),
        "created_at": PROFILE["created_at"],
    }


def revision_body():
    return {
        "max_revision_rounds": LARGE,
        "revision_deadline_hours": 48,
        "reviewer_reassignment_rule": None,
    }


def revision_reply(body=None, generation=1, predecessor=None):
    body = body or revision_body()
    return {
        "id": POLICY,
        "project_id": PROJECT,
        "guide_version": receipt()["version"],
        "policy_generation": generation,
        "policy_hash": HASH,
        "semantics_status": "complete",
        "supersedes_policy_id": predecessor,
        "max_revision_rounds": body["max_revision_rounds"],
        "revision_deadline_hours": body["revision_deadline_hours"],
        "allowed_resubmission_states": body.get(
            "allowed_resubmission_states", ["needs_revision"]
        ),
        "reviewer_reassignment_rule": body.get("reviewer_reassignment_rule"),
        "created_at": PROFILE["created_at"],
    }


def invoke(
    cli,
    origin,
    action,
    path,
    *,
    match=None,
    selectors=(PROJECT, GUIDE),
    output="json",
    key=KEY,
):
    args = [
        "-o",
        output,
        "project",
        "guide",
        action,
        *selectors,
        "--input",
        str(path),
        "--idempotency-key",
        key,
    ]
    if match is not None:
        args += ["--if-match", match]
    return cli(origin, TOKEN, *args)


def input_file(tmp_path, body):
    path = tmp_path / "guide-config.json"
    path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return path


def unknown(result, code="invalid_api_response"):
    assert_failure(result, code)
    assert json.loads(result.stderr)["error"]["outcome_unknown"] is True


def test_guide_edit_exact_omission_null_body_identity_and_safe_output(cli, tmp_path):
    with http_fixture() as (origin, response, requests):
        for body, summary in (
            ({}, None),
            ({"change_summary": None}, None),
            ({"change_summary": "Revised é\n\x1b[31m"}, "Revised é\n\x1b[31m"),
        ):
            path = input_file(tmp_path, body)
            response["body"] = json.dumps(
                guide_reply(summary), ensure_ascii=False
            ).encode()
            result = invoke(cli, origin, "edit", path)
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert json.loads(result.stdout) == guide_reply(summary)
            assert response["raw_commands"][-1] == path.read_bytes()
            headers = response["request_headers"][-1]
            assert headers["Idempotency-Key"] == KEY
            assert "If-Match" not in headers
            assert requests[-1] == (
                "PATCH",
                f"/api/v1/projects/{PROJECT}/guides/{GUIDE}",
                "Bearer " + TOKEN,
            )
            safe = invoke(cli, origin, "edit", path, output="text")
            assert safe.returncode == 0 and "\x1b" not in safe.stdout
        assert len(requests) == 6


def test_policy_put_exact_header_body_and_large_integers(cli, tmp_path):
    with http_fixture() as (origin, response, requests):
        for kind, body, reply in (
            ("review", review_body(), review_reply()),
            ("revision", revision_body(), revision_reply()),
        ):
            path = input_file(tmp_path, body)
            response["body"] = json.dumps(reply).encode()
            result = invoke(
                cli, origin, f"set-{kind}-policy", path, match='"no-current-policy"'
            )
            assert result.returncode == 0 and result.stderr == "", result.stderr
            assert json.loads(result.stdout) == reply
            assert response["raw_commands"][-1] == path.read_bytes()
            assert response["request_headers"][-1]["If-Match"] == '"no-current-policy"'
            assert response["request_headers"][-1]["Idempotency-Key"] == KEY
            assert requests[-1] == (
                "PUT",
                f"/api/v1/projects/{PROJECT}/guides/{GUIDE}/{kind}-policy",
                "Bearer " + TOKEN,
            )
            safe = invoke(
                cli,
                origin,
                f"set-{kind}-policy",
                path,
                match='"no-current-policy"',
                output="text",
            )
            assert safe.returncode == 0 and str(LARGE) in safe.stdout

        predecessor = f'"urn:uuid:{POLICY}.1.{"a" * 64}"'
        body = review_body() | {"human_review_required": True}
        path = input_file(tmp_path, body)
        response["body"] = json.dumps(review_reply(body, 2, POLICY)).encode()
        result = invoke(cli, origin, "set-review-policy", path, match=predecessor)
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert response["request_headers"][-1]["If-Match"] == predecessor


def test_initial_review_default_receipt_and_successor_inheritance(cli, tmp_path):
    body = {
        "review_preference_window_seconds": 3600,
        "review_lease_duration_seconds": 1800,
    }
    path = input_file(tmp_path, body)
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(
            review_reply(body) | {"human_review_required": False}
        ).encode()
        unknown(
            invoke(cli, origin, "set-review-policy", path, match='"no-current-policy"')
        )
        assert len(requests) == 1

        initial = review_reply(body)
        response["body"] = json.dumps(initial).encode()
        accepted = invoke(
            cli, origin, "set-review-policy", path, match='"no-current-policy"'
        )
        assert accepted.returncode == 0 and json.loads(accepted.stdout) == initial

        predecessor = f'"{POLICY}.1.{"a" * 64}"'
        inherited = review_reply(body, generation=2, predecessor=POLICY)
        inherited["human_review_required"] = False
        response["body"] = json.dumps(inherited).encode()
        successor = invoke(cli, origin, "set-review-policy", path, match=predecessor)
        assert successor.returncode == 0 and json.loads(successor.stdout) == inherited
        assert len(requests) == 3


def test_config_input_and_header_refusals_send_no_request(cli, tmp_path):
    with http_fixture() as (origin, response, requests):
        path = input_file(tmp_path, review_body())
        for raw in (
            b"{}",
            b"null",
            b"[]",
            b'{"review_preference_window_seconds": 1, "review_preference_window_seconds": 2, "review_lease_duration_seconds": 1}',
            b'{"review_preference_window_seconds": null, "review_lease_duration_seconds": 1}',
            b'{"review_preference_window_seconds": 1, "review_lease_duration_seconds": 1, "unknown": 1}',
            b'{"review_preference_window_seconds": 1, "review_lease_duration_seconds": 1, "human_review_required": null}',
            b'{"review_preference_window_seconds": 1, "review_lease_duration_seconds": 1, "allowed_decisions": ["accept", null]}',
        ):
            path.write_bytes(raw)
            assert_failure(
                invoke(
                    cli, origin, "set-review-policy", path, match='"no-current-policy"'
                ),
                "invalid_arguments",
                2,
            )
        path = input_file(tmp_path, review_body())
        for match in (
            None,
            "",
            ' "no-current-policy"',
            '"no-current-policy" ',
            "x\r\nInjected: x",
            "x" * 257,
        ):
            assert_failure(
                invoke(cli, origin, "set-review-policy", path, match=match),
                "invalid_arguments",
                2,
            )
        assert_failure(
            invoke(cli, origin, "edit", input_file(tmp_path, {"version": "v2"})),
            "invalid_arguments",
            2,
        )
        assert requests == [] and response["commands"] == []


def test_year_zero_created_at_receipts_are_unknown(cli, tmp_path):
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(
            guide_reply("new") | {"created_at": "0000-01-01T00:00:00Z"}
        ).encode()
        unknown(
            invoke(cli, origin, "edit", input_file(tmp_path, {"change_summary": "new"}))
        )

        response["body"] = json.dumps(
            review_reply() | {"created_at": "0000-01-01T00:00:00Z"}
        ).encode()
        unknown(
            invoke(
                cli,
                origin,
                "set-review-policy",
                input_file(tmp_path, review_body()),
                match='"no-current-policy"',
            )
        )
        assert len(requests) == 2


def test_mismatched_successes_are_unknown_and_never_printed(cli, tmp_path):
    with http_fixture() as (origin, response, requests):
        edit = input_file(tmp_path, {"change_summary": "new"})
        for mutation in (
            {"project_id": POLICY},
            {"id": POLICY},
            {"status": "active"},
            {"change_summary": "old"},
            {"task_examples": None},
        ):
            reply = guide_reply("new") | mutation
            response["body"] = json.dumps(reply).encode()
            unknown(invoke(cli, origin, "edit", edit))
        body = review_body()
        path = input_file(tmp_path, body)
        for mutation in (
            {"project_id": POLICY},
            {"policy_generation": 2},
            {"supersedes_policy_id": POLICY},
            {"human_review_required": True},
            {"review_preference_window_seconds": LARGE - 1},
            {"policy_hash": "bad"},
            {"allowed_decisions": None},
            {"allowed_decisions": ["accept", None]},
        ):
            reply = review_reply() | mutation
            response["body"] = json.dumps(reply).encode()
            unknown(
                invoke(
                    cli, origin, "set-review-policy", path, match='"no-current-policy"'
                )
            )
        assert len(requests) == 13


def test_known_denials_and_ambiguous_writes_are_distinct(cli, tmp_path):
    path = input_file(tmp_path, review_body())
    with http_fixture() as (origin, response, requests):
        for code in (
            "policy_precondition_failed",
            "idempotency_mismatch",
            "authorization_denied",
        ):
            response.update(
                status=409 if code != "authorization_denied" else 403,
                body=json.dumps(canonical_error(code)).encode(),
            )
            denied = invoke(
                cli, origin, "set-review-policy", path, match='"no-current-policy"'
            )
            assert_failure(denied, code)
            assert "outcome_unknown" not in json.loads(denied.stderr)["error"]
        response.update(
            status=409, body=b'{"error":{"code":"policy_precondition_failed"}}'
        )
        unknown(
            invoke(cli, origin, "set-review-policy", path, match='"no-current-policy"'),
            "policy_precondition_failed",
        )
        response.update(status=200, body=b"{}")
        unknown(
            invoke(cli, origin, "set-review-policy", path, match='"no-current-policy"')
        )
        response["drop"] = True
        unknown(
            invoke(cli, origin, "set-review-policy", path, match='"no-current-policy"'),
            "service_unavailable",
        )
        assert len(requests) == 6

    edit = input_file(tmp_path, {"change_summary": None})
    with http_fixture() as (origin, response, requests):
        response.update(status=409, body=b'{"error":{"code":"idempotency_mismatch"}}')
        unknown(invoke(cli, origin, "edit", edit), "idempotency_mismatch")
        assert len(requests) == 1


def test_config_http2_goaway_does_not_replay_write(cli, tmp_path):
    path = input_file(tmp_path, revision_body())
    with goaway_fixture(tmp_path) as (origin, env, bodies, connections):
        result = cli(
            origin,
            TOKEN,
            "-o",
            "json",
            "project",
            "guide",
            "set-revision-policy",
            PROJECT,
            GUIDE,
            "--input",
            str(path),
            "--if-match",
            '"no-current-policy"',
            "--idempotency-key",
            KEY,
            extra_env=env,
        )
        unknown(result, "service_unavailable")
        assert [json.loads(value) for value in bodies] == [revision_body()]
        assert connections == ["h2"]
