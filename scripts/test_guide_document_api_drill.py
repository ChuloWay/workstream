"""Isolation checks for the live guide drill; these do not certify product APIs."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/scripts"))
SPEC = importlib.util.spec_from_file_location("guide_document_api_drill", ROOT / "backend/scripts/guide_document_api_drill.py")
guide = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guide)


class IsolationTests(unittest.IsolatedAsyncioTestCase):
    def test_sufficiency_response_rejects_empty_duplicate_or_foreign_lineage(self):
        setup = {"id": "setup-a", "output_sufficiency_report_id": "report-a",
                 "project_id": "project-a", "guide_id": "guide-a", "guide_version": "initial",
                 "source_snapshot_id": "snapshot-a", "setup_generation": 1}
        expected = {"id": "report-a", "project_setup_run_id": "setup-a",
                    **{key: value for key, value in setup.items()
                       if key not in {"id", "output_sufficiency_report_id"}}}
        self.assertTrue(guide.sufficiency_matches([expected], setup))
        invalid = [[], {}, [expected, expected], [None], [expected | {"setup_generation": True}]]
        invalid.extend([expected | {key: "foreign"}] for key in expected)
        invalid.extend([{key: value for key, value in expected.items() if key != omitted}]
                       for omitted in expected)
        import httpx
        for body in invalid:
            with self.subTest(body=body):
                with self.assertRaises(guide.api.ProbeFailure):
                    guide.api.verify_response(httpx.Response(200, json=body), 200, {},
                        checks={"$": lambda value: guide.sufficiency_matches(value, setup)})
        self.assertEqual(guide.api.verify_response(httpx.Response(200, json=[expected]), 200, {},
            checks={"$": lambda value: guide.sufficiency_matches(value, setup)}), [expected])

    def runtime(self):
        return {
            "WORKSTREAM_DRILL_PROVIDER_ENV": "/private/provider.env",
            "WORKSTREAM_DRILL_GUIDE_PARSER_SOCKET": "/var/lib/workstream/guide-runtime/guide.sock",
            "WORKSTREAM_TEST_MINIO_ENDPOINT": "http://127.0.0.1:9000",
            "WORKSTREAM_DRILL_BROKER_URL": "redis://127.0.0.1:12345/0",
            "WORKSTREAM_TEST_MINIO_BUCKET": "owned-bucket",
            "WORKSTREAM_TEST_MINIO_PREFIX": "owned-prefix",
            "WORKSTREAM_DRILL_SCRATCH_ROOT": "/private/owned-scratch",
        }

    def test_provider_file_cannot_override_isolated_database_identity_or_storage(self):
        provider = {"OPENROUTER_API_KEY": "not-a-real-key", "WORKSTREAM_PROJECT_AGENT_MODEL": "configured-model",
                    "WORKSTREAM_DATABASE_URL": "production-database", "WORKSTREAM_AUTH_PROVIDER": "unsafe",
                    "WORKSTREAM_ARTIFACT_S3_BUCKET": "production-bucket",
                    "WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET": "/private/foreign.sock"}
        env = {"WORKSTREAM_DATABASE_URL": "isolated-database", "WORKSTREAM_AUTH_PROVIDER": "flow"}
        report = {}
        with patch.dict(guide.os.environ, self.runtime(), clear=True), patch.object(guide, "dotenv_values", return_value=provider):
            guide.environment(env, report)
        self.assertEqual(env["WORKSTREAM_DATABASE_URL"], "isolated-database")
        self.assertEqual(env["WORKSTREAM_AUTH_PROVIDER"], "flow")
        self.assertEqual(env["WORKSTREAM_ARTIFACT_S3_BUCKET"], "owned-bucket")
        self.assertEqual(env["WORKSTREAM_PROJECT_AGENT_MODEL"], "configured-model")
        self.assertNotIn("WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET", env)
        self.assertEqual(env["WORKSTREAM_DRILL_GUIDE_PARSER_SOCKET"],
                         "/var/lib/workstream/guide-runtime/guide.sock")
        for scope in ("TASK", "PRODUCER", "PROJECT", "DEPLOYMENT"):
            self.assertGreater(int(env[f"WORKSTREAM_ARTIFACT_ADMISSION_{scope}_MAXIMUM_BYTES"]), 0)
        self.assertNotIn("not-a-real-key", str(report))

    def test_only_selected_provider_credential_reaches_worker(self):
        for provider, selected, unselected in (
            ("openrouter", "OPENROUTER_API_KEY", "OPENAI_API_KEY"),
            ("openai", "OPENAI_API_KEY", "OPENROUTER_API_KEY"),
        ):
            values = {"WORKSTREAM_PROJECT_AGENT_MODEL_PROVIDER": provider,
                      selected: "selected-secret", unselected: "other-secret"}
            env = {unselected: "inherited-secret"}
            with self.subTest(provider=provider), patch.dict(guide.os.environ, self.runtime(), clear=True), patch.object(guide, "dotenv_values", return_value=values):
                guide.environment(env, {})
            self.assertEqual(env[selected], "selected-secret")
            self.assertNotIn(unselected, env)

    def test_remote_runtime_is_rejected(self):
        for key in ("WORKSTREAM_TEST_MINIO_ENDPOINT", "WORKSTREAM_DRILL_BROKER_URL"):
            with self.subTest(key=key), patch.dict(guide.os.environ, self.runtime() | {key: "https://remote.example"}, clear=True), patch.object(guide, "dotenv_values", return_value={"OPENROUTER_API_KEY": "test"}):
                with self.assertRaises(guide.api.ProbeFailure):
                    guide.environment({}, {})

    def test_parser_socket_requires_an_explicit_absolute_trusted_path(self):
        for value in (None, "relative/guide.sock"):
            runtime = self.runtime()
            if value is None:
                runtime.pop("WORKSTREAM_DRILL_GUIDE_PARSER_SOCKET")
            else:
                runtime["WORKSTREAM_DRILL_GUIDE_PARSER_SOCKET"] = value
            with self.subTest(value=value), patch.dict(guide.os.environ, runtime, clear=True), \
                    patch.object(guide, "dotenv_values", return_value={"OPENROUTER_API_KEY": "test"}):
                with self.assertRaisesRegex(
                        guide.api.ProbeFailure, "^guide_parser_socket_missing_or_invalid$"):
                    guide.environment({}, {})

    async def test_parser_prerequisite_denies_missing_and_malformed_services(self):
        class MissingParser:
            async def parse(self, request, source):
                raise guide.ExternalServiceUnavailableError()

        class MalformedParser:
            async def parse(self, request, source):
                raise guide.ExternalServiceProtocolError()

        env = {"WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET":
               "/var/lib/workstream/guide-runtime/guide.sock"}
        for adapter, code in ((MissingParser(), "guide_parser_prerequisite_unavailable"),
                              (MalformedParser(), "guide_parser_prerequisite_malformed")):
            with self.subTest(code=code), patch.object(
                    guide, "UnixSocketGuideDocumentParserAdapter", return_value=adapter):
                with self.assertRaisesRegex(guide.api.ProbeFailure, f"^{code}$"):
                    await guide.parser_prerequisite(env, {})

    async def test_parser_prerequisite_accepts_one_exact_synthetic_parse(self):
        calls = []

        class ValidParser:
            async def parse(self, request, source):
                calls.append((request, source))
                return SimpleNamespace(text=source.decode("utf-8"),
                    total_characters=len(source.decode("utf-8")), next_offset=None,
                    parser_build_digest=guide.FIXED_PARSER_BUILD_DIGEST)

        env = {"WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET":
               "/var/lib/workstream/guide-runtime/guide.sock"}
        report = {}
        with patch.object(guide, "UnixSocketGuideDocumentParserAdapter", return_value=ValidParser()):
            await guide.parser_prerequisite(env, report)
        self.assertEqual(len(calls), 1)
        request, source = calls[0]
        self.assertEqual(source, guide._PARSER_PROBE_SOURCE)
        self.assertEqual((request.media_type, request.operation), ("text/markdown", "read"))
        self.assertEqual(request.source_byte_count, len(source))
        self.assertEqual(request.source_sha256,
                         "sha256:" + guide.hashlib.sha256(source).hexdigest())
        self.assertEqual(report, {"guide_parser_prerequisite": {
            "protocol": guide.GUIDE_DOCUMENT_PARSER_PROTOCOL,
            "parser_build_digest": guide.FIXED_PARSER_BUILD_DIGEST,
        }})
        self.assertNotIn(source.decode("utf-8"), str(report))

    async def test_scenario_checks_parser_before_reading_product_documents(self):
        prerequisite = AsyncMock(
            side_effect=guide.api.ProbeFailure("guide_parser_prerequisite_unavailable"))
        with patch.object(guide, "parser_prerequisite", prerequisite):
            with self.assertRaisesRegex(
                    guide.api.ProbeFailure, "^guide_parser_prerequisite_unavailable$"):
                await guide.scenario(SimpleNamespace(report={}), object(), {
                    "WORKSTREAM_DRILL_GUIDE_PARSER_SOCKET":
                        "/var/lib/workstream/guide-runtime/guide.sock"})
        prerequisite.assert_awaited_once()
        worker_env = prerequisite.await_args.args[0]
        self.assertNotIn("WORKSTREAM_DRILL_GUIDE_PARSER_SOCKET", worker_env)
        self.assertEqual(worker_env["WORKSTREAM_GUIDE_DOCUMENT_PARSER_SOCKET"],
                         "/var/lib/workstream/guide-runtime/guide.sock")


if __name__ == "__main__":
    unittest.main()
