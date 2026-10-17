"""Run the selected POST owner through real PostgreSQL, ART and Rust service custody."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import tempfile

from app.adapters.checkers import external_checker_execution_factory
from app.modules.checkers.api.external import ExternalCheckerRegistrySpec
from tests.checkers.execution.support import live_executor, reserve
from tests.checkers.external.test_selected_post_submit import _post_spec
from tests.post_submit_materialization_helpers import material_fixture

from experiments.pilot04_external_checker_runtime.run_probe import _image_identity


async def run(
    *, database_url: str, image_reference: str, service_binary: Path, root: Path
) -> dict[str, object]:
    """Execute one registered POST image against actual Submission and ART facts."""
    image = _image_identity(image_reference)
    values = _post_spec().model_dump(mode="json")
    values["image_digest"] = image["platform_manifest_digest"]
    values["resources"] |= {"deadline_ms": 8_000, "maximum_output_bytes": 8_192}
    spec = ExternalCheckerRegistrySpec.model_validate(values)
    async with material_fixture(
        root, database_url, post_submit_registry_spec=spec
    ) as fixture:
        socket_root = root / "service"
        socket_root.mkdir(mode=0o700)
        socket_path = socket_root / "checker.sock"
        config = {
            "socket_path": str(socket_path),
            "material_root": str(fixture.scratch),
            "docker_binary": "/usr/bin/docker",
            "runtime": "runc",
            "isolation_mode": "docker-dev",
            "operating_system": image["operating_system"],
            "architecture": image["architecture"],
            "sandbox_uid": os.getuid(),
            "sandbox_gid": os.getgid(),
            "cache": [image],
        }
        config_path = socket_root / "service.json"
        config_path.write_text(json.dumps(config, separators=(",", ":")))
        service = subprocess.Popen(
            [str(service_binary), str(config_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            for _ in range(500):
                if socket_path.exists():
                    break
                if service.poll() is not None:
                    raise RuntimeError("checker service exited before readiness")
                await asyncio.sleep(0.02)
            else:
                raise RuntimeError("checker service socket did not become ready")
            adapter = external_checker_execution_factory(
                socket_path=socket_path, timeout_seconds=90.0
            ).create("unix_socket")
            health = await adapter.health()
            reservation = await reserve(fixture)
            result = await live_executor(
                fixture, selected_execution=adapter
            ).evaluate_post_submission(fixture.request)
            if result.outcome != "completed" or result.execution is None:
                raise RuntimeError("selected POST execution did not complete")
            if len(result.execution.external_members) != 1:
                raise RuntimeError("selected POST member count differs")
            member = result.execution.external_members[0]
            if (
                member.result.verdict != "passed"
                or member.isolation.platform_manifest_digest
                != image["platform_manifest_digest"]
                or result.attempt_id != reservation.attempt_id
            ):
                raise RuntimeError("selected POST result or isolation differs")
            workspace_cleanup = list((fixture.scratch / "workspaces").iterdir()) == []
            if not workspace_cleanup:
                raise RuntimeError("selected POST workspace cleanup is incomplete")
            return {
                "image": image,
                "health": {
                    "runtime": health.runtime,
                    "isolation_mode": health.isolation_mode,
                },
                "attempt_id": str(result.attempt_id),
                "result_digest": result.result_digest,
                "member_result_digest": member.result.result_digest,
                "workspace_cleanup": workspace_cleanup,
                "store_open_count": len(fixture.store.opens),
            }
        finally:
            service.terminate()
            try:
                service.wait(timeout=5)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--image-reference", required=True)
    parser.add_argument("--service-binary", required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="ws-pilot04-selected-post-") as directory:
        result = asyncio.run(
            run(
                database_url=args.database_url,
                image_reference=args.image_reference,
                service_binary=args.service_binary,
                root=Path(directory),
            )
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
