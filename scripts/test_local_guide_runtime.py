"""Local guide parsing must retain the same isolation boundary as deployment."""

from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class LocalGuideRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
        self.services = self.compose["services"]

    def test_parser_has_no_secrets_network_or_source_mount(self):
        parser = self.services["guide-document-parser"]
        self.assertEqual(parser["network_mode"], "none")
        self.assertEqual(parser["user"], "10002:10001")
        self.assertTrue(parser["read_only"])
        self.assertEqual(parser["cap_drop"], ["ALL"])
        self.assertEqual(parser["security_opt"], ["no-new-privileges:true"])
        self.assertFalse(parser.get("environment"))
        self.assertFalse(parser.get("secrets"))
        self.assertEqual(parser["volumes"], ["guide_parser_socket:/var/lib/workstream/guide-runtime"])
        self.assertEqual(parser["pids_limit"], 32)
        self.assertEqual(parser["mem_limit"], "512m")
        self.assertEqual(parser["cpus"], 1.0)
        self.assertIn("size=64m", parser["tmpfs"][0])
        self.assertIn("--healthcheck", parser["healthcheck"]["test"])

    def test_only_worker_receives_provider_keys_and_readonly_parser_socket(self):
        for name in ("backend", "beat", "guide-document-parser"):
            service = self.services[name]
            self.assertFalse(
                {"OPENAI_API_KEY", "OPENROUTER_API_KEY"} & set(service.get("environment", {})),
                name,
            )
            if name != "guide-document-parser":
                self.assertFalse(any("guide_parser_socket:" in mount for mount in service["volumes"]))
        worker = self.services["worker"]
        self.assertIn("10001", worker["group_add"])
        self.assertIn("guide_parser_socket:/var/lib/workstream/guide-runtime:ro", worker["volumes"])
        self.assertEqual(worker["depends_on"]["guide-document-parser"]["condition"], "service_healthy")

    def test_images_create_private_directory_without_exposing_local_env(self):
        for name in ("dev", "release"):
            dockerfile = (ROOT / f"docker/backend/Dockerfile.{name}").read_text()
            self.assertIn("install -d -m 0750 -o 10002 -g 10001 /var/lib/workstream/guide-runtime", dockerfile)
        self.assertIn("backend/.env", (ROOT / ".dockerignore").read_text().splitlines())


if __name__ == "__main__":
    unittest.main()
