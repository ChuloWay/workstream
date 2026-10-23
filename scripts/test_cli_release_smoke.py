"""Prove exact version output rejects misleading prefix/suffix and stderr."""

from __future__ import annotations

import subprocess
import unittest

from test_cli_release import check_version_output


VERSION = "v0.1.0+g" + "a" * 40


class VersionOutputTest(unittest.TestCase):
    def test_exact_output(self) -> None:
        check_version_output(
            subprocess.CompletedProcess([], 0, f"workstream version {VERSION}\n", ""),
            VERSION,
        )

    def test_prefix_suffix_or_warning_fails(self) -> None:
        for output, stderr in (
            (f"workstream version {VERSION}-WRONG\n", ""),
            (f"prefix workstream version {VERSION}\n", ""),
            (f"workstream version {VERSION}\n", "warning"),
        ):
            with (
                self.subTest(output=output, stderr=stderr),
                self.assertRaises(AssertionError),
            ):
                check_version_output(
                    subprocess.CompletedProcess([], 0, output, stderr), VERSION
                )


if __name__ == "__main__":
    unittest.main()
