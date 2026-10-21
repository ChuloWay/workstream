#!/usr/bin/env python3
"""Regression for the strict JSON registry boundary used by the POST driver."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
from uuid import UUID
import unittest

from app.core.identifiers import new_record_id
from app.modules.checkers.api.external import (
    ExternalCheckerExecutionRequest,
    PostSubmitExternalCheckerIdentity,
    make_external_checker_execution_result,
)
import execute_pre
from execute_post import _post_material, _registry_entry_from_json
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

    def test_post_material_uses_the_runtime_grant_archive_role(self) -> None:
        identifiers = [new_record_id() for _ in range(14)]
        identity = PostSubmitExternalCheckerIdentity(
            project_id=identifiers[0],
            task_id=identifiers[1],
            assignment_id=identifiers[2],
            submission_id=identifiers[3],
            submission_version=1,
            evaluation_request_id=identifiers[4],
            evaluation_request_digest="sha256:" + "1" * 64,
            evaluation_generation=1,
            attempt_id=identifiers[5],
            result_id=identifiers[6],
            lease_id=identifiers[7],
            lease_generation=1,
            lease_expires_at=datetime(2026, 10, 17, tzinfo=timezone.utc)
            + timedelta(hours=1),
        )

        material = _post_material(
            identity,
            identifiers,
            (),
            "sha256:" + "2" * 64,
        )

        self.assertEqual(material.role, "submission_archive")

    def test_pre_driver_uses_the_real_pre_phase_and_verifies_a_bound_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract = root / "contract.json"
            request_path = root / "request.json"
            result_path = root / "result.json"
            fact_path = root / "fact.json"
            entry = _registry_entry("sha256:" + "a" * 64)
            contract.write_text(
                json.dumps(
                    {
                        "configuration": {
                            "external_task_id": "terminal-ledger-reconcile",
                            "schema_version": "terminal_benchmark_project.v1",
                        },
                        "registry": entry.model_dump(mode="json"),
                    }
                ),
                encoding="utf-8",
            )
            package = (
                Path(__file__).parents[2]
                / "pilots/terminal_benchmark/packages/ledger-reconcile"
            )

            execute_pre.request(contract, package, request_path)
            request = ExternalCheckerExecutionRequest.model_validate_json(
                request_path.read_text(encoding="utf-8")
            )
            self.assertEqual(request.identity.phase, "pre_submit")
            self.assertEqual(request.registry.phase, "pre_submit")
            self.assertNotEqual(
                request.registry.registry_entry_id, entry.registry_entry_id
            )
            self.assertEqual(
                [item.role for item in request.materials], ["submission_archive"]
            )
            result = make_external_checker_execution_result(
                request_digest=request.request_digest,
                registry_entry_id=request.registry.registry_entry_id,
                registry_entry_digest=request.registry.entry_digest,
                phase="pre_submit",
                outcome="completed",
                verdict="passed",
                findings=(),
                infrastructure_failure_code=None,
            )
            result_path.write_text(
                result.model_dump_json() + "\n",
                encoding="utf-8",
            )

            execute_pre.verify(request_path, result_path, fact_path)

            fact = json.loads(fact_path.read_text(encoding="utf-8"))
            self.assertEqual(fact["request_digest"], request.request_digest)
            self.assertEqual(fact["result_digest"], result.result_digest)


if __name__ == "__main__":
    unittest.main()
