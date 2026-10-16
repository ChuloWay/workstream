"""Focused regressions for the hosted release configuration."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_PATH = ROOT / "deploy" / "hosted" / "preflight.py"
ENTRYPOINT_PATH = ROOT / "docker" / "backend" / "release-entrypoint.sh"
ENV_EXAMPLE = ROOT / "deploy" / "hosted" / "release.env.example"
CHECKER_EXAMPLE = ROOT / "deploy" / "hosted" / "checker-service.example.json"

SPEC = importlib.util.spec_from_file_location("hosted_release_preflight", PREFLIGHT_PATH)
assert SPEC is not None and SPEC.loader is not None
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)


class HostedReleaseConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.runtime_uid = os.getuid() or 10001
        self.runtime_gid = os.getgid() or 10001
        self.checker_path = self.root / "checker.json"
        self.checker = json.loads(CHECKER_EXAMPLE.read_text(encoding="utf-8"))
        self.checker["sandbox_uid"] = self.runtime_uid
        self.checker["sandbox_gid"] = self.runtime_gid
        self.checker_path.write_text(json.dumps(self.checker), encoding="utf-8")
        environment_text = ENV_EXAMPLE.read_text(encoding="utf-8")
        environment_text = environment_text.replace(
            "WORKSTREAM_RUNTIME_UID=10001", f"WORKSTREAM_RUNTIME_UID={self.runtime_uid}"
        ).replace(
            "WORKSTREAM_RUNTIME_GID=10001", f"WORKSTREAM_RUNTIME_GID={self.runtime_gid}"
        ).replace(
            "WORKSTREAM_CHECKER_CONFIG_FILE=/etc/workstream/checker-service.json",
            f"WORKSTREAM_CHECKER_CONFIG_FILE={self.checker_path}",
        )
        self.environment_path = self.root / "release.env"
        self.environment_path.write_text(environment_text, encoding="utf-8")
        self.environment = preflight.parse_environment(self.environment_path)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_valid_configuration_and_rendered_topology(self) -> None:
        preflight.validate_environment(self.environment)
        preflight.validate_checker_config(self.checker, self.environment)
        rendered = preflight.render_compose(self.environment_path)
        preflight.validate_compose(rendered)
        self.assertEqual(set(rendered["services"]), {"api", "worker", "beat", "checker-service"})
        self.assertNotIn("build", rendered["services"]["api"])
        services = rendered["services"]
        for service in services.values():
            self.assertEqual(service["pull_policy"], "always")
            self.assertTrue(service["init"])
            self.assertEqual(service["restart"], "on-failure:5")
            self.assertTrue(service["healthcheck"]["test"])
        api_command = " ".join(services["api"]["command"])
        worker_command = " ".join(services["worker"]["command"])
        self.assertIn("alembic upgrade head", api_command)
        self.assertNotIn("--reload", api_command)
        self.assertIn("--pool=prefork", worker_command)
        health_commands = {
            name: " ".join(service["healthcheck"]["test"])
            for name, service in services.items()
        }
        self.assertIn("/api/v1/health", health_commands["api"])
        self.assertIn("/tmp/celery-worker.pid", health_commands["worker"])
        self.assertIn("/tmp/celerybeat.pid", health_commands["beat"])
        self.assertIn(".Runtimes.runsc", health_commands["checker-service"])
        self.assertEqual(services["api"]["stop_grace_period"], "30s")
        self.assertEqual(services["worker"]["stop_grace_period"], "1h1m40s")
        self.assertEqual(services["beat"]["stop_grace_period"], "30s")
        self.assertEqual(services["api"]["ports"][0]["host_ip"], "127.0.0.1")
        expected_secrets = {
            "database_url",
            "celery_broker_url",
            "api_rate_limit_key",
            "pagination_cursor_hmac",
            "openai_api_key",
        }
        self.assertEqual(set(rendered["secrets"]), expected_secrets)
        for name in ("api", "worker", "beat"):
            mounted = services[name]["secrets"]
            self.assertEqual({item["source"] for item in mounted}, expected_secrets)
            self.assertTrue(all(item["mode"] == 0o400 for item in mounted))
        self.assertNotIn("secrets", services["checker-service"])

    def test_environment_rejects_mutable_or_development_settings(self) -> None:
        cases = {
            "mutable image": ("WORKSTREAM_BACKEND_IMAGE", "registry.example/backend:latest"),
            "local HMAC": ("WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET", "private"),
            "static AWS key": ("WORKSTREAM_ARTIFACT_S3_ACCESS_KEY_ID", "private"),
            "ambient static AWS key": ("AWS_ACCESS_KEY_ID", "private"),
            "web identity token": ("AWS_WEB_IDENTITY_TOKEN_FILE", "/run/token"),
            "debug override": ("WORKSTREAM_DEBUG", "true"),
            "non-finite timeout": (
                "WORKSTREAM_ARTIFACT_S3_OPERATION_TOTAL_TIMEOUT_SECONDS",
                "NaN",
            ),
            "insecure issuer": ("WORKSTREAM_TOKEN_ISSUER", "http://identity.example/flow"),
            "insecure collector": ("WORKSTREAM_OBSERVABILITY_OTLP_ENDPOINT", "http://collector"),
            "introspection expansion": ("WORKSTREAM_TOKEN_INTROSPECTION_MODE", "required"),
            "unsupported identity transport": (
                "WORKSTREAM_ARTIFACT_S3_AWS_WORKLOAD_IDENTITY_METHOD",
                "assume-role-with-web-identity",
            ),
        }
        for label, (key, value) in cases.items():
            with self.subTest(label=label):
                changed = self.environment | {key: value}
                with self.assertRaises(preflight.PreflightError):
                    preflight.validate_environment(changed)

    def test_checker_config_rejects_non_hosted_or_substituted_identity(self) -> None:
        cases = {
            "runc": ("runtime", "runc"),
            "development isolation": ("isolation_mode", "docker-dev"),
            "wrong material root": ("material_root", "/tmp/material"),
            "root sandbox": ("sandbox_uid", 0),
            "empty cache": ("cache", []),
        }
        for label, (key, value) in cases.items():
            with self.subTest(label=label):
                changed = copy.deepcopy(self.checker)
                changed[key] = value
                with self.assertRaises(preflight.PreflightError):
                    preflight.validate_checker_config(changed, self.environment)
        changed = copy.deepcopy(self.checker)
        changed["cache"][0]["config_image_id"] = "sha256:" + "A" * 64
        with self.assertRaises(preflight.PreflightError):
            preflight.validate_checker_config(changed, self.environment)

    def test_rendered_topology_rejects_privilege_and_path_drift(self) -> None:
        rendered = preflight.render_compose(self.environment_path)
        cases = []
        mutable = copy.deepcopy(rendered)
        mutable["services"]["worker"]["image"] = "registry.example/workstream/backend:latest"
        cases.append(("mutable worker image", mutable))
        networked = copy.deepcopy(rendered)
        networked["services"]["checker-service"]["network_mode"] = "default"
        cases.append(("networked checker", networked))
        privileged = copy.deepcopy(rendered)
        privileged["services"]["checker-service"]["cap_drop"] = []
        cases.append(("checker capabilities", privileged))
        writable_material = copy.deepcopy(rendered)
        for mount in writable_material["services"]["checker-service"]["volumes"]:
            if mount["target"] == str(preflight.SCRATCH_ROOT):
                mount["read_only"] = False
        cases.append(("writable checker material", writable_material))
        root_controller = copy.deepcopy(rendered)
        root_controller["services"]["checker-service"]["user"] = "0:0"
        cases.append(("root checker controller", root_controller))
        extra_group = copy.deepcopy(rendered)
        extra_group["services"]["checker-service"]["group_add"].append("10002")
        cases.append(("extra checker group", extra_group))
        expanded_worker = copy.deepcopy(rendered)
        expanded_worker["services"]["worker"]["environment"]["UNREVIEWED"] = "true"
        cases.append(("worker environment drift", expanded_worker))
        for label, changed in cases:
            with self.subTest(label=label), self.assertRaises(preflight.PreflightError):
                preflight.validate_compose(changed)

    def test_private_metadata_rejects_empty_broad_and_linked_files(self) -> None:
        private_file = self.root / "secret"
        private_file.write_text("value", encoding="utf-8")
        private_file.chmod(0o400)
        preflight._private_metadata(
            private_file,
            kind="file",
            uid=os.getuid(),
            gid=os.getgid(),
            mode=0o400,
        )
        with self.assertRaises(preflight.PreflightError):
            preflight._private_metadata(
                private_file,
                kind="file",
                uid=os.getuid() + 1,
                gid=os.getgid(),
                mode=0o400,
            )
        private_file.chmod(0o440)
        with self.assertRaises(preflight.PreflightError):
            preflight._private_metadata(
                private_file,
                kind="file",
                uid=os.getuid(),
                gid=os.getgid(),
                mode=0o400,
            )
        private_file.chmod(0o600)
        private_file.write_text("", encoding="utf-8")
        private_file.chmod(0o400)
        with self.assertRaises(preflight.PreflightError):
            preflight._private_metadata(
                private_file,
                kind="file",
                uid=os.getuid(),
                gid=os.getgid(),
                mode=0o400,
            )
        target = self.root / "target"
        target.write_text("value", encoding="utf-8")
        link = self.root / "link"
        link.symlink_to(target)
        with self.assertRaises(preflight.PreflightError):
            preflight._private_metadata(
                link,
                kind="file",
                uid=os.getuid(),
                gid=os.getgid(),
                mode=0o400,
            )

    def test_private_host_inputs_check_exact_socket_group_without_reading_secrets(self) -> None:
        scratch = self.root / "scratch"
        socket_root = self.root / "socket"
        scratch.mkdir(mode=0o700)
        socket_root.mkdir(mode=0o700)
        os.chown(scratch, self.runtime_uid, self.runtime_gid)
        os.chown(socket_root, self.runtime_uid, self.runtime_gid)
        checker = self.root / "private-checker.json"
        checker.write_text("{}", encoding="utf-8")
        checker.chmod(0o400)
        os.chown(checker, self.runtime_uid, self.runtime_gid)
        secret_paths = []
        environment = dict(self.environment)
        environment["WORKSTREAM_CHECKER_CONFIG_FILE"] = str(checker)
        for index, key in enumerate(preflight.SECRET_FILE_KEYS):
            secret = self.root / f"secret-{index}"
            secret.write_text(f"private-{index}", encoding="utf-8")
            secret.chmod(0o400)
            os.chown(secret, self.runtime_uid, self.runtime_gid)
            environment[key] = str(secret)
            secret_paths.append(secret)
        docker_socket = self.root / "docker.sock"
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(str(docker_socket))
        try:
            environment["WORKSTREAM_DOCKER_SOCKET_GID"] = str(docker_socket.stat().st_gid)
            with (
                patch.object(preflight, "SCRATCH_ROOT", scratch),
                patch.object(preflight, "SOCKET_ROOT", socket_root),
                patch.object(preflight, "DOCKER_SOCKET", docker_socket),
            ):
                preflight.validate_private_host_inputs(environment)
                environment["WORKSTREAM_DOCKER_SOCKET_GID"] = str(
                    docker_socket.stat().st_gid + 1
                )
                with self.assertRaises(preflight.PreflightError):
                    preflight.validate_private_host_inputs(environment)
        finally:
            listener.close()


class ReleaseSecretLoaderTests(unittest.TestCase):
    def _run_loader(
        self,
        root: Path,
        *,
        content: str = "safe-value",
        override: tuple[str, Path] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        secret_names = {
            "WORKSTREAM_DATABASE_URL_FILE": "database",
            "WORKSTREAM_CELERY_BROKER_URL_FILE": "broker",
            "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET_FILE": "rate",
            "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET_FILE": "cursor",
            "OPENAI_API_KEY_FILE": "openai",
        }
        for variable, name in secret_names.items():
            path = root / name
            if path.exists():
                path.chmod(0o600)
            path.write_text(content, encoding="utf-8")
            path.chmod(0o400)
            environment[variable] = str(path)
        if override is not None:
            environment[override[0]] = str(override[1])
        environment["EXPECTED_OPENAI_SHA256"] = hashlib.sha256(content.encode()).hexdigest()
        program = (
            "import hashlib,os;"
            "value=os.environ['OPENAI_API_KEY'].encode();"
            "assert hashlib.sha256(value).hexdigest()==os.environ['EXPECTED_OPENAI_SHA256'];"
            "assert 'OPENAI_API_KEY_FILE' not in os.environ;"
            "print('loader-ok')"
        )
        return subprocess.run(
            ["/bin/sh", str(ENTRYPOINT_PATH), sys.executable, "-c", program],
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def test_loader_does_not_evaluate_or_log_secret_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "evaluated"
            content = f"$(touch {marker}) `touch {marker}` ; private"
            completed = self._run_loader(root, content=content)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout, "loader-ok\n")
            self.assertEqual(completed.stderr, "")
            self.assertFalse(marker.exists())
            self.assertNotIn(content, completed.stdout + completed.stderr)

    def test_loader_rejects_empty_missing_directory_and_symlink_without_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases: list[tuple[str, Path]] = []
            empty = root / "empty"
            empty.touch()
            cases.append(("empty", empty))
            cases.append(("missing", root / "missing"))
            directory = root / "directory"
            directory.mkdir()
            cases.append(("directory", directory))
            target = root / "target"
            target.write_text("do-not-print", encoding="utf-8")
            symlink = root / "symlink"
            symlink.symlink_to(target)
            cases.append(("symlink", symlink))
            broad = root / "broad"
            broad.write_text("do-not-print", encoding="utf-8")
            broad.chmod(0o440)
            cases.append(("broad mode", broad))
            for label, invalid in cases:
                with self.subTest(label=label):
                    completed = self._run_loader(
                        root,
                        override=("WORKSTREAM_DATABASE_URL_FILE", invalid),
                    )
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertEqual(completed.stdout, "")
                    self.assertIn("WORKSTREAM_DATABASE_URL", completed.stderr)
                    self.assertNotIn("do-not-print", completed.stderr)


if __name__ == "__main__":
    unittest.main()
