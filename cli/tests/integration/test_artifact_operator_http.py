"""Built-binary wire, response and one-shot boundaries for nine ART routes."""

import json

from test_contributor_task_mutations import canonical_error
from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture

CONTENT = "018f0ebc-7966-7e8d-bc4d-1cae1e000010"
REPLICA = "018f0ebc-7966-7e8d-bc4d-1cae1e000011"
RECEIPT = "018f0ebc-7966-7e8d-bc4d-1cae1e000012"
JOB = "018f0ebc-7966-7e8d-bc4d-1cae1e000013"
RETRY_JOB = "018f0ebc-7966-7e8d-bc4d-1cae1e000014"
RECOVERY = "018f0ebc-7966-7e8d-bc4d-1cae1e000015"
TASK = "018f0ebc-7966-7e8d-bc4d-1cae1e000016"
SUBMISSION = "018f0ebc-7966-7e8d-bc4d-1cae1e000017"
KEY = "018f0ebc-7966-7e8d-bc4d-1cae1e000018"
STAMP = "2026-10-01T00:00:00Z"

BINDING = {
    "id": ACTOR,
    "content_id": CONTENT,
    "project_id": PROJECT,
    "resource_type": "task",
    "resource_id": TASK,
    "logical_role": "source",
    "scope_version": 1,
    "supersedes_binding_id": None,
    "created_at": STAMP,
}
REPLICA_ROW = {
    "id": REPLICA,
    "content_id": CONTENT,
    "verification_state": "verified",
    "availability_state": "available",
    "integrity_state": "intact",
    "last_reconciled_at": None,
    "created_at": STAMP,
    "updated_at": STAMP,
}
RECEIPT_ROW = {
    "id": RECEIPT,
    "receipt_type": "verification",
    "replica_id": REPLICA,
    "outcome": "verified",
    "verification_job_id": JOB,
    "created_at": STAMP,
}
JOB_ROW = {
    "id": JOB,
    "replica_id": REPLICA,
    "parent_verification_job_id": None,
    "status": "provider_unavailable",
    "attempt_count": 2,
    "maximum_attempts": 2,
    "next_run_at": None,
    "cas_version": 3,
    "terminal_result_code": "provider_unavailable",
    "terminal_at": STAMP,
    "receipt_id": None,
    "created_at": STAMP,
    "updated_at": STAMP,
}
RECOVERY_ROW = {
    "id": RECOVERY,
    "project_id": PROJECT,
    "task_id": TASK,
    "submission_id": SUBMISSION,
    "source_verification_job_id": JOB,
    "source_verification_job_status": "provider_unavailable",
    "retry_verification_job_id": RETRY_JOB,
    "retry_verification_job_status": "pending",
    "parent_recovery_attempt_id": None,
    "status": "requested",
    "terminal_result_code": None,
    "initiation_audit_event_id": ACTOR,
    "terminal_audit_event_id": None,
    "cas_version": 1,
    "created_at": STAMP,
    "terminal_at": None,
    "updated_at": STAMP,
}
AUDIT_ROW = {
    "id": ACTOR,
    "entity_type": "artifact_recovery_attempt",
    "entity_id": RECOVERY,
    "event_type": "ArtifactRecoveryInitiated",
    "from_status": None,
    "to_status": "requested",
    "reason": "Operator request",
    "occurred_at": STAMP,
    "created_at": STAMP,
    "request_id": None,
    "correlation_id": None,
}
USAGE_ROW = {
    "scope_type": "project",
    "scope_id": PROJECT,
    "counted_bytes": 10,
    "limit_bytes": 100,
    "remaining_bytes": 90,
    "configured_limit_bytes": None,
    "unbound_ready_count": 0,
    "unbound_ready_bytes": 0,
    "stale_count": 0,
    "stale_bytes": 0,
    "cas_version": 1,
    "updated_at": STAMP,
}
READINESS = {
    "backend": "local",
    "provider_profile": None,
    "configured": True,
    "active": False,
    "status": "not_active",
    "prerequisites": {"namespace": True},
}
RETRY = {
    "recovery_attempt_id": RECOVERY,
    "source_verification_job_id": JOB,
    "retry_verification_job_id": RETRY_JOB,
    "replayed": False,
}


def invoke(cli, origin, *args, output="json"):
    return cli(origin, TOKEN, "-o", output, "operations", "artifact", *args)


def retry_args(*extra):
    return (
        "retry",
        JOB,
        "--project-id",
        PROJECT,
        "--task-id",
        TASK,
        "--submission-id",
        SUBMISSION,
        "--reason",
        "Provider remained unavailable",
        "--idempotency-key",
        KEY,
        "--expected-source-job-cas-version",
        "3",
        *extra,
    )


def test_exact_eight_read_routes_and_safe_text(cli):
    cases = (
        (
            ("bindings", "task", TASK),
            {"items": [BINDING], "next_cursor": None},
            f"/api/v1/operator/artifacts/bindings?limit=50&resource_id={TASK}&resource_type=task",
        ),
        (
            ("replicas", CONTENT),
            {"items": [REPLICA_ROW], "next_cursor": None},
            f"/api/v1/operator/artifacts/contents/{CONTENT}/replicas?limit=50",
        ),
        (
            ("receipts", REPLICA),
            {"items": [RECEIPT_ROW], "next_cursor": None},
            f"/api/v1/operator/artifacts/replicas/{REPLICA}/receipts?limit=50",
        ),
        (
            ("verification-job", JOB),
            JOB_ROW,
            f"/api/v1/operator/artifacts/verification-jobs/{JOB}",
        ),
        (
            ("recovery-attempt", RECOVERY),
            RECOVERY_ROW,
            f"/api/v1/operator/artifacts/recovery-attempts/{RECOVERY}",
        ),
        (
            ("audit-events", "artifact_recovery_attempt", RECOVERY),
            {"items": [AUDIT_ROW], "next_cursor": None},
            f"/api/v1/operator/artifacts/audit-events?limit=50&resource_id={RECOVERY}&resource_type=artifact_recovery_attempt",
        ),
        (
            ("admission-usage", PROJECT, "--task-id", TASK),
            {"items": [USAGE_ROW], "next_cursor": None},
            f"/api/v1/operator/artifacts/admission-usage?limit=50&project_id={PROJECT}&task_id={TASK}",
        ),
        (("readiness",), READINESS, "/api/v1/operator/artifacts/readiness"),
    )
    with http_fixture() as (origin, response, requests):
        for index, (args, body, path) in enumerate(cases, start=1):
            response["body"] = json.dumps(body).encode()
            result = invoke(cli, origin, *args)
            assert result.returncode == 0 and result.stderr == "", (args, result.stderr)
            assert json.loads(result.stdout) == body
            assert requests[-1] == ("GET", path, "Bearer " + TOKEN)
            assert len(requests) == index

        response["body"] = json.dumps(
            {
                "items": [BINDING | {"logical_role": "a\u202eb"}],
                "next_cursor": "opaque",
            },
            ensure_ascii=False,
        ).encode()
        text = invoke(cli, origin, "bindings", "task", TASK, output="text")
        assert text.returncode == 0 and text.stderr == ""
        assert (
            "Artifact bindings (current observation, not later authority):"
            in text.stdout
        )
        assert "\u202e" not in text.stdout and "\\u202e" in text.stdout.lower()


def test_bounded_page_continuations_are_one_exact_request(cli):
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(
            {"items": [BINDING], "next_cursor": "opaque-2"}
        ).encode()
        result = invoke(
            cli,
            origin,
            "bindings",
            "task",
            TASK,
            "--limit",
            "1",
            "--cursor",
            "opaque-1",
        )
        assert (
            result.returncode == 0
            and json.loads(result.stdout)["next_cursor"] == "opaque-2"
        )
        assert requests == [
            (
                "GET",
                f"/api/v1/operator/artifacts/bindings?cursor=opaque-1&limit=1&resource_id={TASK}&resource_type=task",
                "Bearer " + TOKEN,
            )
        ]


def test_all_read_successes_reject_selected_resource_substitution(cli):
    cases = (
        (
            ("bindings", "task", TASK),
            {"items": [BINDING | {"resource_id": ACTOR}], "next_cursor": None},
        ),
        (
            ("replicas", CONTENT),
            {"items": [REPLICA_ROW | {"content_id": ACTOR}], "next_cursor": None},
        ),
        (
            ("receipts", REPLICA),
            {"items": [RECEIPT_ROW | {"replica_id": ACTOR}], "next_cursor": None},
        ),
        (("verification-job", JOB), JOB_ROW | {"id": ACTOR}),
        (("recovery-attempt", RECOVERY), RECOVERY_ROW | {"id": ACTOR}),
        (
            ("audit-events", "artifact_recovery_attempt", RECOVERY),
            {"items": [AUDIT_ROW | {"entity_id": ACTOR}], "next_cursor": None},
        ),
        (
            ("admission-usage", PROJECT),
            {"items": [USAGE_ROW | {"scope_id": ACTOR}], "next_cursor": None},
        ),
        (("readiness",), READINESS | {"provider_object_ref": "s3://private"}),
    )
    with http_fixture() as (origin, response, requests):
        for args, body in cases:
            response["body"] = json.dumps(body).encode()
            assert_failure(invoke(cli, origin, *args), "invalid_api_response")
        assert len(requests) == len(cases)


def test_pages_and_objects_reject_truncation_null_numeric_and_reflection(cli):
    with http_fixture() as (origin, response, requests):
        bad_pages = (
            {"items": [BINDING]},
            {"items": None, "next_cursor": None},
            {"items": [], "next_cursor": "opaque"},
            {"items": [BINDING | {"scope_version": None}], "next_cursor": None},
            {"items": [BINDING | {"logical_role": TOKEN}], "next_cursor": None},
            {"items": [BINDING | {"secret": "provider-key"}], "next_cursor": None},
        )
        for body in bad_pages:
            response["body"] = json.dumps(body).encode()
            assert_failure(
                invoke(cli, origin, "bindings", "task", TASK), "invalid_api_response"
            )
        bad_jobs = (
            JOB_ROW | {"cas_version": -1},
            JOB_ROW | {"maximum_attempts": "2"},
            JOB_ROW | {"parent_verification_job_id": "bad"},
            {key: value for key, value in JOB_ROW.items() if key != "status"},
        )
        for body in bad_jobs:
            response["body"] = json.dumps(body).encode()
            assert_failure(
                invoke(cli, origin, "verification-job", JOB), "invalid_api_response"
            )
        response["body"] = json.dumps(
            READINESS | {"prerequisites": {"namespace": None}}
        ).encode()
        assert_failure(invoke(cli, origin, "readiness"), "invalid_api_response")
        assert len(requests) == len(bad_pages) + len(bad_jobs) + 1


def test_invalid_inputs_never_send_or_infer_authority(cli):
    with http_fixture() as (origin, _response, requests):
        cases = (
            ("bindings", "review", TASK),
            ("bindings", "task", "bad"),
            ("replicas", "bad"),
            ("receipts", "bad"),
            ("verification-job", "bad"),
            ("recovery-attempt", "bad"),
            ("audit-events", "task", RECOVERY),
            ("admission-usage", "bad"),
            ("admission-usage", PROJECT, "--task-id", "bad"),
            ("bindings", "task", TASK, "--limit", "0"),
            ("bindings", "task", TASK, "--cursor", ""),
            ("retry", JOB),
            (*retry_args(), "--submission-id", "bad"),
            (*retry_args(), "--reason", " "),
            (*retry_args(), "--expected-source-job-cas-version", "-1"),
            (*retry_args(), "--idempotency-key", "bad"),
        )
        for args in cases:
            assert_failure(invoke(cli, origin, *args), "invalid_arguments", 2)
        assert requests == []


def test_retry_posts_once_with_exact_body_status_and_manual_replay(cli):
    with http_fixture() as (origin, response, requests):
        response.update(status=202, body=json.dumps(RETRY).encode())
        result = invoke(cli, origin, *retry_args())
        assert result.returncode == 0 and json.loads(result.stdout) == RETRY
        assert requests == [
            (
                "POST",
                f"/api/v1/operator/artifacts/verification-jobs/{JOB}/retry",
                "Bearer " + TOKEN,
            )
        ]
        assert response["commands"] == [
            (
                "application/json",
                [KEY],
                {
                    "project_id": PROJECT,
                    "task_id": TASK,
                    "submission_id": SUBMISSION,
                    "reason": "Provider remained unavailable",
                    "client_idempotency_key": KEY,
                    "expected_source_job_cas_version": 3,
                },
            )
        ]
        response["body"] = json.dumps(RETRY | {"replayed": True}).encode()
        replay = invoke(cli, origin, *retry_args())
        assert replay.returncode == 0 and json.loads(replay.stdout)["replayed"] is True
        assert len(requests) == 2  # Explicit caller replay only.


def test_retry_distinguishes_known_denial_conflict_ineligible_and_unknown(cli):
    with http_fixture() as (origin, response, requests):
        for status, code in (
            (404, "not_found"),
            (409, "artifact_recovery_conflict"),
            (422, "artifact_recovery_ineligible"),
        ):
            response.update(
                status=status, body=json.dumps(canonical_error(code)).encode()
            )
            result = invoke(cli, origin, *retry_args())
            assert_failure(result, code)
            assert json.loads(result.stderr)["error"].get("outcome_unknown") is None
        response.update(
            status=202,
            body=json.dumps(RETRY | {"source_verification_job_id": ACTOR}).encode(),
        )
        assert_failure(invoke(cli, origin, *retry_args()), "invalid_api_response")
        response.update(
            status=503,
            body=b"<html>gateway lost result</html>",
            headers={"Content-Type": "text/html"},
        )
        unknown = invoke(cli, origin, *retry_args(), output="text")
        assert unknown.returncode == 1 and unknown.stdout == ""
        assert "outcome unknown" in unknown.stderr and "unchanged job" in unknown.stderr
        assert len(requests) == 5


def test_retry_response_rejects_hidden_fields_and_bad_replay_flag(cli):
    with http_fixture() as (origin, response, requests):
        response["status"] = 202
        for body in (
            RETRY | {"provider_object_ref": "s3://private"},
            RETRY | {"replayed": None},
            RETRY | {"recovery_attempt_id": "bad"},
        ):
            response["body"] = json.dumps(body).encode()
            assert_failure(invoke(cli, origin, *retry_args()), "invalid_api_response")
        assert len(requests) == 3
