"""Opt-in real-Docker startup isolation proof; never pulls or scans for cleanup.

Usage: python3 container_ownership.py --service ABSOLUTE_BINARY --image redis:7
The already-cached image must supply /bin/sh and sleep. No checker is executed.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True, type=Path)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    service = args.service.resolve(strict=True)
    docker = str(Path(shutil.which("docker") or "/usr/bin/docker").resolve(strict=True))

    def call(*arguments):
        return subprocess.check_output(
            [docker, *arguments], text=True, timeout=30, stderr=subprocess.PIPE
        ).strip()

    image = json.loads(call("image", "inspect", args.image))[0]
    containers = []
    processes = []
    pending_creation = None

    def inspect(identity):
        result = subprocess.run(
            [docker, "container", "inspect", identity],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode:
            # An absent result must not conceal an unavailable daemon.
            call("info", "--format", "{{.ID}}")
            if "No such" not in result.stderr:
                raise RuntimeError(result.stderr)
            return None
        return json.loads(result.stdout)[0]

    def receive(connection, length):
        data = b""
        while len(data) < length:
            part = connection.recv(length - len(data))
            if not part:
                raise OSError("short health frame")
            data += part
        return data

    with tempfile.TemporaryDirectory(prefix="ws-owner-") as temporary:
        root = Path(temporary)

        def start(name):
            directory = root / name
            directory.mkdir(mode=0o700, exist_ok=True)
            material = directory / "material"
            material.mkdir(mode=0o700, exist_ok=True)
            address = directory / "service.sock"
            config = {
                "socket_path": str(address),
                "material_root": str(material),
                "docker_binary": docker,
                "runtime": "runc",
                "isolation_mode": "docker-dev",
                "operating_system": image["Os"],
                "architecture": image["Architecture"],
                "sandbox_uid": os.geteuid() or 65534,
                "sandbox_gid": os.getegid() or 65534,
                # Startup checks configuration/runtime, not execution cache content.
                "cache": [
                    {
                        "repository": "ownership-proof/checker",
                        "platform_manifest_digest": "sha256:" + "a" * 64,
                        "platform_manifest_media_type": "application/vnd.oci.image.manifest.v1+json",
                        "platform_manifest_byte_count": 1,
                        "operating_system": image["Os"],
                        "architecture": image["Architecture"],
                        "config_image_id": image["Id"],
                    }
                ],
            }
            path = directory / "config.json"
            path.write_text(json.dumps(config))
            process = subprocess.Popen(
                [str(service), str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            processes.append(process)
            deadline = time.monotonic() + 60
            last_error = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(process.stderr.read())
                try:
                    with socket.socket(socket.AF_UNIX) as connection:
                        # Health includes a Docker control call (bounded at 10s).
                        connection.settimeout(15)
                        connection.connect(str(address))
                        request = json.dumps(
                            {
                                "protocol_version": "external_checker_service.v1",
                                "operation": "health",
                            }
                        ).encode()
                        connection.sendall(struct.pack(">I", len(request)) + request)
                        length = struct.unpack(">I", receive(connection, 4))[0]
                        if not 0 < length <= 81920:
                            raise RuntimeError("invalid health frame size")
                        response = json.loads(receive(connection, length))
                        if response.get("status") != "ready":
                            raise RuntimeError(response)
                        owner = (directory / ".workstream-checker-owner").read_text()
                        if not re.fullmatch("[0-9a-f]{64}", owner):
                            raise RuntimeError("invalid owner custody")
                        return process, owner
                except (OSError, json.JSONDecodeError) as error:
                    last_error = error
                    time.sleep(0.1)
            raise RuntimeError(f"service readiness timed out: {last_error}")

        def stop(process):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)

        def create(owner, attempt):
            nonlocal pending_creation
            name = f"ws-checker-{owner}-{attempt}" if owner else f"ws-checker-{attempt}"
            labels = [
                "--label",
                "workstream.external-checker=true",
                "--label",
                f"workstream.external-checker-attempt={attempt}",
            ]
            if owner:
                labels += ["--label", f"workstream.external-checker-owner={owner}"]
            pending_creation = name
            identity = call(
                "create",
                "--name",
                name,
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--pids-limit=16",
                "--memory=32m",
                "--cpus=0.1",
                *labels,
                "--entrypoint=/bin/sh",
                image["Id"],
                "-c",
                "sleep 300",
            )
            if not re.fullmatch("[0-9a-f]{64}", identity):
                raise RuntimeError("Docker did not return a full container ID")
            containers.append(identity)
            pending_creation = None
            return identity

        try:
            a, owner_a = start("a")
            b, owner_b = start("b")
            assert owner_a != owner_b
            stop(b)
            active_a = create(owner_a, "a1")
            stale_b = create(owner_b, "b1")
            unowned = create(None, os.urandom(12).hex())
            call("start", active_a)
            assert inspect(active_a)["State"]["Running"]
            b, recovered_b = start("b")
            assert recovered_b == owner_b
            assert inspect(stale_b) is None
            assert inspect(active_a)["State"]["Running"], "B removed A's active work"
            assert inspect(unowned) is not None, "B adopted an unowned container"
            stop(a)
            a, recovered_a = start("a")
            assert recovered_a == owner_a
            assert inspect(active_a) is None
            assert inspect(unowned) is not None
            print(
                "PASS: distinct custody, foreign active survival, own restart recovery, unowned survival"
            )
        finally:
            for process in processes:
                stop(process)
                process.stderr.close()
            for identity in containers:
                if inspect(identity) is not None:
                    call("rm", "-f", identity)
            assert all(inspect(identity) is None for identity in containers)
            if pending_creation is not None:
                raise RuntimeError(
                    "Container creation outcome is uncertain; inspect exact fixture name "
                    f"{pending_creation}. Recorded IDs were cleaned; no global cleanup was attempted."
                )
            print("Cleanup confirmed for all recorded fixture container IDs")


if __name__ == "__main__":
    main()
