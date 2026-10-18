"""Built CLI process proof for seven existing administrative guide GETs."""

from copy import deepcopy
import json
from urllib.parse import quote

import pytest

from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture

GUIDE = "018f0ebc-7966-7e8d-bc4d-1cae1e000020"
SNAPSHOT = "018f0ebc-7966-7e8d-bc4d-1cae1e000021"
REPORT = "018f0ebc-7966-7e8d-bc4d-1cae1e000022"
POLICY = "018f0ebc-7966-7e8d-bc4d-1cae1e000023"
EFFECTIVE = "018f0ebc-7966-7e8d-bc4d-1cae1e000024"
PRE = "018f0ebc-7966-7e8d-bc4d-1cae1e000025"
HASH = "sha256:" + "a" * 64
WHEN = "2026-10-18T00:00:00Z"
LARGE = 9223372036854775808
GUIDE_PATH = f"/api/v1/projects/{PROJECT}/guides/{GUIDE}"


def report():
    return {
        "id": REPORT,
        "project_id": PROJECT,
        "guide_id": GUIDE,
        "guide_version": "v1",
        "source_snapshot_id": SNAPSHOT,
        "source_snapshot_hash": HASH,
        "status": "passed_with_warnings",
        "findings": [
            {"severity": "warning", "code": "check", "message": "é\n\x1b[31m\u202e"}
        ],
        "summary": "Summary",
        "agent_name": None,
        "agent_version": None,
        "project_setup_run_id": None,
        "setup_generation": LARGE,
        "agent_material_sha256": None,
        "agent_material_byte_count": LARGE,
        "created_by": "guide-setup-agent",
        "created_at": WHEN,
        "warnings_acknowledged_by_role": None,
        "warnings_acknowledged_by_actor": None,
        "warnings_acknowledged_at": None,
        "acknowledgement_note": None,
    }


def artifact_policy():
    return {
        "id": POLICY,
        "project_id": PROJECT,
        "guide_id": GUIDE,
        "guide_version": "v1",
        "source_snapshot_id": SNAPSHOT,
        "source_snapshot_hash": HASH,
        "policy_version": "v1",
        "lifecycle_status": "approved",
        "policy_body": {"maximum_archive_size_bytes": LARGE},
        "policy_hash": HASH,
        "derivation_source": "unified_compilation",
        "source_material_refs": ["document:one"],
        "derivation_agent_name": None,
        "derivation_agent_version": None,
        "created_by": "guide-setup-agent",
        "created_at": WHEN,
        "updated_at": WHEN,
        "approved_by_role": "project_manager",
        "approved_by_actor": ACTOR,
        "approved_at": WHEN,
        "supersedes_policy_id": None,
        "superseded_at": None,
        "change_summary": None,
    }


def effective_policy():
    return {
        "id": EFFECTIVE,
        "project_id": PROJECT,
        "guide_id": GUIDE,
        "guide_version": "v1",
        "source_snapshot_id": SNAPSHOT,
        "source_snapshot_hash": HASH,
        "submission_artifact_policy_id": POLICY,
        "submission_artifact_policy_hash": HASH,
        "lifecycle_status": "approved",
        "merge_algorithm_version": "v1",
        "effective_policy": {"maximum_archive_size_bytes": LARGE},
        "effective_policy_hash": HASH,
        "created_by": "system",
        "created_at": WHEN,
        "supersedes_effective_policy_id": None,
        "superseded_at": None,
    }


def pre_policy():
    return {
        "id": PRE,
        "project_id": PROJECT,
        "guide_id": GUIDE,
        "guide_version": "v1",
        "source_snapshot_id": SNAPSHOT,
        "source_snapshot_hash": HASH,
        "effective_policy_id": EFFECTIVE,
        "effective_policy_hash": HASH,
        "lifecycle_status": "compiled",
        "compiler_version": "v1",
        "compiled_bundle_hash": HASH,
        "checker_names": ["secret_scanner"],
        "created_by": "system",
        "created_at": WHEN,
        "supersedes_pre_submit_checker_policy_id": None,
        "superseded_at": None,
    }


def active_guide():
    return {
        "guide": {
            "id": GUIDE,
            "project_id": PROJECT,
            "version": "v1",
            "status": "active",
            "change_summary": None,
            "task_examples": None,
            "task_examples_hash": None,
            "approved_by": ACTOR,
            "effective_at": WHEN,
            "created_by": ACTOR,
            "created_at": WHEN,
            "updated_at": WHEN,
            "superseded_at": None,
            "contribution_policy_id": POLICY,
            "contribution_policy_version_id": POLICY,
            "activation_operation_id": REPORT,
        },
        "guide_source_snapshot": {
            "id": SNAPSHOT,
            "project_id": PROJECT,
            "guide_id": GUIDE,
            "guide_version": "v1",
            "manifest_schema_version": "v1",
            "manifest_json": {},
            "bundle_hash": HASH,
            "captured_by": ACTOR,
            "captured_at": WHEN,
            "items": [],
        },
        "guide_sufficiency_report": report(),
        "submission_artifact_policy": artifact_policy(),
        "effective_submission_artifact_policy": effective_policy(),
        "pre_submit_checker_policy": pre_policy() | {"checker_configs": {}},
        "post_submit_checker_policy": {
            "id": REPORT,
            "project_id": PROJECT,
            "guide_version": "v1",
            "required_checkers": [],
            "warning_checkers": [],
            "blocking_severities": [],
            "policy_hash": HASH,
            "lifecycle_status": "approved",
            "projection_operation_id": EFFECTIVE,
            "approval_operation_id": PRE,
            "approved_at": WHEN,
            "created_at": WHEN,
        },
        "review_policy": {
            "id": POLICY,
            "project_id": PROJECT,
            "guide_version": "v1",
            "policy_generation": LARGE,
            "policy_hash": HASH,
            "human_review_required": True,
            "semantics_format": "v2",
            "semantics_status": "complete",
            "supersedes_policy_id": None,
            "review_preference_window_seconds": LARGE,
            "review_lease_duration_seconds": LARGE,
            "max_active_review_leases_per_reviewer": 1,
            "self_review_allowed": False,
            "reject_policy": "close_task",
            "finding_evidence_requirement": "optional",
            "requires_second_review": False,
            "allowed_decisions": ["accept", "needs_revision", "reject"],
            "minimum_finding_fields": [],
            "created_at": WHEN,
        },
        "revision_policy": {
            "id": PRE,
            "project_id": PROJECT,
            "guide_version": "v1",
            "policy_generation": LARGE,
            "policy_hash": HASH,
            "semantics_status": "complete",
            "supersedes_policy_id": None,
            "max_revision_rounds": LARGE,
            "revision_deadline_hours": LARGE,
            "allowed_resubmission_states": ["needs_revision"],
            "reviewer_reassignment_rule": None,
            "created_at": WHEN,
        },
    }


CASES = [
    (
        ("project", "active-guide", PROJECT),
        f"/api/v1/projects/{PROJECT}/active-guide",
        active_guide,
    ),
    (
        ("project", "guide", "sufficiency", "list", PROJECT, GUIDE),
        GUIDE_PATH + "/sufficiency-reports",
        lambda: [report()],
    ),
    (
        ("project", "guide", "sufficiency", "show", PROJECT, GUIDE, REPORT),
        GUIDE_PATH + "/sufficiency-reports/" + REPORT,
        report,
    ),
    (
        ("project", "guide", "artifact-policy", "list", PROJECT, GUIDE),
        GUIDE_PATH + "/submission-artifact-policies",
        lambda: [artifact_policy()],
    ),
    (
        ("project", "guide", "artifact-policy", "show", PROJECT, GUIDE, POLICY),
        GUIDE_PATH + "/submission-artifact-policies/" + POLICY,
        artifact_policy,
    ),
    (
        ("project", "guide", "artifact-policy", "effective", PROJECT, GUIDE),
        GUIDE_PATH + "/effective-submission-artifact-policy",
        effective_policy,
    ),
    (
        ("project", "guide", "pre-submit-policy", PROJECT, GUIDE),
        GUIDE_PATH + "/pre-submit-checker-policy",
        pre_policy,
    ),
]


@pytest.mark.parametrize(("command", "path", "make_value"), CASES)
def test_exact_public_read_parity_and_safe_text(cli, command, path, make_value):
    with http_fixture() as (origin, response, requests):
        value = make_value()
        response["body"] = json.dumps(value, ensure_ascii=False, indent=2).encode()
        result = cli(origin, TOKEN, *command, "-o", "json")
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert result.stdout.strip().encode() == response["body"]
        assert requests == [("GET", path, "Bearer " + TOKEN)]
        text = cli(origin, TOKEN, *command)
        assert text.returncode == 0 and text.stderr == "", text.stderr
        assert "\x1b" not in text.stdout and "\u202e" not in text.stdout
        assert (
            "\\u001b" in text.stdout
            or "\\u001B" in text.stdout
            or command != CASES[1][0]
        )
        assert len(requests) == 2 and response["commands"] == []


@pytest.mark.parametrize(("command", "path", "make_value"), CASES)
def test_denial_redacts_bearer_and_never_retries(cli, command, path, make_value):
    with http_fixture() as (origin, response, requests):
        response.update(
            status=404,
            body=json.dumps(
                {"error": {"code": "resource_not_found", "message": TOKEN}}
            ).encode(),
            headers={"Content-Type": "application/json", "X-Correlation-ID": TOKEN},
        )
        result = cli(origin, TOKEN, "-o", "json", *command)
        assert_failure(result, "resource_not_found")
        assert TOKEN not in result.stderr
        assert requests == [("GET", path, "Bearer " + TOKEN)]


@pytest.mark.parametrize(("command", "_path", "make_value"), CASES)
def test_mismatched_lineage_and_truncated_payload_fail_closed(
    cli, command, _path, make_value
):
    with http_fixture() as (origin, response, _requests):
        value = make_value()
        if isinstance(value, list):
            value[0]["project_id"] = ACTOR
        elif "guide" in value:
            value["guide_source_snapshot"]["guide_id"] = ACTOR
        else:
            value["project_id"] = ACTOR
        response["body"] = json.dumps(value).encode()
        assert_failure(
            cli(origin, TOKEN, "-o", "json", *command), "invalid_api_response"
        )
        response["body"] = b"{}"
        assert_failure(
            cli(origin, TOKEN, "-o", "json", *command), "invalid_api_response"
        )


def test_exact_uuid_selectors_and_bounded_historical_collections(cli):
    with http_fixture() as (origin, response, requests):
        for command, value in (
            (
                (
                    "project",
                    "guide",
                    "sufficiency",
                    "show",
                    PROJECT,
                    GUIDE,
                    REPORT.replace("-", ""),
                ),
                report(),
            ),
            (
                (
                    "project",
                    "guide",
                    "artifact-policy",
                    "show",
                    PROJECT,
                    GUIDE,
                    POLICY.replace("-", ""),
                ),
                artifact_policy(),
            ),
        ):
            response["body"] = json.dumps(value).encode()
            result = cli(origin, TOKEN, *command, "-o", "json")
            assert result.returncode == 0, result.stderr
            assert requests[-1][1].endswith(command[-1])
        for command, make_value in (
            (CASES[1][0], report),
            (CASES[3][0], artifact_policy),
        ):
            rows = [
                make_value() | {"id": f"018f0ebc-7966-7e8d-bc4d-{index:012x}"}
                for index in range(100)
            ]
            response["body"] = json.dumps(rows).encode()
            assert cli(origin, TOKEN, *command, "-o", "json").returncode == 0
            response["body"] = json.dumps(rows + [make_value()]).encode()
            assert_failure(
                cli(origin, TOKEN, "-o", "json", *command), "invalid_api_response"
            )
            response["body"] = json.dumps([make_value(), make_value()]).encode()
            assert_failure(
                cli(origin, TOKEN, "-o", "json", *command), "invalid_api_response"
            )


def test_full_integer_range_and_malformed_report_fields(cli):
    command = CASES[2][0]
    with http_fixture() as (origin, response, _requests):
        value = report()
        response["body"] = json.dumps(value).encode()
        assert cli(origin, TOKEN, *command, "-o", "json").returncode == 0
        for bad in ("1.5", "1e4", "true", '"1"'):
            response["body"] = json.dumps(value).replace(str(LARGE), bad, 1).encode()
            assert_failure(
                cli(origin, TOKEN, "-o", "json", *command), "invalid_api_response"
            )
        response["body"] = json.dumps(value | {"setup_generation": None}).encode()
        assert cli(origin, TOKEN, *command, "-o", "json").returncode == 0
        for key, bad in (
            ("source_snapshot_hash", "not-a-hash"),
            ("status", "accepted"),
            ("id", ACTOR),
        ):
            changed = deepcopy(value)
            changed[key] = bad
            response["body"] = json.dumps(changed).encode()
            assert_failure(
                cli(origin, TOKEN, "-o", "json", *command), "invalid_api_response"
            )


def test_uuid_spelling_is_sent_unchanged(cli):
    with http_fixture() as (origin, response, requests):
        response["body"] = json.dumps(report()).encode()
        project = "urn:uuid:" + PROJECT
        guide = "{" + GUIDE + "}"
        selected = REPORT.replace("-", "")
        result = cli(
            origin,
            TOKEN,
            "project",
            "guide",
            "sufficiency",
            "show",
            project,
            guide,
            selected,
            "-o",
            "json",
        )
        assert result.returncode == 0, result.stderr
        assert (
            requests[-1][1]
            == f"/api/v1/projects/{quote(project, safe=':')}/guides/{quote(guide, safe=':')}/sufficiency-reports/{selected}"
        )


def test_active_chain_substitution_and_reflected_bearer_fail_closed(cli):
    command = CASES[0][0]
    with http_fixture() as (origin, response, _requests):
        for section, field, bad in (
            ("guide_sufficiency_report", "status", "blocked"),
            ("submission_artifact_policy", "lifecycle_status", "draft"),
            (
                "effective_submission_artifact_policy",
                "submission_artifact_policy_id",
                ACTOR,
            ),
            (
                "pre_submit_checker_policy",
                "effective_policy_hash",
                "sha256:" + "b" * 64,
            ),
            ("review_policy", "project_id", ACTOR),
            ("guide", "activation_operation_id", None),
        ):
            value = active_guide()
            value[section][field] = bad
            response["body"] = json.dumps(value).encode()
            assert_failure(
                cli(origin, TOKEN, "-o", "json", *command), "invalid_api_response"
            )
        value = active_guide()
        value["guide_sufficiency_report"]["summary"] = TOKEN.upper()
        response["body"] = json.dumps(value).encode()
        assert_failure(
            cli(origin, TOKEN, "-o", "json", *command), "invalid_api_response"
        )


@pytest.mark.parametrize(
    ("section", "field", "bad"),
    [
        ("guide", "approved_by", None),
        ("submission_artifact_policy", "approved_by_actor", None),
        ("submission_artifact_policy", "approved_at", None),
        ("post_submit_checker_policy", "policy_hash", None),
        ("post_submit_checker_policy", "projection_operation_id", None),
        ("post_submit_checker_policy", "approval_operation_id", None),
        ("post_submit_checker_policy", "approved_at", None),
        ("review_policy", "semantics_status", "legacy_incomplete"),
        ("review_policy", "policy_hash", None),
        ("review_policy", "review_preference_window_seconds", None),
        ("review_policy", "max_active_review_leases_per_reviewer", 2),
        ("review_policy", "self_review_allowed", True),
        ("review_policy", "reject_policy", "reopen_task"),
        ("review_policy", "finding_evidence_requirement", "unknown"),
        ("review_policy", "requires_second_review", True),
        ("review_policy", "allowed_decisions", ["accept", "unknown"]),
        ("review_policy", "allowed_decisions", []),
        ("revision_policy", "semantics_status", "legacy_incomplete"),
        ("revision_policy", "policy_hash", None),
        ("revision_policy", "allowed_resubmission_states", ["rejected"]),
        ("revision_policy", "allowed_resubmission_states", []),
    ],
)
def test_active_current_policy_semantics_fail_closed(cli, section, field, bad):
    with http_fixture() as (origin, response, _requests):
        value = active_guide()
        value[section][field] = bad
        response["body"] = json.dumps(value).encode()
        assert_failure(
            cli(origin, TOKEN, "-o", "json", *CASES[0][0]),
            "invalid_api_response",
        )


def test_schema_string_arrays_allow_blank_members_and_current_pre_hash_is_required(cli):
    with http_fixture() as (origin, response, _requests):
        value = active_guide()
        value["review_policy"]["minimum_finding_fields"] = [""]
        value["review_policy"]["allowed_decisions"] = ["accept"] * 4
        response["body"] = json.dumps(value).encode()
        result = cli(origin, TOKEN, "-o", "json", *CASES[0][0])
        assert result.returncode == 0, result.stderr

        policy = pre_policy()
        policy["compiled_bundle_hash"] = None
        response["body"] = json.dumps(policy).encode()
        assert_failure(
            cli(origin, TOKEN, "-o", "json", *CASES[6][0]),
            "invalid_api_response",
        )


def test_active_review_policy_format_preserves_v2_automatic_acceptance_mode(cli):
    with http_fixture() as (origin, response, _requests):
        value = active_guide()
        value["review_policy"]["human_review_required"] = False
        response["body"] = json.dumps(value).encode()
        result = cli(origin, TOKEN, "-o", "json", *CASES[0][0])
        assert result.returncode == 0, result.stderr

        value["review_policy"]["semantics_format"] = "v1"
        response["body"] = json.dumps(value).encode()
        assert_failure(
            cli(origin, TOKEN, "-o", "json", *CASES[0][0]),
            "invalid_api_response",
        )


def test_unknown_duplicate_and_oversized_success_are_not_printed(cli):
    command = CASES[2][0]
    with http_fixture() as (origin, response, _requests):
        value = report()
        response["body"] = json.dumps(value | {"secret_extra": "unexpected"}).encode()
        assert_failure(
            cli(origin, TOKEN, "-o", "json", *command), "invalid_api_response"
        )
        body = json.dumps(value)
        response["body"] = body.replace(
            '"id": "' + REPORT + '"', '"id": "' + REPORT + '", "id": "' + ACTOR + '"', 1
        ).encode()
        assert_failure(
            cli(origin, TOKEN, "-o", "json", *command), "invalid_api_response"
        )
        response["body"] = b" " * (16 * 1024 * 1024 + 1)
        assert_failure(
            cli(origin, TOKEN, "-o", "json", *command), "invalid_api_response"
        )
