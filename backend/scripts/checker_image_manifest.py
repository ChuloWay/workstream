"""Canonical raw platform-manifest validation for publisher and node cache."""
from __future__ import annotations

import hashlib
import json
import re

from scripts.checker_image_process import ImageError

MANIFEST_TYPES = (
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
MAX_MANIFEST_BYTES = 10 * 1024 * 1024


def verify_platform_manifest(raw: bytes, digest: str) -> dict:
    """Reject indexes and bind the exact raw manifest and tested config identity."""
    try:
        manifest = json.loads(raw)
        if (
            not isinstance(manifest, dict)
            or manifest.get("mediaType") not in MANIFEST_TYPES
            or manifest.get("schemaVersion") != 2
            or not isinstance(manifest.get("layers"), list)
            or "manifests" in manifest
            or len(raw) > MAX_MANIFEST_BYTES
            or "sha256:" + hashlib.sha256(raw).hexdigest() != digest
        ):
            raise ValueError
        for descriptor in [manifest["config"], *manifest["layers"]]:
            if (
                not isinstance(descriptor, dict)
                or not isinstance(descriptor.get("digest"), str)
                or DIGEST.fullmatch(descriptor["digest"]) is None
                or type(descriptor.get("size")) is not int
                or descriptor["size"] < 0
                or not isinstance(descriptor.get("mediaType"), str)
                or not descriptor["mediaType"]
            ):
                raise ValueError
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ImageError("platform manifest does not match the tested image") from exc
    return manifest
