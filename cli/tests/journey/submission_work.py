"""Real CLI intake, durable evaluation and unpaid contribution observation."""

import csv
import hashlib
import json
import time
from uuid import uuid4
from zipfile import ZipFile


def submit_and_observe(
    client, tokens, actors, project_id, task_id, assignment_id, grant
):
    token = tokens["alice"]
    packet = (
        "--assignment",
        assignment_id,
        "--summary",
        "Local declared-proof format exercise",
        "--attestation",
        "These are illustrative format claims, not verified remote work.",
    )
    rejected = client.directory / "rejected.zip"
    with ZipFile(rejected, "x") as bundle:
        bundle.writestr("proof.json", "{}")
    failure = client.call(
        token,
        "task",
        "prepare",
        task_id,
        *packet,
        "--file",
        str(rejected),
        "--idempotency-key",
        str(uuid4()),
        expected_exit=1,
    )
    if failure["error"]["code"] != "pre_submission_checker_failed":
        raise AssertionError("invalid declared proof was not rejected by intake")
    # Exact task-history resolution requires an existing Submission. The self
    # collection supports an empty result and is the appropriate absence proof.
    if client.call(token, "me", "submissions", "--task", task_id)["items"]:
        raise AssertionError("rejected candidate created a submission")
    archive = client.directory / "submission.zip"
    with ZipFile(archive, "x") as bundle:
        bundle.writestr(
            "proof.json",
            json.dumps(
                {
                    "schema": "harnessy.work.proof.v1",
                    "commit_sha": "a" * 40,
                    "pr_url": "https://github.com/example/format-exercise/pull/1",
                    "ci_run_url": "https://github.com/example/format-exercise/actions/runs/1",
                    "ci_conclusion": "success",
                    "merged": True,
                }
            ),
        )
    archive_hash = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
    command = (
        "task",
        "prepare",
        task_id,
        *packet,
        "--file",
        str(archive),
        "--idempotency-key",
        str(uuid4()),
    )
    first = client.call(token, *command)
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        page = client.call(token, "task", "preparations", task_id)
        matching = [
            item for item in page["items"] if item["archive_sha256"] == archive_hash
        ]
        if len(matching) > 1:
            raise AssertionError("one preparation request produced duplicate runs")
        if matching and matching[0]["state"] == "ready":
            ready = matching[0]
            break
        if matching and matching[0]["state"] in {
            "checks_failed",
            "infrastructure_failed",
            "stale",
        }:
            raise AssertionError("real intake failed; no substitution permitted")
        time.sleep(1)
    else:
        raise AssertionError("real intake did not reach ready admission")
    replay = client.call(token, *command)
    if (
        replay["put_attempt_id"] != first["put_attempt_id"]
        or replay["admission_id"] != ready["admission_id"]
        or replay["replayed"] is not True
    ):
        raise AssertionError("exact preparation replay changed custody")
    submit = ("task", "submit", task_id, *packet, "--admission", ready["admission_id"])
    receipt = client.call(token, *submit)
    if client.call(token, *submit) != receipt:
        raise AssertionError("exact submission replay changed receipt")
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        outcome = client.call(token, "submission", "show", receipt["submission_id"])
        if outcome["status"] == "accepted":
            break
        if outcome["status"] in {"rejected", "needs_revision"}:
            raise AssertionError(
                "real checker did not reach the expected acceptance branch"
            )
        time.sleep(1)
    else:
        raise AssertionError("durable evaluation did not reach acceptance")
    records = client.call(token, "contributions", "--project", project_id)["items"]
    if len(records) != 1:
        raise AssertionError("expected exactly one unpaid submitter contribution")
    record = records[0]
    for field, value in {
        "task_id": task_id,
        "project_id": project_id,
        "submission_id": receipt["submission_id"],
        "contributor_id": actors["alice"],
        "source_task_assignment_id": assignment_id,
        "contribution_type": "accepted_submission",
        "awards": [],
        "source_review_id": None,
        "source_review_lease_id": None,
    }.items():
        if record[field] != value:
            raise AssertionError("contribution differs from the exercised attempt")
    if not record["source_final_acceptance_id"]:
        raise AssertionError("accepted contribution lacks final acceptance provenance")
    exported = client.call(tokens["finance"], "project", "contributions", project_id)
    if exported["items"] != records:
        raise AssertionError("authorized project export differs from own evidence")
    destination = client.directory / "contributions.csv"
    saved = client.call(
        token, "contributions", "--project", project_id, "--csv", str(destination)
    )
    if saved != {"format": "csv", "saved": True}:
        raise AssertionError("CSV publication did not report success")
    with destination.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 1:
        raise AssertionError("CSV duplicated or lost the unpaid contribution")
    for field in (
        "contribution_id",
        "project_id",
        "task_id",
        "submission_id",
        "contributor_id",
        "source_final_acceptance_id",
        "source_task_assignment_id",
        "artifact_hash",
        "contribution_policy_version_id",
    ):
        if rows[0][field] != record[field]:
            raise AssertionError("CSV lineage differs from JSON evidence")
    client.call(token, "project", "show", project_id)
    client.write_and_replay(
        tokens["manager"],
        "project",
        "role-grant",
        "revoke",
        project_id,
        grant["id"],
        body={"reason": "Verify fresh authority after completed journey"},
    )
    denied = client.call(token, "project", "show", project_id, expected_exit=1)
    if denied["error"].get("status") != 404:
        raise AssertionError("revoked project grant still permits protected inspection")
    return receipt
