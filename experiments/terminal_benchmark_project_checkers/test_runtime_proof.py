#!/usr/bin/env python3
"""Focused fixtures for the WS493 launch boundary and matrix reducer."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import build_matrix


HEAD = "a" * 40
GRANT_ID = "extract_" + "b" * 32


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _write_ndjson(path: Path, values: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(value, sort_keys=True) + "\n" for value in values),
        encoding="utf-8",
    )


class MatrixReducerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.raw = Path(self.temporary.name)
        self.launches = [
            {
                "kind": "checker",
                "container_id": "c1",
                "name": "ws-checker-a",
                "mount_source_identities": build_matrix.SOURCE_IDENTITIES["checker"],
            },
            {
                "kind": "checker",
                "container_id": "c2",
                "name": "ws-checker-b",
                "mount_source_identities": build_matrix.SOURCE_IDENTITIES["checker"],
            },
            {
                "kind": "builder",
                "attempt": "dead",
                "container_id": "b0",
                "name": "ws-terminal-builder-dead",
                "mount_source_identities": build_matrix.SOURCE_IDENTITIES["builder"],
            },
            {
                "kind": "builder",
                "attempt": "good",
                "container_id": "b1",
                "name": "ws-terminal-builder-good",
                "mount_source_identities": build_matrix.SOURCE_IDENTITIES["builder"],
            },
            {
                "kind": "candidate",
                "attempt": "good",
                "container_id": "c3",
                "name": "ws-terminal-candidate-good",
                "mount_source_identities": build_matrix.SOURCE_IDENTITIES["candidate"],
            },
            *[
                {
                    "kind": "reference",
                    "attempt": "good",
                    "container_id": f"r{index}",
                    "name": f"ws-terminal-reference-good-{index}",
                    "mount_source_identities": build_matrix.SOURCE_IDENTITIES[
                        "reference"
                    ],
                }
                for index in range(3)
            ],
        ]
        self.starts = [
            {"argv": ["start", "-a", "-i", "ws-checker-a"], "status": 0},
            {"argv": ["start", "-a", "-i", "ws-checker-b"], "status": 0},
            {
                "argv": ["start", "--attach", "ws-terminal-builder-good"],
                "status": 0,
            },
            {
                "argv": ["start", "--attach", "ws-terminal-candidate-good"],
                "status": 1,
            },
            *[
                {
                    "argv": [
                        "start",
                        "--attach",
                        f"ws-terminal-reference-good-{index}",
                    ],
                    "status": 0,
                }
                for index in range(3)
            ],
        ]
        _write_json(self.raw / "interrupt.json", {"adapter_failure": True})
        _write_json(
            self.raw / "restart-cleanup.json",
            {
                "owned_containers_absent": True,
                "owned_images_absent": True,
                "unowned_control_preserved": True,
            },
        )
        for name in ("art-interrupt.json", "art-complete.json"):
            _write_json(
                self.raw / name,
                {"ledger_empty": True, "workspace_empty": True},
            )
        _write_json(
            self.raw / "complete-result.json",
            {
                "result": {
                    "findings": [],
                    "outcome": "completed",
                    "verdict": "passed",
                }
            },
        )
        self._flush()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _flush(self) -> None:
        _write_ndjson(self.raw / "launches.ndjson", self.launches)
        _write_ndjson(self.raw / "command-results.ndjson", self.starts)

    def test_exact_matrix_is_accepted(self) -> None:
        value = build_matrix.reduce_matrix(self.raw, HEAD)
        self.assertEqual(value["head_sha"], HEAD)

    def test_extra_partial_attempt_is_rejected(self) -> None:
        self.launches.append(
            {
                "kind": "candidate",
                "attempt": "extra",
                "container_id": "extra",
                "name": "ws-terminal-candidate-extra",
                "mount_source_identities": build_matrix.SOURCE_IDENTITIES["candidate"],
            }
        )
        self._flush()
        with self.assertRaisesRegex(ValueError, "launch"):
            build_matrix.reduce_matrix(self.raw, HEAD)

    def test_duplicate_start_is_rejected(self) -> None:
        self.starts.append(self.starts[3].copy())
        self._flush()
        with self.assertRaisesRegex(ValueError, "start observations differ"):
            build_matrix.reduce_matrix(self.raw, HEAD)


class DockerWrapperSourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.raw = self.root / "raw"
        self.work = self.root / "work"
        self.art = self.root / "art"
        self.cache = self.root / "cache"
        self.workspace = self.art / "workspaces" / GRANT_ID / "workspace"
        self.tests = self.workspace / "tests"
        self.tests.mkdir(parents=True)
        (self.workspace / "solution").mkdir()
        (self.workspace / "solution" / "program.py").write_text("pass\n")
        self.raw.mkdir()
        self.work.mkdir()
        self.cache.mkdir()
        self.inspect = self.root / "inspect.json"
        self.fake_docker = self.root / "fake-docker"
        self.fake_docker.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            "if [[ ${1:-} == exec && ${3:-} == docker "
            "&& ${4:-} == container && ${5:-} == inspect ]]; then\n"
            '  cat "${WS493_TEST_INSPECT:?}"\n'
            "fi\n",
            encoding="utf-8",
        )
        self.fake_docker.chmod(0o755)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _run(self, source: Path) -> subprocess.CompletedProcess[str]:
        item = {
            "Id": "candidate-id",
            "Name": "/ws-terminal-candidate-abc",
            "Config": {
                "Labels": {
                    "workstream.owner": "terminal-benchmark-checker-service-v1",
                    "workstream.resource-kind": "candidate",
                    "workstream.attempt": "abc",
                    "workstream.grant-id": GRANT_ID,
                },
                "User": "65532:65532",
            },
            "HostConfig": {
                "Runtime": "runsc",
                "NetworkMode": "none",
                "CapDrop": ["ALL"],
                "CapAdd": [],
                "SecurityOpt": ["no-new-privileges"],
                "ReadonlyRootfs": True,
                "PidsLimit": 32,
                "Memory": 536_870_912,
                "NanoCpus": 1_000_000_000,
                "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=16777216"},
            },
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": str(source),
                    "Destination": "/tests",
                    "RW": False,
                }
            ],
        }
        _write_json(self.inspect, [item])
        environment = {
            **os.environ,
            "WS493_REAL_DOCKER": str(self.fake_docker),
            "WS493_DIND_NAME": "ws-pilot00-test-dind",
            "WS493_RAW_DIR": str(self.raw),
            "WS493_WRAPPER_WORK_DIR": str(self.work),
            "WS493_SERVICE_PID_FILE": str(self.work / "service.pid"),
            "WS493_SERVICE_BINARY": str(self.work / "service"),
            "WS493_BARRIER_ENABLE": str(self.work / "barrier.enable"),
            "WS493_BARRIER_READY": str(self.work / "barrier.ready"),
            "WS493_BARRIER_RELEASE": str(self.work / "barrier.release"),
            "WS493_BARRIER_TOKEN": "token",
            "WS493_SANDBOX_USER": "65532:65532",
            "WS493_ART_ROOT": str(self.art),
            "WS493_CACHE_ROOT": str(self.cache),
            "WS493_TEST_INSPECT": str(self.inspect),
        }
        return subprocess.run(
            [
                str(Path(__file__).with_name("docker-wrapper.sh")),
                "create",
                "--name",
                "ws-terminal-candidate-abc",
            ],
            env=environment,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )

    def test_exact_art_source_is_recorded_without_raw_path(self) -> None:
        result = self._run(self.tests)
        self.assertEqual(result.returncode, 0, result.stderr)
        [launch] = [
            json.loads(line)
            for line in (self.raw / "launches.ndjson").read_text().splitlines()
        ]
        self.assertEqual(
            launch["mount_source_identities"], {"/tests": "art_workspace_tests"}
        )
        self.assertNotIn(str(self.root), json.dumps(launch))

    def test_parent_source_substitution_is_rejected(self) -> None:
        result = self._run(Path("/run"))
        self.assertEqual(result.returncode, 70)
        self.assertFalse((self.raw / "launches.ndjson").exists())


if __name__ == "__main__":
    unittest.main()
