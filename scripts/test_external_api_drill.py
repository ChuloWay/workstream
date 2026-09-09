"""Focused evidence-integrity tests for the standalone external-client drill."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

SOURCE = Path(__file__).resolve().parents[1] / "backend/scripts/external_api_drill.py"
SPEC = importlib.util.spec_from_file_location("external_api_drill", SOURCE)
drill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drill)


class ContractTests(unittest.TestCase):
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


class ExecutionTests(unittest.IsolatedAsyncioTestCase):
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
