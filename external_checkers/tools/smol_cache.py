#!/usr/bin/env python3
"""Verify a Docker-save archive and emit one Smol node cache entry.

The operator supplies the approved *platform manifest* identity. No pulling,
registration, policy mutation or archive extraction is performed. The archive
must include its exact OCI manifest/config blobs and plain or gzip rootfs layers.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import tarfile

MAX_METADATA = 10 * 1024 * 1024


def digest(stream) -> str:
    value = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):
        value.update(chunk)
    return "sha256:" + value.hexdigest()


def provision(archive: Path, repository: str, manifest_digest: str, destination: Path) -> dict:
    archive = archive.resolve(strict=True)
    with tarfile.open(archive, "r:") as bundle:
        members = {item.name: item for item in bundle.getmembers()}
        if len(members) != len(bundle.getmembers()):
            raise ValueError("duplicate archive members")

        def regular(name: str):
            member = members[name]
            if not member.isfile():
                raise ValueError("image member is not regular")
            return bundle.extractfile(member)

        def metadata(name: str):
            if members[name].size > MAX_METADATA:
                raise ValueError("image metadata exceeds limit")
            with regular(name) as source:
                return source.read()

        raw_manifest = metadata("blobs/sha256/" + manifest_digest.removeprefix("sha256:"))
        if "sha256:" + hashlib.sha256(raw_manifest).hexdigest() != manifest_digest:
            raise ValueError("platform manifest digest differs")
        manifest = json.loads(raw_manifest)
        if manifest.get("mediaType") not in {
            "application/vnd.oci.image.manifest.v1+json",
            "application/vnd.docker.distribution.manifest.v2+json",
        }:
            raise ValueError("an exact platform manifest is required")
        config_id = manifest["config"]["digest"]
        raw_config = metadata("blobs/sha256/" + config_id.removeprefix("sha256:"))
        if "sha256:" + hashlib.sha256(raw_config).hexdigest() != config_id:
            raise ValueError("config digest differs")
        config = json.loads(raw_config)
        if (config["os"], config["architecture"]) != ("linux", "amd64"):
            raise ValueError("unsupported platform")
        saved = json.loads(metadata("manifest.json"))
        if len(saved) != 1 or saved[0]["Config"] != "blobs/sha256/" + config_id[7:]:
            raise ValueError("archive must contain exactly the approved image")
        layers = saved[0]["Layers"]
        if len(layers) != len(config["rootfs"]["diff_ids"]):
            raise ValueError("rootfs layer count differs")
        for name, expected in zip(layers, config["rootfs"]["diff_ids"], strict=True):
            with regular(name) as layer:
                compressed = layer.read(2) == b"\x1f\x8b"
                layer.seek(0)
                content = gzip.GzipFile(fileobj=layer) if compressed else layer
                if digest(content) != expected:
                    raise ValueError("rootfs layer digest differs")
    destination = destination.resolve()
    with destination.open("xb") as output:
        output.write(raw_config)
    destination.chmod(0o400)
    with archive.open("rb") as source:
        archive_digest = digest(source)
    archive.chmod(0o400)
    return {
        "repository": repository,
        "platform_manifest_digest": manifest_digest,
        "platform_manifest_media_type": manifest["mediaType"],
        "platform_manifest_byte_count": len(raw_manifest),
        "config_image_id": config_id,
        "operating_system": config["os"],
        "architecture": config["architecture"],
        "smol": {"archive": str(archive), "archive_sha256": archive_digest,
                 "image_config": str(destination)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--config-output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(provision(args.archive, args.repository, args.manifest, args.config_output)))


if __name__ == "__main__":
    main()
