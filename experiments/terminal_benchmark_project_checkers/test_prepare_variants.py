#!/usr/bin/env python3
"""Focused custody and mutation tests for the WS493 negative packages."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest

import prepare_variants


HEAD = "a" * 40


class VariantPreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        if os.geteuid() != 0:
            self.skipTest("root-owned production custody requires root")
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        source = (
            Path(__file__).parents[2]
            / "pilots/terminal_benchmark/packages/ledger-reconcile"
        )
        shutil.copytree(source, self.source)
        for path in self.source.rglob("*"):
            os.chown(path, 0, 0)
            path.chmod(0o555 if path.is_dir() else 0o444)
        os.chown(self.source, 0, 0)
        self.source.chmod(0o555)
        self.destination = self.root / "variants"

    def tearDown(self) -> None:
        if hasattr(self, "temporary"):
            self.temporary.cleanup()

    def test_exact_variants_prepare_and_verify(self) -> None:
        prepare_variants.prepare(self.source, self.destination, HEAD)
        prepare_variants.verify(self.destination, HEAD)
        self.assertEqual(
            set(self.destination.iterdir()),
            {self.destination / ".inventory.json"}
            | {self.destination / name for name in prepare_variants.VARIANTS},
        )
        self.assertIn(
            b"socket.gethostname",
            (
                self.destination / "reference-instability/tests/test_task.py"
            ).read_bytes(),
        )
        self.assertIn(
            b"SystemExit(2)",
            (self.destination / "capacity-spoof/tests/test_task.py").read_bytes(),
        )

    def test_extra_source_entry_is_rejected(self) -> None:
        path = self.source / "unexpected"
        path.write_text("unexpected", encoding="utf-8")
        os.chown(path, 0, 0)
        path.chmod(0o444)
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            prepare_variants.prepare(self.source, self.destination, HEAD)

    def test_source_symlink_is_rejected(self) -> None:
        path = self.source / "workspace/program.py"
        path.unlink()
        path.symlink_to("../solution/program.py")
        with self.assertRaisesRegex(ValueError, "inventory|metadata"):
            prepare_variants.prepare(self.source, self.destination, HEAD)

    def test_unsafe_mode_and_oversize_are_rejected(self) -> None:
        path = self.source / "workspace/program.py"
        path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "metadata differs"):
            prepare_variants.prepare(self.source, self.destination, HEAD)
        path.chmod(0o444)
        path.write_bytes(b"x" * (prepare_variants.MAXIMUM_FILE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "metadata differs"):
            prepare_variants.prepare(self.source, self.destination, HEAD)

    def test_substituted_variant_and_extra_variant_are_rejected(self) -> None:
        prepare_variants.prepare(self.source, self.destination, HEAD)
        path = self.destination / "no-op-pass/tests/test_task.py"
        path.chmod(0o644)
        path.write_text("pass\n", encoding="utf-8")
        path.chmod(0o444)
        with self.assertRaisesRegex(ValueError, "inventory content differs"):
            prepare_variants.verify(self.destination, HEAD)
        shutil.rmtree(self.destination)
        prepare_variants.prepare(self.source, self.destination, HEAD)
        extra = self.destination / "extra"
        extra.mkdir()
        with self.assertRaisesRegex(ValueError, "root inventory differs"):
            prepare_variants.verify(self.destination, HEAD)


if __name__ == "__main__":
    unittest.main()
