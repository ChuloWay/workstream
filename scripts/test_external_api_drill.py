"""Focused evidence-integrity tests for the standalone external-client drill."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx

SOURCE = Path(__file__).resolve().parents[1] / "backend/scripts/external_api_drill.py"
SPEC = importlib.util.spec_from_file_location("external_api_drill", SOURCE)
drill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drill)


class ContractTests(unittest.TestCase):
    def test_collected_failure_keeps_cli_nonzero(self):
        async def failed_run(args, report):
            report["cases"].append({"result": "failed"})
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"
            args = SimpleNamespace(report=output, isolation_metadata=Path(directory) / "db.json")
            with patch.object(drill.argparse.ArgumentParser, "parse_args", return_value=args), \
                 patch.object(drill, "run", failed_run):
                self.assertEqual(drill.main(), 1)
            self.assertEqual(json.loads(output.read_text())["result"], "failed")

    def test_nested_field_inventory_does_not_claim_execution(self):
        document = {"paths": {"/items": {"post": {
            "requestBody": {"content": {"application/json": {"schema": {
                "$ref": "#/components/schemas/Input"}}}}, "responses": {}}}},
            "components": {"schemas": {"Input": {"properties": {"rules": {
                "type": "array", "items": {"properties": {"enabled": {"type": "boolean"}}}
            }}}}}}
        item = drill.inventory(document)["POST /items"]
        self.assertIn("body.rules[].enabled", item["uncovered_fields"])
        self.assertEqual(item["status"], "untested")
        self.assertEqual(item["field_cases"], {})

    def test_wrong_body_status_and_boolean_coercion_fail(self):
        for body, status in (({"enabled": False}, 200), ({"enabled": True}, 500),
                             ({"enabled": 1}, 200), ({}, 200)):
            with self.subTest(body=body, status=status):
                with self.assertRaises(drill.ProbeFailure):
                    drill.verify_response(httpx.Response(status, json=body), 200, {"enabled": True})
        self.assertEqual(drill.verify_response(httpx.Response(200, json={"enabled": True}),
                                              200, {"enabled": True}), {"enabled": True})

    def test_token_has_no_implicit_administrator(self):
        import base64
        issuer = drill.TokenIssuer()
        token = issuer.issue("contributor")
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        self.assertEqual(claims["roles"], [])
        self.assertEqual(claims["scope"], "workstream:access")
        self.assertEqual(claims["exp"] - claims["iat"], 600)
        self.assertNotIn(issuer.secret, token)

    def test_response_predicates_reject_missing_malformed_and_extra_fields(self):
        from uuid import uuid4
        valid = {"id": str(uuid4()), "created_at": "2026-01-01T00:00:00Z"}
        checks = {"id": drill.uuid_value, "created_at": drill.timestamp_value}
        for invalid in (valid | {"id": "not-uuid"}, valid | {"created_at": "yesterday"},
                        valid | {"created_at": "2026-01-01T00:00:00"},
                        valid | {"created_at": "9999-01-01T00:00:00Z"},
                        valid | {"secret": "should not appear"}, {"id": valid["id"]}):
            with self.subTest(invalid=invalid), self.assertRaises(drill.ProbeFailure):
                drill.verify_response(httpx.Response(200, json=invalid), 200, {}, checks, valid)
        self.assertEqual(drill.verify_response(httpx.Response(200, json=valid), 200, {},
                                              checks, valid), valid)


class ExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_response_assertions_are_mapped_and_header_can_be_omitted(self):
        def handler(request):
            self.assertNotIn("Idempotency-Key", request.headers)
            return httpx.Response(200, json={"enabled": True}, headers={
                name: request.headers[name] for name in ("X-Request-ID", "X-Correlation-ID")})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     base_url="http://127.0.0.1") as client:
            report = {}
            probe = drill.Drill(client, {"paths": {"/items": {"post": {}}}}, report)
            await probe.call("assert_enabled", "POST", "/items", payload={},
                             headers={"Idempotency-Key": None}, values={"enabled": True})
            self.assertEqual(report["operations"]["POST /items"]["field_cases"],
                             {"response.200.enabled": ["assert_enabled"]})
            with self.assertRaisesRegex(drill.ProbeFailure, "duplicate_case_name"):
                await probe.call("assert_enabled", "POST", "/items", payload={})

    async def test_denial_does_not_mark_operation_working(self):
        def handler(request):
            return httpx.Response(403, json={"error": {"code": "denied"}}, headers={
                name: request.headers[name] for name in ("X-Request-ID", "X-Correlation-ID")})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     base_url="http://127.0.0.1") as client:
            report = {}
            probe = drill.Drill(client, {"paths": {"/items": {"get": {}}}}, report)
            await probe.call("deny", "GET", "/items", expected=403,
                             values={"error.code": "denied"})
            self.assertEqual(report["operations"]["GET /items"]["status"], "denial_only")
            with self.assertRaises(drill.ProbeFailure):
                await probe.call("false_success", "GET", "/items", expected=200)
            self.assertEqual(report["cases"][-1]["result"], "failed")
            await probe.call("later_valid_denial", "GET", "/items", expected=403)
            self.assertEqual(report["operations"]["GET /items"]["status"], "failed")

    async def test_success_cannot_erase_prior_failure(self):
        def handler(request):
            return httpx.Response(200, json={"enabled": False}, headers={
                name: request.headers[name] for name in ("X-Request-ID", "X-Correlation-ID")})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                     base_url="http://127.0.0.1") as client:
            report = {}
            probe = drill.Drill(client, {"paths": {"/items": {"get": {}}}}, report)
            with self.assertRaises(drill.ProbeFailure):
                await probe.call("bad_body", "GET", "/items", values={"enabled": True})
            await probe.call("later_success", "GET", "/items", values={"enabled": False})
            self.assertEqual(report["operations"]["GET /items"]["status"], "failed")

    async def test_external_database_rejected_before_connecting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            path.write_text("{}")
            with patch.dict("os.environ", {"WORKSTREAM_DATABASE_URL":
                 "postgresql+asyncpg://test:secret@remote.invalid/production"}), \
                 patch.object(drill.asyncpg, "connect") as connect:
                with self.assertRaises(drill.ProbeFailure):
                    await drill.isolation(path)
                connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
