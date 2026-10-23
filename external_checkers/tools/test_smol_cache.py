"""Cache verification rejects substitution before a VM can consume an image."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from smol_cache import provision


def sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class CacheTest(unittest.TestCase):
    def bundle(self, root, *, corrupt=False, compressed=False):
        layer = b"verified filesystem layer"
        config = json.dumps({"os": "linux", "architecture": "amd64",
                             "rootfs": {"diff_ids": [sha(layer)]},
                             "config": {"Entrypoint": ["/checker"]}}).encode()
        manifest = json.dumps({"mediaType": "application/vnd.oci.image.manifest.v1+json",
                               "config": {"digest": sha(config)}}).encode()
        config_name = "blobs/sha256/" + sha(config)[7:]
        entries = {config_name: config, "blobs/sha256/" + sha(manifest)[7:]: manifest,
                   "manifest.json": json.dumps([{"Config": config_name,
                                                   "Layers": ["layer"]}]).encode(),
                   "layer": b"substitution" if corrupt else gzip.compress(layer) if compressed else layer}
        archive = root / "image.tar"
        with tarfile.open(archive, "w") as output:
            for name, content in entries.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                output.addfile(info, io.BytesIO(content))
        return archive, sha(manifest), sha(config)

    def test_plain_and_compressed_layers_bind_the_same_config_identity(self):
        for compressed in (False, True):
            with self.subTest(compressed=compressed), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive, manifest, config = self.bundle(root, compressed=compressed)
                receipt = provision(archive, "test/checker", manifest, root / "config.json")
                self.assertEqual(receipt["config_image_id"], config)
                self.assertEqual(receipt["platform_manifest_digest"], manifest)
                self.assertEqual(receipt["smol"]["archive_sha256"], sha(archive.read_bytes()))

    def test_changed_rootfs_is_rejected_even_with_the_original_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive, manifest, _ = self.bundle(root, corrupt=True)
            with self.assertRaisesRegex(ValueError, "layer digest differs"):
                provision(archive, "test/checker", manifest, root / "config.json")
            self.assertFalse((root / "config.json").exists())


if __name__ == "__main__":
    unittest.main()
