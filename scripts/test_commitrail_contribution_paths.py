"""Exercise advertised contribution paths through the shared validator."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_commitrail_records as gate


class ContributionPathTests(unittest.TestCase):
    standalone = ".commitrail/changes/fix-guide-validation.md"
    initiative = ".commitrail/initiatives/WS-EXAMPLE-001/WS-EXAMPLE-001-01.md"

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write(".commitrail/INDEX.md", "# Engineering index\n")
        self.write(
            ".commitrail/CHANGE_TEMPLATE.md",
            "# <Change ID> — <Outcome>\n\n- [ ] `<observable result>`\n",
        )

    def write(self, path: str, text: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    @staticmethod
    def record() -> str:
        return (
            "# Fix guide validation\n\n- Initiative: None\n"
            "- Durable disposition: Complete\n"
            "- Intended merge outcome: Reject invalid guide identities.\n\n"
            "## Intent\nAvoid invalid persisted guide identities.\n"
            "## Bounded change\nGuide validator and its regression.\n"
            "## Acceptance criteria\nEmpty guide identities are rejected.\n"
            "## Risk and review routing\nL1; QA and security inspect validation.\n"
            "## Evidence\nThe empty-identity regression fails before the fix.\n"
        )

    def validate(self, paths: list[str]) -> None:
        # This suite owns contribution routing, not Git discovery/archive custody.
        # All Markdown, content, record counting and parent checks execute normally.
        with patch.object(gate, "tracked_legacy_paths", return_value=[]):
            gate.validate(self.root, paths)

    def add_initiative(self) -> None:
        self.write(
            ".commitrail/INDEX.md",
            "| Initiative | Durable disposition | Next |\n|---|---|---|\n"
            "| WS-EXAMPLE-001 | Planned | Next change |\n",
        )
        self.write(
            ".commitrail/initiatives/WS-EXAMPLE-001/OVERVIEW.md",
            "# Example\n\n- Disposition: Planned\n",
        )
        self.write(
            self.initiative,
            self.record().replace("Initiative: None", "Initiative: WS-EXAMPLE-001"),
        )

    def test_standalone_backend_record_needs_no_initiative(self) -> None:
        self.write(self.standalone, self.record())
        self.assertFalse((self.root / ".commitrail/initiatives").exists())
        self.validate(["backend/app/example.py", self.standalone])

    def test_editorial_readme_and_ordinary_docs_need_no_record(self) -> None:
        for paths in (
            ["README.md"],
            ["docs/quickstart.md"],
            ["README.md", "docs/quickstart.md"],
        ):
            with self.subTest(paths=paths):
                self.validate(paths)

    def test_standalone_requires_one_live_explicit_no_initiative(self) -> None:
        for owner in (
            "",
            "- Initiative: WS-EXAMPLE-001\n",
            "<!-- - Initiative: None -->\n",
            "- Initiative: None\n- Initiative: WS-EXAMPLE-001\n",
            "- Initiative: None\n- Initiative: None\n",
        ):
            with self.subTest(owner=owner):
                self.write(
                    self.standalone,
                    self.record().replace("- Initiative: None\n", owner),
                )
                with self.assertRaisesRegex(
                    gate.CommitrailError, "STANDALONE_INITIATIVE_INVALID"
                ):
                    self.validate([self.standalone])

    def test_standalone_accepts_inline_code_no_initiative(self) -> None:
        self.write(
            self.standalone,
            self.record().replace("Initiative: None", "Initiative: `None`"),
        )
        self.validate([self.standalone])

    def test_readme_does_not_exempt_implementation_or_process_controls(self) -> None:
        for path in (
            "backend/app/example.py",
            "scripts/example.py",
            "frontend/src/main.ts",
            "AGENTS.md",
            "CONTRIBUTING.md",
            ".github/pull_request_template.md",
            ".github/workflows/backend.yml",
            ".ci/example.json",
            ".agents/skills/example/SKILL.md",
            ".codex/agents/example.toml",
            "docs/engineering/example.md",
            ".commitrail/INDEX.md",
        ):
            with self.subTest(path=path):
                with self.assertRaisesRegex(
                    gate.CommitrailError, "CHANGE_RECORD_REQUIRED"
                ):
                    self.validate(["README.md", path])

    def test_one_record_across_both_layouts(self) -> None:
        self.add_initiative()
        self.write(self.standalone, self.record())
        with self.assertRaisesRegex(gate.CommitrailError, "MULTIPLE_CHANGE_RECORDS"):
            self.validate([self.standalone, self.initiative])

    def test_two_standalone_records_are_rejected(self) -> None:
        second = ".commitrail/changes/another-change.md"
        self.write(self.standalone, self.record())
        self.write(second, self.record())
        with self.assertRaisesRegex(gate.CommitrailError, "MULTIPLE_CHANGE_RECORDS"):
            self.validate([self.standalone, second])

    def test_invalid_standalone_name_cannot_hide_beside_valid_record(self) -> None:
        self.write(self.standalone, self.record())
        for name in (
            "Bad_Name.md",
            "nested/change.md",
            "-change.md",
            "change--name.md",
            "notes.txt",
        ):
            invalid = f".commitrail/changes/{name}"
            with self.subTest(name=name):
                self.write(invalid, self.record())
                with self.assertRaisesRegex(
                    gate.CommitrailError, "RECORD_PATH_INVALID"
                ):
                    self.validate([self.standalone, invalid])

    def test_standalone_uses_existing_content_checks(self) -> None:
        valid = self.record()
        corruptions = (
            (valid.replace("Complete", "Approved"), "DISPOSITION_INVALID"),
            (valid.replace("## Evidence", "## Commentary"), "FIELD_MISSING"),
            (
                valid.replace(
                    "The empty-identity regression fails before the fix.",
                    "<!-- hidden -->",
                ),
                "FIELD_EMPTY",
            ),
            (valid.replace("Reject invalid guide identities.", ""), "FIELD_EMPTY"),
            (valid + "\n- CI: pending\n", "TRANSIENT_STATE"),
            (
                valid.replace(
                    "Empty guide identities are rejected.", "`<observable result>`"
                ),
                "TEMPLATE_MARKER",
            ),
            (f"```markdown\n{valid}\n```\n", "DISPOSITION_INVALID"),
        )
        for text, error in corruptions:
            with self.subTest(error=error, text=text):
                self.write(self.standalone, text)
                with self.assertRaisesRegex(gate.CommitrailError, error):
                    self.validate(["backend/app/example.py", self.standalone])

    def test_standalone_does_not_bypass_global_index_consistency(self) -> None:
        self.add_initiative()
        self.write(self.standalone, self.record())
        self.write(
            ".commitrail/initiatives/WS-EXAMPLE-001/OVERVIEW.md",
            "# Example\n\n- Disposition: Complete\n",
        )
        with self.assertRaisesRegex(gate.CommitrailError, "INDEX_OVERVIEW_MISMATCH"):
            self.validate([self.standalone])

    def test_existing_initiative_still_requires_its_overview(self) -> None:
        self.add_initiative()
        (self.root / ".commitrail/initiatives/WS-EXAMPLE-001/OVERVIEW.md").unlink()
        with self.assertRaisesRegex(gate.CommitrailError, "OVERVIEW_MISSING"):
            self.validate([self.initiative])

    def test_existing_initiative_still_requires_matching_record_owner(self) -> None:
        self.add_initiative()
        wrong = ".commitrail/initiatives/WS-EXAMPLE-001/WS-OTHER-001-01.md"
        self.write(wrong, self.record())
        with self.assertRaisesRegex(gate.CommitrailError, "RECORD_OWNER_MISMATCH"):
            self.validate([wrong])


if __name__ == "__main__":
    unittest.main()
