"""Built-binary manager evidence reads keep exact selectors and projections."""

from copy import deepcopy
import json
from urllib.parse import parse_qs, urlsplit

from test_http_boundary import ACTOR, PROJECT, TOKEN, assert_failure, http_fixture
from test_task_http_boundary import DETAIL, TASK
from test_task_context_http import CONTEXT, REQUIREMENTS, REVISION_LINEAGE
from test_submission_http import CHECKER, HISTORY, RUN, SUBMISSION

OTHER = "018f0ebc-7966-7e8d-bc4d-1cae1e000099"

MANAGER_CONTEXT = {
    key: deepcopy(CONTEXT[key])
    for key in (
        "project",
        "guide",
        "review_policy",
        "revision_policy",
        "contribution_policy_version_id",
    )
} | {"task": DETAIL}
MANAGER_CONTEXT["review_policy"]["generation"] = 10**25
MANAGER_CONTEXT["revision_policy"]["generation"] = 10**25
LOCKED = {
    "task_id": TASK,
    "project_id": PROJECT,
    **REVISION_LINEAGE,
    "locked_post_submit_checker_policy_body_summary": {
        "schema_version": None,
        "default_checkers": ["quality"],
        "required_checkers": ["quality"],
        "warning_checkers": [],
        "execution_checkers": [],
        "blocking_severities": ["error"],
    },
}
MANAGER_HISTORY = HISTORY | {
    "task_id": TASK,
    "contributor_id": ACTOR,
    "task_assignment_id": OTHER,
    "contribution_policy_version_id": ACTOR,
    "locked_guide_version": "guide-1",
    "locked_post_submit_checker_policy_id": ACTOR,
    "locked_post_submit_checker_policy_version": "post-1",
    "locked_post_submit_checker_policy_hash": "sha256:" + "a" * 64,
    "locked_review_policy_id": ACTOR,
    "locked_review_policy_generation": 10**25,
    "locked_review_policy_hash": "sha256:" + "a" * 64,
    "locked_revision_policy_id": ACTOR,
    "locked_revision_policy_generation": 10**25,
    "locked_revision_policy_hash": "sha256:" + "a" * 64,
    "locked_guide_source_snapshot_id": None,
    "locked_guide_source_snapshot_hash": None,
    "locked_effective_project_submission_artifact_policy_id": None,
    "locked_effective_project_submission_artifact_policy_hash": None,
    "locked_pre_submit_checker_policy_id": None,
    "locked_pre_submit_checker_bundle_hash": None,
}
MANAGER_RUN = CHECKER | {
    "task_id": TASK,
    "routing_recommendation": "allow_review",
    "outcome_source": "auto_checker",
    "trigger_source": "submission.created",
    "locked_guide_version": "guide-1",
    "locked_post_submit_checker_policy_id": ACTOR,
    "locked_post_submit_checker_policy_version": "post-1",
    "locked_post_submit_checker_policy_hash": "sha256:" + "a" * 64,
    "locked_review_policy_id": ACTOR,
    "locked_review_policy_generation": 10**25,
    "locked_review_policy_hash": "sha256:" + "a" * 64,
    "locked_revision_policy_id": ACTOR,
    "locked_revision_policy_generation": 10**25,
    "locked_revision_policy_hash": "sha256:" + "a" * 64,
    "results": [
        CHECKER["results"][0] | {"message": "Manager detail", "blocks_review": True}
    ],
}


def _respond(response, body):
    response["body"] = json.dumps(body, ensure_ascii=False).encode()


def test_manager_context_wire_and_projection(cli):
    with http_fixture() as (origin, response, requests):
        for command, suffix, body in (
            ("task-requirements", "submission-requirements", REQUIREMENTS),
            ("task-locked-context", "locked-context", LOCKED),
            ("task-context", "work-context", MANAGER_CONTEXT),
        ):
            _respond(response, body)
            before = len(requests)
            result = cli(origin, TOKEN, "project", command, PROJECT, TASK, "-o", "json")
            assert result.returncode == 0 and json.loads(result.stdout) == body, (
                result.stderr
            )
            assert requests[before:] == [
                (
                    "GET",
                    f"/api/v1/projects/{PROJECT}/tasks/{TASK}/{suffix}",
                    "Bearer " + TOKEN,
                )
            ]
            text = cli(origin, TOKEN, "project", command, PROJECT, TASK)
            assert text.returncode == 0, text.stderr
            assert "\x1b" not in text.stdout and "\u202e" not in text.stdout
            assert len(requests) == before + 2


def test_manager_history_and_exact_run_wire(cli):
    cursor = "opaque+/=&?#\n"
    with http_fixture() as (origin, response, requests):
        for command, suffix, body in (
            (
                "task-submissions",
                f"/tasks/{TASK}/submissions",
                {"items": [MANAGER_HISTORY], "next_cursor": cursor},
            ),
            ("submission", f"/submissions/{SUBMISSION}", MANAGER_HISTORY),
            (
                "checker-runs",
                f"/submissions/{SUBMISSION}/checker-runs",
                {"items": [MANAGER_RUN], "next_cursor": cursor},
            ),
        ):
            _respond(response, body)
            selector = TASK if command == "task-submissions" else SUBMISSION
            args = ("project", command, PROJECT, selector)
            if command != "submission":
                args += ("--limit", "1", "--cursor", cursor)
            result = cli(origin, TOKEN, *args, "-o", "json")
            assert result.returncode == 0 and json.loads(result.stdout) == body, (
                result.stderr
            )
            url = urlsplit(requests[-1][1])
            assert url.path == f"/api/v1/projects/{PROJECT}{suffix}"
            if command != "submission":
                assert parse_qs(url.query) == {"limit": ["1"], "cursor": [cursor]}
            text = cli(origin, TOKEN, *args)
            assert text.returncode == 0 and "\x1b" not in text.stdout, text.stderr
        _respond(response, MANAGER_RUN)
        result = cli(
            origin,
            TOKEN,
            "project",
            "checker-runs",
            PROJECT,
            SUBMISSION,
            "--run",
            RUN,
            "-o",
            "json",
        )
        assert result.returncode == 0 and json.loads(result.stdout) == MANAGER_RUN, (
            result.stderr
        )
        assert (
            requests[-1][1]
            == f"/api/v1/projects/{PROJECT}/submissions/{SUBMISSION}/checker-runs/{RUN}"
        )


def test_manager_evidence_rejects_foreign_or_malformed_bodies(cli):
    cases = (
        ("task-requirements", TASK, REQUIREMENTS | {"project_id": OTHER}),
        ("task-locked-context", TASK, LOCKED | {"locked_review_policy_hash": "bad"}),
        (
            "task-context",
            TASK,
            MANAGER_CONTEXT | {"lifecycle": {"next_actions": ["claim"]}},
        ),
        (
            "task-submissions",
            TASK,
            {"items": [MANAGER_HISTORY | {"task_id": OTHER}], "next_cursor": None},
        ),
        ("submission", SUBMISSION, MANAGER_HISTORY | {"id": OTHER}),
        (
            "checker-runs",
            SUBMISSION,
            {"items": [MANAGER_RUN | {"submission_id": OTHER}], "next_cursor": None},
        ),
    )
    with http_fixture() as (origin, response, requests):
        for command, selector, body in cases:
            _respond(response, body)
            result = cli(
                origin, TOKEN, "project", command, PROJECT, selector, "-o", "json"
            )
            assert_failure(result, "invalid_api_response")
        _respond(response, MANAGER_RUN | {"id": OTHER})
        result = cli(
            origin,
            TOKEN,
            "project",
            "checker-runs",
            PROJECT,
            SUBMISSION,
            "--run",
            RUN,
            "-o",
            "json",
        )
        assert_failure(result, "invalid_api_response")
        before = len(requests)
        for args in (
            ("project", "task-context", "not-a-uuid", TASK),
            ("project", "task-submissions", PROJECT, TASK, "--cursor", ""),
            (
                "project",
                "checker-runs",
                PROJECT,
                SUBMISSION,
                "--run",
                RUN,
                "--cursor",
                "next",
            ),
        ):
            assert cli(origin, TOKEN, *args).returncode != 0
        assert len(requests) == before


def test_manager_evidence_rejects_oversized_success_without_output(cli):
    with http_fixture() as (origin, response, requests):
        oversized = deepcopy(LOCKED)
        oversized["locked_guide_version"] = "x" * 65536
        _respond(response, oversized)
        result = cli(
            origin, TOKEN, "project", "task-locked-context", PROJECT, TASK, "-o", "json"
        )
        assert_failure(result, "invalid_api_response")
        assert result.stdout == "" and len(requests) == 1
