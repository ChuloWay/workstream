#!/usr/bin/env python3
"""Regression for the strict JSON registry boundary used by the POST driver."""

from __future__ import annotations

from uuid import UUID
import unittest

from execute_post import _registry_entry_from_json
from prepare_contract import _registry_entry


class RegistryJsonBoundaryTests(unittest.TestCase):
    def test_registry_entry_round_trips_through_strict_json_validation(self) -> None:
        expected = _registry_entry("sha256:" + "a" * 64)

        restored = _registry_entry_from_json(expected.model_dump(mode="json"))

        self.assertEqual(restored, expected)
        self.assertIsInstance(restored.registry_entry_id, UUID)
        self.assertIsInstance(restored.registration_operation_id, UUID)
        self.assertIsInstance(restored.registered_by_actor_profile_id, UUID)
        self.assertIsInstance(restored.authorization_decision_event_id, UUID)


if __name__ == "__main__":
    unittest.main()
