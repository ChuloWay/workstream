"""Keep the revision contract gate aligned with durable timeout rejection."""

import unittest

from scripts.check_stale_review_contracts import scan_text


class RevisionTimeoutContractTests(unittest.TestCase):
    def test_deadline_rejection_receipt_is_allowed(self) -> None:
        for text in (
            "The revision deadline automatically rejects the outstanding attempt.",
            "Revision deadline expiry records a rejected outcome and releases the assignment.",
            "Timeout creates an immutable TASK rejection receipt and returns the task to ready.",
        ):
            with self.subTest(text=text):
                self.assertEqual(scan_text("docs/spec_review_lifecycle.md", text), [])

    def test_cap_only_rejection_remains_forbidden(self) -> None:
        for text in (
            "The revision limit automatically rejects the outstanding attempt.",
            "The worker auto-rejects after the revision limit.",
            "auto_reject_after_limit: true",
        ):
            with self.subTest(text=text):
                self.assertTrue(scan_text("docs/spec_review_lifecycle.md", text))

    def test_timeout_cannot_fabricate_a_human_review(self) -> None:
        for text in (
            "Timeout creates a reject Review.",
            "Revision deadline expiry inserts a Review record.",
            "The checker records a rejected outcome.",
        ):
            with self.subTest(text=text):
                self.assertTrue(scan_text("docs/spec_review_lifecycle.md", text))


if __name__ == "__main__":
    unittest.main()
