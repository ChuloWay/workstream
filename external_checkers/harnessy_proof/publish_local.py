#!/usr/bin/env python3
"""Publish the proof checker to a loopback registry and write its local configs.

Run on the Docker host from the repository root. The script builds this
directory's image, pushes it to the loopback registry, resolves the exact
platform manifest, pulls that digest so the daemon records it, and writes:

- ``checker-service.json``: the Rust checker-service configuration;
- ``registry-pre.json`` and ``registry-post.json``: ``ExternalCheckerRegistrySpec``
  bodies for ``POST /api/v1/operations/external-checker-registry``.

It uses only the Python standard library and the Docker CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
MANIFEST_TYPES = (
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)
CAPABILITY_ID = "harnessy.work_proof"
INPUT_SCHEMA_IDS = {
    "pre_submit": "external_checker_pre_submit_input",
    "post_submit": "external_checker_post_submit_input",
}
# The socket stays on a named volume: Docker Desktop host-shared paths refuse
# chmod on Unix sockets, and AF_UNIX paths must stay within 107 bytes.
SOCKET_PATH = "/run/ws-checker/checker.sock"


def material_root(compose_project: str) -> str:
    """The Docker-VM path of the named material volume, identical in every container."""
    return f"/var/lib/docker/volumes/{compose_project}-checker-material/_data"


def _hash(value: object) -> str:
    """Canonical JSON digest for the string/integer/object schema documents used here."""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# PRE has no GitHub facts, so only shape mode is valid there. POST accepts shape
# mode ({}) or GitHub comparison mode naming both repository and base branch.
CONFIGURATION_SCHEMAS: dict[str, dict[str, object]] = {
    "pre_submit": {"type": "object", "additionalProperties": False, "maxProperties": 0},
    "post_submit": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "github_repository": {
                "type": "string",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$",
            },
            "base_branch": {"type": "string", "minLength": 1, "maxLength": 255},
        },
        "dependentRequired": {
            "github_repository": ["base_branch"],
            "base_branch": ["github_repository"],
        },
    },
}
# WorkStream adds GitHub facts to the normalized POST input only for bindings in
# GitHub comparison mode. The checker validates the full facts shape itself.
INPUT_SCHEMAS: dict[str, dict[str, object]] = {
    "pre_submit": {"type": "object"},
    "post_submit": {
        "type": "object",
        "properties": {
            "github_facts": {
                "type": "object",
                "required": ["schema_version"],
                "properties": {"schema_version": {"const": "workstream.github_facts.v1"}},
            }
        },
    },
}


def _schema(schema_id: str, document: dict[str, object] | None = None) -> dict[str, object]:
    document = {"type": "object"} if document is None else document
    return {
        "schema_id": schema_id,
        "schema_version": "v1",
        "document": document,
        "schema_sha256": _hash(document),
    }


def registry_spec(phase: str, image_digest: str, capability_version: str) -> dict[str, object]:
    """One immutable registry body; PRE and POST share the image and limits."""
    return {
        "capability_id": CAPABILITY_ID,
        "capability_version": capability_version,
        "phase": phase,
        "image_digest": image_digest,
        "configuration_schema": _schema(
            "harnessy.work_proof.configuration", CONFIGURATION_SCHEMAS[phase]
        ),
        "input_schema": _schema(INPUT_SCHEMA_IDS[phase], INPUT_SCHEMAS[phase]),
        "output_schema": _schema("external_checker_result"),
        "resources": {
            "cpu_millis": 500,
            "memory_bytes": 134_217_728,
            "deadline_ms": 30_000,
            "maximum_output_bytes": 32_768,
        },
    }


def service_config(
    image: dict[str, object], *, compose_project: str, sandbox_uid: int, sandbox_gid: int
) -> dict[str, object]:
    return {
        "socket_path": SOCKET_PATH,
        "material_root": material_root(compose_project),
        "docker_binary": "/usr/local/bin/docker",
        "runtime": "runc",
        "isolation_mode": "docker-dev",
        "operating_system": image["operating_system"],
        "architecture": image["architecture"],
        "sandbox_uid": sandbox_uid,
        "sandbox_gid": sandbox_gid,
        "cache": [image],
    }


def _docker(*arguments: str) -> str:
    return subprocess.run(["docker", *arguments], check=True, capture_output=True, text=True).stdout


def publish(registry: str, repository: str) -> dict[str, object]:
    """Build, push and resolve one single-platform manifest by digest."""
    if re.fullmatch(r"(localhost|127\.0\.0\.1):[0-9]{1,5}", registry) is None:
        raise SystemExit("the proof checker publishes only to a loopback registry")
    tagged = f"{registry}/{repository}:local"
    # Docker progress goes to stderr so stdout carries only the final JSON summary.
    subprocess.run(
        ["docker", "build", "--provenance=false", "--sbom=false", "--tag", tagged, str(HERE)],
        check=True,
        stdout=sys.stderr,
    )
    subprocess.run(["docker", "push", tagged], check=True, stdout=sys.stderr)
    request = Request(
        f"http://{registry}/v2/{repository}/manifests/local",
        method="HEAD",
        headers={"Accept": ",".join(MANIFEST_TYPES)},
    )
    with urlopen(request, timeout=10) as response:
        media_type = response.headers["Content-Type"]
        byte_count = int(response.headers["Content-Length"])
        digest = response.headers["Docker-Content-Digest"]
    if media_type not in MANIFEST_TYPES:
        raise SystemExit(f"registry returned {media_type}, not a platform manifest")
    reference = f"{registry}/{repository}@{digest}"
    subprocess.run(["docker", "pull", "--quiet", reference], check=True, stdout=subprocess.DEVNULL)
    inspected = json.loads(_docker("image", "inspect", "--format", "{{json .}}", reference))
    if reference not in inspected.get("RepoDigests", []):
        raise SystemExit("the daemon did not record the platform-manifest digest")
    return {
        "repository": f"{registry}/{repository}",
        "platform_manifest_digest": digest,
        "platform_manifest_media_type": media_type,
        "platform_manifest_byte_count": byte_count,
        "operating_system": inspected["Os"],
        "architecture": inspected["Architecture"],
        "config_image_id": inspected["Id"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--registry", required=True, help="loopback host:port")
    parser.add_argument("--repository", default="harnessy-proof")
    parser.add_argument("--compose-project", required=True)
    parser.add_argument("--sandbox-uid", type=int, required=True)
    parser.add_argument("--sandbox-gid", type=int, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    # The registry holds one immutable entry per phase, capability and version,
    # so a rebuilt image (new digest) needs a new version. v2 adds GitHub
    # comparison mode and real configuration/input schemas.
    parser.add_argument("--capability-version", default="v2")
    args = parser.parse_args(argv)
    image = publish(args.registry, args.repository)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "checker-service.json": service_config(
            image,
            compose_project=args.compose_project,
            sandbox_uid=args.sandbox_uid,
            sandbox_gid=args.sandbox_gid,
        ),
        "registry-pre.json": registry_spec(
            "pre_submit", image["platform_manifest_digest"], args.capability_version
        ),
        "registry-post.json": registry_spec(
            "post_submit", image["platform_manifest_digest"], args.capability_version
        ),
    }
    for name, value in outputs.items():
        (args.out_dir / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "image": f"{image['repository']}@{image['platform_manifest_digest']}",
                "architecture": image["architecture"],
                "written": sorted(outputs),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
