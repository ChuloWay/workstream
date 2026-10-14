"""Reject false evidence in the drill; these tests do not certify product APIs."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiments.pilot04_external_checker_runtime.guide_evidence import verify_source_commitment


class SourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.examples = [{"content": "Repair the worker", "title": None, "labels": []},
                         {"content": "Inspect another fault", "title": "Example", "labels": ["python"]}]
        self.expected = dict(examples=self.examples, examples_hash="sha256:" + "a" * 64,
                             source_hash="sha256:" + "b" * 64)
        self.source = dict(task_examples=deepcopy(self.examples),
                           task_examples_hash=self.expected["examples_hash"],
                           manifest_json={"task_examples_hash": self.expected["examples_hash"],
                                          "task_examples_count": 2},
                           bundle_hash=self.expected["source_hash"])
        self.attempt = {"canonical_input_hash": "sha256:" + "c" * 64,
                        "canonical_result": {"setup_notes": [
                            "Recorded provider observed examples " + self.expected["examples_hash"],
                            "Recorded provider observed input sha256:" + "c" * 64]}}

    def test_control_and_each_independent_source_substitution(self):
        verify_source_commitment(self.source, self.attempt, **self.expected)
        for field, value in (("task_examples", list(reversed(self.examples))),
                             ("task_examples_hash", "sha256:" + "d" * 64),
                             ("bundle_hash", "sha256:" + "d" * 64)):
            with self.subTest(field=field), self.assertRaisesRegex(AssertionError, "source commitment"):
                verify_source_commitment(self.source | {field: value}, self.attempt, **self.expected)
        for field, value in (("task_examples_hash", "sha256:" + "d" * 64),
                             ("task_examples_count", 1)):
            changed = deepcopy(self.source)
            changed["manifest_json"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(AssertionError, "source commitment"):
                verify_source_commitment(changed, self.attempt, **self.expected)

    def test_correct_storage_cannot_hide_different_worker_inputs(self):
        for index in (0, 1):
            changed = deepcopy(self.attempt)
            changed["canonical_result"]["setup_notes"][index] += "foreign"
            with self.subTest(index=index), self.assertRaisesRegex(AssertionError, "worker observed"):
                verify_source_commitment(self.source, changed, **self.expected)
        changed = self.attempt | {"canonical_input_hash": "sha256:" + "d" * 64}
        with self.assertRaisesRegex(AssertionError, "worker observed"):
            verify_source_commitment(self.source, changed, **self.expected)


if __name__ == "__main__":
    unittest.main()
