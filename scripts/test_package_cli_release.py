"""Fail-closed release bundle tests without a Go build or network."""

from __future__ import annotations

import io
from pathlib import Path
from tempfile import TemporaryDirectory
import tarfile
import unittest
import zipfile

from package_cli_release import PLATFORMS, digest, validate, verify


TAG = "cli-v0.1.0"
COMMIT = "a" * 40


class ReleaseBundleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive_names = []
        for platform in PLATFORMS:
            version, name = validate(TAG, COMMIT, platform)
            self.archive_names.append(name)
            binary_name = (
                "workstream.exe" if platform.startswith("windows-") else "workstream"
            )
            payload = f"native executable with {version}".encode()
            archive = self.root / name
            if name.endswith(".zip"):
                with zipfile.ZipFile(archive, "w") as writer:
                    writer.writestr(binary_name, payload)
                    writer.writestr("LICENSE", b"license")
            else:
                with tarfile.open(archive, "w:gz") as writer:
                    for member, data in (
                        (binary_name, payload),
                        ("LICENSE", b"license"),
                    ):
                        info = tarfile.TarInfo(member)
                        info.size = len(data)
                        writer.addfile(info, io.BytesIO(data))
        self.write_manifest()

    def write_manifest(self) -> None:
        (self.root / "SHA256SUMS").write_text(
            "".join(
                f"{digest(self.root / name)}  {name}\n"
                for name in sorted(self.archive_names)
            ),
            encoding="ascii",
        )

    def test_complete_release_bundle(self) -> None:
        self.assertEqual(len(verify(self.root, TAG, COMMIT, assembled=True)), 4)

    def test_missing_archive_fails(self) -> None:
        (self.root / self.archive_names[0]).unlink()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            verify(self.root, TAG, COMMIT, assembled=True)

    def test_extra_archive_fails(self) -> None:
        (self.root / "surprise.txt").write_text("extra", encoding="ascii")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            verify(self.root, TAG, COMMIT, assembled=True)

    def test_checksum_mismatch_fails(self) -> None:
        (self.root / self.archive_names[0]).write_bytes(b"substituted")
        with self.assertRaisesRegex(ValueError, "checksum"):
            verify(self.root, TAG, COMMIT, assembled=True)

    def test_wrong_embedded_source_fails_even_with_updated_checksum(self) -> None:
        name = next(name for name in self.archive_names if name.endswith(".zip"))
        archive = self.root / name
        with zipfile.ZipFile(archive, "w") as writer:
            writer.writestr("workstream.exe", b"wrong version")
            writer.writestr("LICENSE", b"license")
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "embedded CLI version"):
            verify(self.root, TAG, COMMIT, assembled=True)

    def test_version_suffix_fails_even_with_updated_checksum(self) -> None:
        name = next(name for name in self.archive_names if name.endswith(".zip"))
        archive = self.root / name
        version = validate(TAG, COMMIT, "windows-amd64")[0]
        with zipfile.ZipFile(archive, "w") as writer:
            writer.writestr(
                "workstream.exe", f"native executable with {version}-WRONG".encode()
            )
            writer.writestr("LICENSE", b"license")
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "embedded CLI version"):
            verify(self.root, TAG, COMMIT, assembled=True)

    def test_ambiguous_tag_fails(self) -> None:
        for tag in ("v0.1.0", "cli-v01.0.0", "cli-v0.1.0-rc1", "cli-v0.1.0\nother"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                validate(tag, COMMIT, "linux-amd64")


if __name__ == "__main__":
    unittest.main()
