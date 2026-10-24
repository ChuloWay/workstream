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

from scripts.checker_image_manifest import verify_platform_manifest
from scripts.checker_image_process import ImageError

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
            raise ImageError("duplicate archive members")

        def regular(name: str):
            member = members[name]
            if not member.isfile():
                raise ImageError("image member is not regular")
            return bundle.extractfile(member)

        def metadata(name: str):
            if members[name].size > MAX_METADATA:
                raise ImageError("image metadata exceeds limit")
            with regular(name) as source:
                return source.read()

        raw_manifest = metadata("blobs/sha256/" + manifest_digest.removeprefix("sha256:"))
        manifest = verify_platform_manifest(raw_manifest, manifest_digest)
        config_id = manifest["config"]["digest"]
        raw_config = metadata("blobs/sha256/" + config_id.removeprefix("sha256:"))
        if "sha256:" + hashlib.sha256(raw_config).hexdigest() != config_id:
            raise ImageError("config digest differs")
        if len(raw_config) != manifest["config"]["size"]:
            raise ImageError("config descriptor size differs")
        config = json.loads(raw_config)
        if (config["os"], config["architecture"]) != ("linux", "amd64"):
            raise ImageError("unsupported platform")
        saved = json.loads(metadata("manifest.json"))
        if len(saved) != 1 or saved[0]["Config"] != "blobs/sha256/" + config_id[7:]:
            raise ImageError("archive must contain exactly the approved image")
        layers = saved[0]["Layers"]
        descriptors = manifest["layers"]
        diff_ids = config["rootfs"]["diff_ids"]
        if len(layers) != len(diff_ids) or len(layers) != len(descriptors):
            raise ImageError("rootfs layer count differs")

        def uncompressed_digest(source):
            compressed = source.read(2) == b"\x1f\x8b"
            source.seek(0)
            return digest(gzip.GzipFile(fileobj=source) if compressed else source)

        for name, expected, descriptor in zip(layers, diff_ids, descriptors, strict=True):
            # Close the pinned manifest graph, independently of manifest.json's
            # selected Docker-save representation. Both must name the same bytes
            # after decompression, even when the archive stores a plain layer.
            approved = "blobs/sha256/" + descriptor["digest"][7:]
            if approved not in members or members[approved].size != descriptor["size"]:
                raise ImageError("approved layer descriptor is missing or differs")
            with regular(approved) as layer:
                if digest(layer) != descriptor["digest"]:
                    raise ImageError("approved layer blob digest differs")
                layer.seek(0)
                if uncompressed_digest(layer) != expected:
                    raise ImageError("approved rootfs layer digest differs")
            with regular(name) as layer:
                if uncompressed_digest(layer) != expected:
                    raise ImageError("rootfs layer digest differs")
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
