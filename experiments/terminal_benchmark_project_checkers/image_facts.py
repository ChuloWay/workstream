#!/usr/bin/env python3
"""Resolve only exact linux/amd64 manifest facts from pinned image bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
MEDIA_TYPES = {
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
}


def _bytes(path: Path, expected_digest: str) -> bytes:
    data = path.read_bytes()
    if data.endswith(b"\n"):
        data = data[:-1]
    if f"sha256:{hashlib.sha256(data).hexdigest()}" != expected_digest:
        raise ValueError("manifest digest differs")
    return data


def select_child(path: Path, expected_digest: str) -> None:
    value = json.loads(_bytes(path, expected_digest))
    matches = [
        item
        for item in value.get("manifests", [])
        if item.get("platform", {}).get("os") == "linux"
        and item.get("platform", {}).get("architecture") == "amd64"
        and item.get("annotations", {}).get("vnd.docker.reference.type")
        != "attestation-manifest"
    ]
    if len(matches) != 1 or DIGEST.fullmatch(str(matches[0].get("digest"))) is None:
        raise ValueError("linux/amd64 child manifest differs")
    print(matches[0]["digest"])


def manifest_fact(path: Path, expected_digest: str, repository: str) -> None:
    data = _bytes(path, expected_digest)
    value = json.loads(data)
    media_type = value.get("mediaType")
    config = value.get("config", {}).get("digest")
    if media_type not in MEDIA_TYPES or DIGEST.fullmatch(str(config)) is None:
        raise ValueError("platform manifest is invalid")
    print(
        json.dumps(
            {
                "repository": repository,
                "platform_manifest_digest": expected_digest,
                "platform_manifest_media_type": media_type,
                "platform_manifest_byte_count": len(data),
                "operating_system": "linux",
                "architecture": "amd64",
                "config_image_id": config,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)
    child = subparsers.add_parser("select-child")
    child.add_argument("path", type=Path)
    child.add_argument("expected_digest")
    fact = subparsers.add_parser("manifest-fact")
    fact.add_argument("path", type=Path)
    fact.add_argument("expected_digest")
    fact.add_argument("repository")
    arguments = parser.parse_args()
    if DIGEST.fullmatch(arguments.expected_digest) is None:
        raise SystemExit("expected digest is invalid")
    try:
        if arguments.operation == "select-child":
            select_child(arguments.path, arguments.expected_digest)
        else:
            manifest_fact(
                arguments.path, arguments.expected_digest, arguments.repository
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
