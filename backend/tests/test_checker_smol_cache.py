"""The node cache must execute the complete approved image graph."""
import gzip
import hashlib
import io
import json
import tarfile

import pytest

from scripts.checker_image_process import ImageError
from scripts.checker_smol_cache import provision


def sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def bundle(root, *, compressed=False, defect=None):
    layer = b"verified filesystem layer"
    blob = gzip.compress(layer) if compressed else layer
    descriptor = {"mediaType": "application/vnd.oci.image.layer.v1.tar" + ("+gzip" if compressed else ""),
                  "digest": sha(blob), "size": len(blob)}
    config = json.dumps({"os": "linux", "architecture": "amd64",
                         "rootfs": {"diff_ids": [sha(layer)]},
                         "config": {"Entrypoint": ["/checker"]}}).encode()
    manifest = {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "config": {"digest": sha(config), "size": len(config),
                           "mediaType": "application/vnd.oci.image.config.v1+json"},
                "layers": [descriptor]}
    if defect == "wrong_schema":
        manifest["schemaVersion"] = 1
    if defect == "index":
        manifest["manifests"] = []
    if defect == "missing_approved_layer":
        descriptor["digest"] = sha(b"other layer")
    if defect == "wrong_size":
        descriptor["size"] += 1
    if defect == "missing_layers":
        del manifest["layers"]
    raw_manifest = json.dumps(manifest).encode()
    config_name = "blobs/sha256/" + sha(config)[7:]
    selected = b"substitution" if defect == "changed_rootfs" else blob
    entries = {config_name: config, "blobs/sha256/" + sha(raw_manifest)[7:]: raw_manifest,
               "manifest.json": json.dumps([{"Config": config_name, "Layers": ["selected-layer"]}]).encode(),
               "selected-layer": selected, "blobs/sha256/" + sha(blob)[7:]: blob}
    path = root / "image.tar"
    with tarfile.open(path, "w") as output:
        for name, content in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            output.addfile(info, io.BytesIO(content))
    return path, sha(raw_manifest), sha(config)


@pytest.mark.parametrize("compressed", [False, True])
def test_plain_and_compressed_layers_bind_the_approved_graph(tmp_path, compressed):
    archive, manifest, config = bundle(tmp_path, compressed=compressed)
    receipt = provision(archive, "test/checker", manifest, tmp_path / "config.json")
    assert receipt["config_image_id"] == config
    assert receipt["platform_manifest_digest"] == manifest
    assert receipt["smol"]["archive_sha256"] == sha(archive.read_bytes())


@pytest.mark.parametrize("defect", ["wrong_schema", "index", "missing_layers",
                                    "missing_approved_layer", "wrong_size", "changed_rootfs"])
def test_manifest_and_rootfs_substitution_never_publish_a_cache_entry(tmp_path, defect):
    archive, manifest, _ = bundle(tmp_path, defect=defect)
    with pytest.raises(ImageError):
        provision(archive, "test/checker", manifest, tmp_path / "config.json")
    assert not (tmp_path / "config.json").exists()
