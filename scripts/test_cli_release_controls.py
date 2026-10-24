"""Release control rejection probes; no GitHub write or network required."""

from __future__ import annotations

from copy import deepcopy
import unittest

from check_cli_release_controls import (
    RULESET_NAME,
    validate_environment,
    validate_ruleset,
)


REPOSITORY = "Flow-Research/workstream"
ENVIRONMENT = {
    "name": "cli-release",
    "can_admins_bypass": False,
    "deployment_branch_policy": {"custom_branch_policies": True},
    "protection_rules": [
        {
            "type": "required_reviewers",
            "prevent_self_review": True,
            "reviewers": [{"type": "User"}],
        }
    ],
}
BRANCHES = {"total_count": 1, "branch_policies": [{"name": "main", "type": "branch"}]}
SUMMARY = [{"id": 10, "name": RULESET_NAME, "enforcement": "active"}]
RULESET = {
    "id": 10,
    "name": RULESET_NAME,
    "target": "tag",
    "source_type": "Repository",
    "source": REPOSITORY,
    "enforcement": "active",
    "bypass_actors": [],
    "conditions": {"ref_name": {"include": ["refs/tags/cli-v*"], "exclude": []}},
    "rules": [{"type": "update"}, {"type": "deletion"}],
}


class ReleaseControlsTest(unittest.TestCase):
    def test_exact_controls_pass(self) -> None:
        validate_environment(ENVIRONMENT, BRANCHES)
        validate_ruleset(SUMMARY, RULESET, REPOSITORY)

    def test_environment_administrator_bypass_must_be_explicitly_disabled(self) -> None:
        for value in (True, None, "false", "true", 0):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "administrator bypass"),
            ):
                validate_environment(
                    {**ENVIRONMENT, "can_admins_bypass": value}, BRANCHES
                )

    def test_environment_missing_administrator_bypass_fails(self) -> None:
        environment = deepcopy(ENVIRONMENT)
        del environment["can_admins_bypass"]
        with self.assertRaisesRegex(ValueError, "administrator bypass"):
            validate_environment(environment, BRANCHES)

    def test_hidden_bypass_field_is_not_treated_as_empty_proof(self) -> None:
        ruleset = deepcopy(RULESET)
        del ruleset["bypass_actors"]
        # Metadata-read tokens omit this field. Machine validation checks the
        # visible rules only; an administrator must inspect bypass actors.
        validate_ruleset(SUMMARY, ruleset, REPOSITORY)

    def test_environment_without_other_human_review_fails(self) -> None:
        for change in (
            {"protection_rules": []},
            {
                "protection_rules": [
                    {
                        "type": "required_reviewers",
                        "prevent_self_review": False,
                        "reviewers": [1],
                    }
                ]
            },
            {"deployment_branch_policy": {"custom_branch_policies": False}},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_environment({**ENVIRONMENT, **change}, BRANCHES)

    def test_extra_or_tag_branch_policy_fails(self) -> None:
        for policies in (
            [{"name": "main"}, {"name": "release/*"}],
            [{"name": "main", "type": "tag"}],
        ):
            with self.subTest(policies=policies), self.assertRaises(ValueError):
                validate_environment(
                    ENVIRONMENT,
                    {"total_count": len(policies), "branch_policies": policies},
                )

    def test_unprotected_or_bypassed_tag_fails(self) -> None:
        for key, value in (
            ("enforcement", "evaluate"),
            ("bypass_actors", [{"actor_type": "Team", "actor_id": 7}]),
            ("rules", [{"type": "deletion"}]),
            ("target", "branch"),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_ruleset(SUMMARY, {**RULESET, key: value}, REPOSITORY)

    def test_wrong_tag_pattern_or_source_fails(self) -> None:
        ruleset = deepcopy(RULESET)
        ruleset["conditions"]["ref_name"]["include"] = ["refs/tags/other-*"]
        with self.assertRaises(ValueError):
            validate_ruleset(SUMMARY, ruleset, REPOSITORY)
        with self.assertRaises(ValueError):
            validate_ruleset(SUMMARY, RULESET, "other/repository")


if __name__ == "__main__":
    unittest.main()
