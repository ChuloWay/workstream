"""Focused evidence-integrity tests for the standalone external-client drill."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx

SOURCE = Path(__file__).resolve().parents[1] / "backend/scripts/external_api_drill.py"
SPEC = importlib.util.spec_from_file_location("external_api_drill", SOURCE)
drill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(drill)


class ContractTests(unittest.TestCase):
    def test_openapi_discovery_has_stable_failure_codes(self):
        cases = (
            (httpx.Response(503, json={"paths": {}}), "openapi_document_unavailable"),
            (httpx.Response(200, text="not JSON"), "openapi_document_invalid"),
            (httpx.Response(200, json=[]), "openapi_document_invalid"),
            (httpx.Response(200, json={"openapi": "3.1.0"}), "openapi_document_invalid"),
            (httpx.Response(200, json={"openapi": "3.1.0", "paths": []}),
             "openapi_document_invalid"),
        )
        for response, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(drill.ProbeFailure, "^" + code + "$"):
                drill.openapi_document(response)
        document = {"openapi": "3.1.0", "paths": {}}
        self.assertEqual(drill.openapi_document(httpx.Response(200, json=document)), document)

    def test_startup_accepts_eventual_health_without_ignoring_failures(self):
        client = SimpleNamespace(get=AsyncMock(side_effect=[
            httpx.ConnectError("not listening"), httpx.Response(503), httpx.Response(200)]))
        process = Mock()
        process.poll.return_value = None
        with patch.object(drill.asyncio, "sleep", new_callable=AsyncMock):
            drill.asyncio.run(drill.wait_for_server(client, process))
        self.assertEqual(client.get.await_count, 3)
        self.assertEqual(process.poll.call_count, 3)

    def test_startup_deadline_and_exited_server_remain_failures(self):
        client = SimpleNamespace(get=AsyncMock(return_value=httpx.Response(200)))
        process = Mock()
        process.poll.return_value = 1
        with self.assertRaisesRegex(drill.ProbeFailure, "^server_startup_failed$"):
            drill.asyncio.run(drill.wait_for_server(client, process))
        client.get.assert_not_awaited()
        process.poll.return_value = None
        with self.assertRaisesRegex(drill.ProbeFailure, "^server_startup_timeout$"):
            drill.asyncio.run(drill.wait_for_server(client, process, timeout_seconds=0))
        client.get.assert_not_awaited()

    def test_hanging_health_request_cannot_escape_deadline(self):
        async def hang(*args):
            await drill.asyncio.sleep(10)
        client = SimpleNamespace(get=AsyncMock(side_effect=hang))
        process = Mock()
        process.poll.return_value = None
        with self.assertRaisesRegex(drill.ProbeFailure, "^server_startup_timeout$"):
            drill.asyncio.run(drill.wait_for_server(client, process, timeout_seconds=0.01))
        client.get.assert_awaited_once()

    def test_cleanup_timeout_preserves_original_failure_and_rejects_success(self):
        for preserving_failure in (True, False):
            process = Mock()
            process.wait.side_effect = drill.subprocess.TimeoutExpired("server", 10)
            with self.subTest(preserving_failure=preserving_failure):
                if preserving_failure:
                    with self.assertRaisesRegex(drill.ProbeFailure, "^original_probe_failure$"):
                        try:
                            raise drill.ProbeFailure("original_probe_failure")
                        finally:
                            drill.stop_server(process, preserving_failure=True)
                else:
                    with self.assertRaisesRegex(drill.ProbeFailure, "^server_cleanup_timeout$"):
                        drill.stop_server(process, preserving_failure=False)
                process.terminate.assert_called_once_with()
                process.kill.assert_called_once_with()
                self.assertEqual(process.wait.call_count, 2)


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

    def test_nested_containers_do_not_coerce_boolean_integer_or_float(self):
        for actual, expected in (({"enabled": 1}, {"enabled": True}), ([1], [True]),
                                 ([{"values": [1.0]}], [{"values": [1]}]),
                                 ([1], [1, 2]), ({"a": 1, "b": 2}, {"a": 1})):
            with self.subTest(actual=actual, expected=expected), self.assertRaises(drill.ProbeFailure):
                drill.verify_response(httpx.Response(200, json={"nested": actual}),
                                      200, {"nested": expected})
        valid = {"nested": [{"enabled": True, "values": [1, None, "value"]}]}
        self.assertEqual(drill.verify_response(httpx.Response(200, json=valid), 200, valid), valid)

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
