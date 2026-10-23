"""Verify visible hosted release controls; hidden bypass requires admin review."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess


TAG = re.compile(r"cli-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
RULESET_NAME = "Workstream CLI immutable tags"


def validate_environment(environment: dict, branches: dict) -> None:
    if environment.get("name") != "cli-release":
        raise ValueError("release environment identity mismatch")
    policy = environment.get("deployment_branch_policy") or {}
    if policy.get("custom_branch_policies") is not True:
        raise ValueError("release environment must restrict deployment branches")
    reviews = [
        rule
        for rule in environment.get("protection_rules", [])
        if rule.get("type") == "required_reviewers"
        and rule.get("prevent_self_review") is True
        and rule.get("reviewers")
    ]
    if len(reviews) != 1:
        raise ValueError("release environment requires other-human approval")
    branch_rows = branches.get("branch_policies")
    if (
        branches.get("total_count") != 1
        or not isinstance(branch_rows, list)
        or len(branch_rows) != 1
    ):
        raise ValueError("release environment must allow only main")
    branch = branch_rows[0]
    if branch.get("name") != "main" or branch.get("type", "branch") != "branch":
        raise ValueError("release environment must allow only main branch")


def validate_ruleset(summaries: list[dict], ruleset: dict, repository: str) -> None:
    matching = [
        item
        for item in summaries
        if item.get("name") == RULESET_NAME and item.get("enforcement") == "active"
    ]
    if len(matching) != 1 or matching[0].get("id") != ruleset.get("id"):
        raise ValueError("one active CLI tag ruleset is required")
    conditions = (ruleset.get("conditions") or {}).get("ref_name") or {}
    if (
        ruleset.get("name") != RULESET_NAME
        or ruleset.get("target") != "tag"
        or ruleset.get("source_type") != "Repository"
        or ruleset.get("source") != repository
        or ruleset.get("enforcement") != "active"
        or ("bypass_actors" in ruleset and ruleset["bypass_actors"] != [])
        or conditions.get("include") != ["refs/tags/cli-v*"]
        or conditions.get("exclude") != []
        or not {"update", "deletion"}.issubset(
            {rule.get("type") for rule in ruleset.get("rules", [])}
        )
    ):
        raise ValueError("CLI tag update/deletion protection is incomplete")


def github_json(path: str) -> object:
    result = subprocess.run(
        ["gh", "api", f"repos/{os.environ['GITHUB_REPOSITORY']}/{path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise ValueError("release control is unavailable through GitHub API")
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    if not TAG.fullmatch(args.tag):
        raise ValueError("invalid CLI release tag")
    repository = os.environ["GITHUB_REPOSITORY"]
    validate_environment(
        github_json("environments/cli-release"),
        github_json("environments/cli-release/deployment-branch-policies"),
    )
    summaries = github_json("rulesets?targets=tag")
    matching = [
        item
        for item in summaries
        if item.get("name") == RULESET_NAME and item.get("enforcement") == "active"
    ]
    if len(matching) != 1 or not isinstance(matching[0].get("id"), int):
        raise ValueError("one active CLI tag ruleset is required")
    validate_ruleset(
        summaries, github_json(f"rulesets/{matching[0]['id']}"), repository
    )


if __name__ == "__main__":
    main()
