"""Opt-in Docker-dev proof for the invocation-local model relay.

The probe uses an already-local base image and registry image, builds only a
small disposable checker layer, and never contacts a model provider. It starts
one fake private global proxy and drives the real Rust service through one
post-submit invocation. Every created container and image reference is recorded
and removed explicitly; the probe never scans or prunes Docker state.

Usage:
  TMPDIR=/dev/shm python3 model_relay_docker.py \
    --service /absolute/path/to/workstream-checker-service
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tarfile
import tempfile
import threading
import time


PROTOCOL = "external_checker_service.v1"
GRANT_PROTOCOL = "workstream.external_checker_material_grant.v1"
MODEL_PROTOCOL = "workstream.checker_model_proxy.v1"
MAX_FRAME = 1024 * 1024
MODEL_GRANT_ID = "model_0123456789abcdef0123456789abcdef"
MATERIAL_GRANT_ID = "extract_0123456789abcdef0123456789abcdef"
PROMPT = "docker relay proof"
MODEL_REPLY = {
    "protocol_version": MODEL_PROTOCOL,
    "outcome": "completed",
    "output": "docker-relay-ok",
    "receipt_digest": "sha256:" + "e" * 64,
    "failure_code": None,
}


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def run(docker: str, *arguments: str, timeout: int = 60) -> str:
    return subprocess.check_output(
        [docker, *arguments], text=True, stderr=subprocess.PIPE, timeout=timeout
    ).strip()


def inspect_container(docker: str, identity: str) -> dict | None:
    result = subprocess.run(
        [docker, "container", "inspect", identity],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        run(docker, "info", "--format", "{{.ID}}")
        if "No such" not in result.stderr:
            raise RuntimeError(result.stderr)
        return None
    return json.loads(result.stdout)[0]


def read_exact(connection: socket.socket, length: int) -> bytes:
    body = bytearray()
    while len(body) < length:
        part = connection.recv(length - len(body))
        if not part:
            raise OSError("short frame")
        body.extend(part)
    return bytes(body)


def read_frame(connection: socket.socket, maximum: int = MAX_FRAME) -> bytes:
    length = struct.unpack(">I", read_exact(connection, 4))[0]
    if not 0 < length <= maximum:
        raise RuntimeError("invalid frame length")
    return read_exact(connection, length)


def write_frame(connection: socket.socket, body: bytes) -> None:
    if not 0 < len(body) <= MAX_FRAME:
        raise RuntimeError("invalid frame body")
    connection.sendall(struct.pack(">I", len(body)) + body)


def extract_registry_binary(docker: str, image: str, root: Path) -> Path:
    archive = root / "registry-image.tar"
    subprocess.check_call(
        [docker, "image", "save", "--output", str(archive), image], timeout=60
    )
    content: bytes | None = None
    with tarfile.open(archive) as outer:
        manifest_member = outer.extractfile("manifest.json")
        if manifest_member is None:
            raise RuntimeError("local registry image manifest is missing")
        manifests = json.load(manifest_member)
        selected = next(
            (
                item
                for item in manifests
                if image in item.get("RepoTags", [])
                or image.split(":", 1)[0] in item.get("RepoTags", [])
            ),
            manifests[0] if len(manifests) == 1 else None,
        )
        if selected is None:
            raise RuntimeError("local registry image is ambiguous")
        for layer_name in selected["Layers"]:
            layer_member = outer.extractfile(layer_name)
            if layer_member is None:
                raise RuntimeError("local registry image layer is missing")
            with tarfile.open(fileobj=io.BytesIO(layer_member.read())) as layer:
                for member in layer:
                    normalized = member.name.removeprefix("./").removeprefix("/")
                    if normalized == "bin/.wh.registry":
                        content = None
                    elif normalized == "bin/registry" and member.isfile():
                        source = layer.extractfile(member)
                        if source is None:
                            raise RuntimeError("local registry binary is unreadable")
                        content = source.read()
    archive.unlink()
    if content is None:
        raise RuntimeError("local registry binary is missing")
    registry = root / "registry"
    registry.write_bytes(content)
    registry.chmod(0o500)
    return registry


def start_registry(binary: Path, root: Path) -> tuple[subprocess.Popen, int]:
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    storage = root / "registry-data"
    storage.mkdir(mode=0o700)
    config = root / "registry.yml"
    config.write_text(
        "version: 0.1\n"
        "log:\n  level: error\n"
        f"storage:\n  filesystem:\n    rootdirectory: {storage}\n"
        f"http:\n  addr: 127.0.0.1:{port}\n",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [str(binary), "serve", str(config)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("disposable registry failed to start")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return process, port
        except OSError:
            time.sleep(0.05)
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    raise RuntimeError("disposable registry readiness timed out")


def wait_for_service(process: subprocess.Popen, address: Path) -> None:
    deadline = time.monotonic() + 60
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(process.stderr.read())
        try:
            with socket.socket(socket.AF_UNIX) as connection:
                connection.settimeout(15)
                connection.connect(str(address))
                write_frame(
                    connection,
                    canonical({"protocol_version": PROTOCOL, "operation": "health"}),
                )
                response = json.loads(read_frame(connection, 96 * 1024))
                if response.get("status") == "ready":
                    return
        except (OSError, ValueError, RuntimeError) as error:
            last_error = error
            time.sleep(0.1)
    raise RuntimeError(f"service readiness timed out: {last_error}")


def schema(schema_id: str) -> dict:
    document = {"type": "object"}
    return {
        "schema_id": schema_id,
        "schema_version": "v1",
        "document": document,
        "schema_sha256": digest(document),
    }


def request_and_manifest(image_digest: str) -> tuple[dict, dict]:
    def identifier(byte: str) -> str:
        return f"{byte * 8}-0000-4000-8000-000000000000"

    def sha(byte: str) -> str:
        return "sha256:" + byte * 64

    semantic = digest(
        {"schema_version": "workstream.submission_bundle_manifest.v1", "entries": []}
    )
    registry = {
        "capability_id": "probe.model_relay",
        "capability_version": "v1",
        "phase": "post_submit",
        "image_digest": image_digest,
        "configuration_schema": schema("probe.model_relay.configuration"),
        "input_schema": schema("external_checker_post_submit_input"),
        "output_schema": schema("external_checker_result"),
        "resources": {
            "cpu_millis": 500,
            "memory_bytes": 64 * 1024 * 1024,
            "deadline_ms": 30_000,
            "maximum_output_bytes": 32_768,
        },
        "registry_entry_id": identifier("f"),
        "entry_digest": sha("0"),
        "registration_operation_id": identifier("a"),
        "registered_by_actor_profile_id": identifier("b"),
        "authorization_decision_event_id": identifier("c"),
        "created_at": "2026-10-23T00:00:00Z",
    }
    entry = dict(registry)
    for field in (
        "registry_entry_id",
        "entry_digest",
        "registration_operation_id",
        "registered_by_actor_profile_id",
        "authorization_decision_event_id",
        "created_at",
    ):
        entry.pop(field)
    registry["entry_digest"] = digest(entry)
    identity = {
        "phase": "post_submit",
        "project_id": identifier("1"),
        "task_id": identifier("2"),
        "assignment_id": identifier("3"),
        "submission_id": identifier("4"),
        "submission_version": 2,
        "evaluation_request_id": identifier("5"),
        "evaluation_request_digest": sha("5"),
        "evaluation_generation": 3,
        "attempt_id": identifier("6"),
        "result_id": identifier("7"),
        "lease_id": identifier("8"),
        "lease_generation": 4,
        "lease_expires_at": "2026-10-23T01:00:00+00:00",
    }
    material = {
        "phase": "post_submit",
        "role": "submission_archive",
        "submission_id": identity["submission_id"],
        "submission_version": identity["submission_version"],
        "binding_id": identifier("9"),
        "content_id": identifier("a"),
        "replica_id": identifier("b"),
        "content_sha256": sha("c"),
        "byte_count": 0,
        "media_type": "application/zip",
        "evidence_id": identifier("c"),
        "verification_receipt_id": identifier("d"),
        "verification_job_id": identifier("e"),
        "verification_generation": 5,
        "namespace_fingerprint": sha("d"),
        "semantic_manifest_sha256": semantic,
    }
    configuration: dict[str, object] = {}
    checker_input: dict[str, object] = {}
    request = {
        "schema_version": "external_checker_request.v1",
        "registry": registry,
        "identity": identity,
        "configuration": configuration,
        "configuration_sha256": digest(configuration),
        "input": checker_input,
        "input_sha256": digest(checker_input),
        "materials": [material],
    }
    request["request_digest"] = digest(request)
    manifest = {
        "protocol_version": GRANT_PROTOCOL,
        "grant_id": MATERIAL_GRANT_ID,
        "request_digest": request["request_digest"],
        "phase": "post_submit",
        "submission_id": identity["submission_id"],
        "submission_version": identity["submission_version"],
        "evaluation_request_id": identity["evaluation_request_id"],
        "evaluation_request_digest": identity["evaluation_request_digest"],
        "evaluation_generation": identity["evaluation_generation"],
        "attempt_id": identity["attempt_id"],
        "result_id": identity["result_id"],
        "lease_id": identity["lease_id"],
        "lease_generation": identity["lease_generation"],
        "lease_expires_at": identity["lease_expires_at"],
        "binding_id": material["binding_id"],
        "content_id": material["content_id"],
        "replica_id": material["replica_id"],
        "content_sha256": material["content_sha256"],
        "byte_count": material["byte_count"],
        "evidence_id": material["evidence_id"],
        "verification_receipt_id": material["verification_receipt_id"],
        "verification_job_id": material["verification_job_id"],
        "verification_generation": material["verification_generation"],
        "namespace_fingerprint": material["namespace_fingerprint"],
        "semantic_manifest_sha256": semantic,
        "directories": [],
        "files": [],
    }
    manifest["binding_digest"] = digest(manifest)
    return request, manifest


def write_checker_sources(root: Path) -> tuple[Path, Path]:
    client_source = root / "model-client.c"
    client = root / "model-client"
    client_source.write_text(
        r"""#include <arpa/inet.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

static int transfer(int fd, void *buffer, size_t length, int writing) {
  size_t offset = 0;
  while (offset < length) {
    ssize_t count = writing ? write(fd, (char *)buffer + offset, length - offset)
                            : read(fd, (char *)buffer + offset, length - offset);
    if (count < 0 && errno == EINTR) continue;
    if (count <= 0) return -1;
    offset += (size_t)count;
  }
  return 0;
}

int main(void) {
  static const char body[] = "{\"prompt\":\"docker relay proof\"}";
  struct sockaddr_un address = {0};
  int descriptor = socket(AF_UNIX, SOCK_STREAM, 0);
  if (descriptor < 0) return 20;
  address.sun_family = AF_UNIX;
  if (strlen("/work/model.sock") >= sizeof(address.sun_path)) return 21;
  strcpy(address.sun_path, "/work/model.sock");
  if (connect(descriptor, (struct sockaddr *)&address, sizeof(address)) != 0) return 22;
  uint32_t length = htonl((uint32_t)(sizeof(body) - 1));
  if (transfer(descriptor, &length, sizeof(length), 1) ||
      transfer(descriptor, (void *)body, sizeof(body) - 1, 1)) return 23;
  if (transfer(descriptor, &length, sizeof(length), 0)) return 24;
  length = ntohl(length);
  if (length == 0 || length > 1024 * 1024) return 25;
  char *reply = malloc(length);
  if (!reply || transfer(descriptor, reply, length, 0)) return 26;
  if (write(STDOUT_FILENO, reply, length) != (ssize_t)length) return 27;
  free(reply);
  close(descriptor);
  return 0;
}
""",
        encoding="utf-8",
    )
    subprocess.check_call(
        ["cc", "-static", "-Os", "-s", str(client_source), "-o", str(client)],
        timeout=60,
    )
    client.chmod(0o555)
    checker = root / "checker.sh"
    expected_reply = canonical(MODEL_REPLY).decode()
    checker.write_text(
        f"""#!/bin/sh
set -eu
request="$(cat)"
case "$request" in
  *'"model_grant"'*|*'"grant_id"'*|*'PROVIDER_SECRET_PROOF'*|*'model-proxy.sock'*) exit 40 ;;
esac
reply="$(/model-client)"
[ "$reply" = '{expected_reply}' ] || exit 41
request_digest="$(printf %s "$request" | sed -n 's/.*"request_digest":"\\([^"]*\\)".*/\\1/p')"
registry_digest="$(printf %s "$request" | sed -n 's/.*"entry_digest":"\\([^"]*\\)".*/\\1/p')"
registry_id="$(printf %s "$request" | sed -n 's/.*"registry_entry_id":"\\([^"]*\\)".*/\\1/p')"
case "$request_digest:$registry_digest:$registry_id" in
  sha256:????????????????????????????????????????????????????????????????:sha256:????????????????????????????????????????????????????????????????:?*) ;;
  *) exit 42 ;;
esac
body="$(printf '{{\"findings\":[],\"infrastructure_failure_code\":null,\"outcome\":\"completed\",\"phase\":\"post_submit\",\"registry_entry_digest\":\"%s\",\"registry_entry_id\":\"%s\",\"request_digest\":\"%s\",\"schema_version\":\"external_checker_result.v1\",\"verdict\":\"passed\"}}' "$registry_digest" "$registry_id" "$request_digest")"
result_digest="$(printf %s "$body" | sha256sum | cut -d' ' -f1)"
printf '{{\"findings\":[],\"infrastructure_failure_code\":null,\"outcome\":\"completed\",\"phase\":\"post_submit\",\"registry_entry_digest\":\"%s\",\"registry_entry_id\":\"%s\",\"request_digest\":\"%s\",\"result_digest\":\"sha256:%s\",\"schema_version\":\"external_checker_result.v1\",\"verdict\":\"passed\"}}' "$registry_digest" "$registry_id" "$request_digest" "$result_digest"
""",
        encoding="utf-8",
    )
    checker.chmod(0o555)
    return client, checker


def fake_proxy(
    address: Path, expected_digest: str, result: dict, ready: threading.Event
) -> None:
    try:
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(str(address))
            address.chmod(0o600)
            listener.listen(1)
            ready.set()
            listener.settimeout(45)
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(15)
                request = json.loads(read_frame(connection))
                expected = {
                    "protocol_version": MODEL_PROTOCOL,
                    "grant_id": MODEL_GRANT_ID,
                    "request_digest": expected_digest,
                    "prompt": PROMPT,
                }
                if request != expected:
                    raise RuntimeError("proxy received a different closed request")
                result["request"] = request
                write_frame(connection, canonical(MODEL_REPLY))
    except BaseException as error:
        result["error"] = error
        ready.set()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", required=True, type=Path)
    parser.add_argument("--base-image", default="alpine:3.20")
    parser.add_argument("--registry-image", default="registry:2")
    args = parser.parse_args()
    service = args.service.resolve(strict=True)
    docker = str(Path(shutil.which("docker") or "/usr/bin/docker").resolve(strict=True))
    uid, gid = os.geteuid(), os.getegid()
    if uid == 0 or gid == 0:
        raise RuntimeError(
            "probe requires the same non-root UID/GID used by the service"
        )

    # These inspect calls must succeed locally. The probe never pulls either image.
    run(docker, "image", "inspect", args.base_image)
    run(docker, "image", "inspect", args.registry_image)
    nonce = os.urandom(8).hex()
    build_name = f"ws-model-relay-build-{nonce}"
    local_tag = f"ws-model-relay-proof:{nonce}"
    registry_tag: str | None = None
    created_image_id: str | None = None
    containers: list[str] = []
    container_names = (build_name,)
    checker_id: str | None = None
    inspection_path: Path | None = None
    service_process: subprocess.Popen | None = None
    registry_process: subprocess.Popen | None = None

    temporary_parent = os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(
        prefix="ws-model-relay-", dir=temporary_parent
    ) as temporary:
        root = Path(temporary).resolve()
        try:
            client, checker = write_checker_sources(root)
            build_id = run(docker, "create", "--name", build_name, args.base_image)
            containers.append(build_id)
            run(docker, "cp", str(client), f"{build_id}:/model-client")
            run(docker, "cp", str(checker), f"{build_id}:/checker.sh")
            created_image_id = run(
                docker,
                "commit",
                "--change",
                'ENTRYPOINT ["/checker.sh"]',
                "--change",
                "CMD []",
                build_id,
                local_tag,
                timeout=120,
            )
            run(docker, "rm", build_id)
            containers.remove(build_id)

            registry_binary = extract_registry_binary(docker, args.registry_image, root)
            registry_process, port = start_registry(registry_binary, root)
            repository = f"127.0.0.1:{port}/ws-model-relay-proof"
            registry_tag = f"{repository}:{nonce}"
            run(docker, "tag", local_tag, registry_tag)
            run(docker, "push", registry_tag, timeout=120)
            image = json.loads(run(docker, "image", "inspect", registry_tag))[0]
            reference = next(
                item
                for item in image["RepoDigests"]
                if item.startswith(repository + "@sha256:")
            )
            platform_digest = reference.split("@", 1)[1]

            request, manifest = request_and_manifest(platform_digest)
            socket_root = root / "service"
            material_root = root / "material"
            proxy_root = root / "proxy"
            relay_root = root / "relay"
            for directory in (socket_root, material_root, proxy_root, relay_root):
                directory.mkdir(mode=0o700)
            workspaces = material_root / "workspaces"
            grant_root = workspaces / MATERIAL_GRANT_ID
            workspace = grant_root / "workspace"
            workspaces.mkdir(mode=0o700)
            grant_root.mkdir(mode=0o700)
            workspace.mkdir(mode=0o500)
            manifest_path = grant_root / ".external-checker-grant.json"
            manifest_path.write_bytes(canonical(manifest))
            manifest_path.chmod(0o400)

            proxy_address = proxy_root / "model-proxy.sock"
            proxy_result: dict[str, object] = {}
            proxy_ready = threading.Event()
            proxy_thread = threading.Thread(
                target=fake_proxy,
                args=(
                    proxy_address,
                    request["request_digest"],
                    proxy_result,
                    proxy_ready,
                ),
                daemon=True,
            )
            proxy_thread.start()
            if not proxy_ready.wait(5) or "error" in proxy_result:
                raise RuntimeError(
                    f"fake proxy startup failed: {proxy_result.get('error')}"
                )

            inspection_path = root / "container-inspection.json"
            wrapper = root / "docker-wrapper.py"
            wrapper.write_text(
                "#!/usr/bin/python3\n"
                "import json, pathlib, subprocess, sys\n"
                f"docker={docker!r}\n"
                f"proof=pathlib.Path({str(inspection_path)!r})\n"
                "result=subprocess.run([docker,*sys.argv[1:]], stdin=sys.stdin.buffer, "
                "stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n"
                "if result.returncode == 0 and len(sys.argv)>1 and sys.argv[1]=='create':\n"
                " identity=result.stdout.decode().strip()\n"
                " inspected=subprocess.check_output([docker,'container','inspect',identity])\n"
                " proof.write_bytes(inspected)\n"
                "sys.stdout.buffer.write(result.stdout)\n"
                "sys.stderr.buffer.write(result.stderr)\n"
                "raise SystemExit(result.returncode)\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o700)
            config = {
                "socket_path": str(socket_root / "checker.sock"),
                "model_proxy_socket": str(proxy_address),
                "model_relay_root": str(relay_root),
                "material_root": str(material_root),
                "docker_binary": str(wrapper),
                "runtime": "runc",
                "isolation_mode": "docker-dev",
                "operating_system": image["Os"],
                "architecture": image["Architecture"],
                "sandbox_uid": uid,
                "sandbox_gid": gid,
                "cache": [
                    {
                        "repository": repository,
                        "platform_manifest_digest": platform_digest,
                        "platform_manifest_media_type": "application/vnd.docker.distribution.manifest.v2+json",
                        "platform_manifest_byte_count": 1,
                        "operating_system": image["Os"],
                        "architecture": image["Architecture"],
                        "config_image_id": image["Id"],
                    }
                ],
            }
            config_path = root / "service.json"
            config_path.write_bytes(canonical(config))
            environment = dict(os.environ)
            provider_secret = "provider-secret-proof-" + nonce
            environment["PROVIDER_SECRET_PROOF"] = provider_secret
            service_process = subprocess.Popen(
                [str(service), str(config_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                env=environment,
            )
            wait_for_service(service_process, socket_root / "checker.sock")
            envelope = {
                "protocol_version": PROTOCOL,
                "operation": "execute",
                "request": request,
                "grant": {
                    "grant_id": MATERIAL_GRANT_ID,
                    "binding_digest": manifest["binding_digest"],
                },
                "model_grant": {
                    "grant_id": MODEL_GRANT_ID,
                    "binding_digest": request["request_digest"],
                },
            }
            with socket.socket(socket.AF_UNIX) as connection:
                connection.settimeout(45)
                connection.connect(str(socket_root / "checker.sock"))
                write_frame(connection, canonical(envelope))
                response = json.loads(read_frame(connection, 96 * 1024))

            proxy_thread.join(timeout=5)
            if proxy_thread.is_alive() or "error" in proxy_result:
                raise RuntimeError(
                    f"fake proxy exchange failed: {proxy_result.get('error')}"
                )
            if (
                response["result"]["outcome"] != "completed"
                or response["result"]["verdict"] != "passed"
            ):
                raise RuntimeError(f"checker execution failed: {response['result']}")
            if response["isolation"]["isolation_mode"] != "docker-dev":
                raise RuntimeError("missing Docker-dev isolation receipt")

            inspected = json.loads(inspection_path.read_text())[0]
            checker_id = inspected["Id"]
            mounts = {item["Destination"]: item for item in inspected["Mounts"]}
            material_mount = mounts["/work/input"]
            model_mount = mounts["/work/model.sock"]
            if inspected["HostConfig"]["NetworkMode"] != "none":
                raise RuntimeError("checker network was not disabled")
            if inspected["HostConfig"]["ReadonlyRootfs"] is not True:
                raise RuntimeError("checker root filesystem was writable")
            if material_mount["RW"] or material_mount["Source"] != str(workspace):
                raise RuntimeError("checker material mount was not exact and read-only")
            model_source = Path(model_mount["Source"])
            if model_mount["RW"] or model_source.name != "model.sock":
                raise RuntimeError("checker model socket mount was not read-only")
            if (
                model_source.parent.parent != relay_root
                or not model_source.parent.name.startswith(".model-")
            ):
                raise RuntimeError(
                    "checker received a non-invocation-local model socket"
                )
            serialized_inspection = canonical(inspected).decode()
            for forbidden in (str(proxy_address), MODEL_GRANT_ID, provider_secret):
                if forbidden in serialized_inspection:
                    raise RuntimeError(
                        "private proxy material reached the checker container"
                    )
            if inspect_container(docker, checker_id) is not None:
                raise RuntimeError("checker container was not cleaned")
            if any(relay_root.iterdir()):
                raise RuntimeError("invocation relay path was not cleaned")
            print(
                json.dumps(
                    {
                        "status": "PASS",
                        "runtime": "docker-dev/runc",
                        "network_mode": "none",
                        "rootfs_read_only": True,
                        "material_read_only": True,
                        "invocation_socket_read_only": True,
                        "proxy_request_closed": proxy_result["request"]
                        == {
                            "protocol_version": MODEL_PROTOCOL,
                            "grant_id": MODEL_GRANT_ID,
                            "request_digest": request["request_digest"],
                            "prompt": PROMPT,
                        },
                        "reply": MODEL_REPLY["output"],
                        "checker_container_removed": True,
                        "relay_directory_empty": True,
                        "gvisor_qualified": False,
                    },
                    sort_keys=True,
                )
            )
        finally:
            if service_process is not None:
                if service_process.poll() is None:
                    service_process.terminate()
                    try:
                        service_process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        service_process.kill()
                        service_process.wait(timeout=10)
                service_process.stderr.close()
            if registry_process is not None and registry_process.poll() is None:
                registry_process.terminate()
                try:
                    registry_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    registry_process.kill()
                    registry_process.wait(timeout=10)
            if (
                checker_id is None
                and inspection_path is not None
                and inspection_path.exists()
            ):
                try:
                    checker_id = json.loads(inspection_path.read_text())[0]["Id"]
                except (KeyError, IndexError, TypeError, ValueError):
                    checker_id = None
            for identity in containers:
                if inspect_container(docker, identity) is not None:
                    run(docker, "rm", "--force", identity)
            for name in container_names:
                if inspect_container(docker, name) is not None:
                    run(docker, "rm", "--force", name)
            if (
                checker_id is not None
                and inspect_container(docker, checker_id) is not None
            ):
                run(docker, "rm", "--force", checker_id)
            for reference in (registry_tag, local_tag):
                if reference is not None:
                    try:
                        subprocess.run(
                            [docker, "image", "rm", "--force", reference],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=30,
                        )
                    except subprocess.TimeoutExpired:
                        pass
            if created_image_id is not None:
                try:
                    subprocess.run(
                        [docker, "image", "rm", "--force", created_image_id],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=30,
                    )
                except subprocess.TimeoutExpired:
                    pass
            remaining = [
                identity
                for identity in (*containers, *container_names)
                if inspect_container(docker, identity)
            ]
            if (
                checker_id is not None
                and inspect_container(docker, checker_id) is not None
            ):
                remaining.append(checker_id)
            retained_images = []
            for reference in (registry_tag, local_tag, created_image_id):
                if reference is None:
                    continue
                result = subprocess.run(
                    [docker, "image", "inspect", reference],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                )
                if result.returncode == 0:
                    retained_images.append(reference)
            if remaining or retained_images:
                raise RuntimeError(
                    "probe cleanup incomplete: "
                    f"containers={remaining}; images={retained_images}"
                )


if __name__ == "__main__":
    main()
