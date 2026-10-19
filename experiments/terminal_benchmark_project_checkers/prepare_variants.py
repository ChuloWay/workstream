#!/usr/bin/env python3
"""Prepare and verify the fixed PRE-valid WS493 negative proof packages."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile


SCHEMA = "workstream.terminal_benchmark_negative_packages.v1"
DIRECTORIES = ("environment", "solution", "tests", "workspace")
FILES = (
    ".dockerignore",
    "environment/Dockerfile",
    "instruction.md",
    "solution/program.py",
    "task.toml",
    "tests/cases.json",
    "tests/test_task.py",
    "workspace/program.py",
)
MAXIMUM_FILE_BYTES = 1_048_576
MAXIMUM_TOTAL_BYTES = 8_388_608
VARIANTS = {
    "capacity-spoof": (
        "tests/test_task.py",
        b'import sys\nprint("resource temporarily unavailable", file=sys.stderr)\nraise SystemExit(2)\n',
    ),
    "memory-capacity": (
        "tests/test_task.py",
        b'payload = []\nfor _ in range(75):\n    chunk = bytearray(8 * 1024 * 1024)\n    for offset in range(0, len(chunk), 4096):\n        chunk[offset] = 1\n    payload.append(chunk)\nraise AssertionError("memory limit was not enforced")\n',
    ),
    "no-op-pass": (
        "tests/test_task.py",
        b'import json\nprint(json.dumps({"status": "intentionally-ineffective"}, sort_keys=True))\n',
    ),
    "reference-failure": (
        "solution/program.py",
        b"raise SystemExit(2)\n",
    ),
    "reference-instability": (
        "tests/test_task.py",
        None,
    ),
}
INSTABILITY_SUFFIX = (
    b"\n# Emit only after the original assertions pass.\n"
    b"import socket\nprint(socket.gethostname())\n"
)


def _read_regular(root: Path, relative: str, *, expected_mode: int) -> bytes:
    path = root / relative
    metadata = os.lstat(path)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != expected_mode
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or metadata.st_size > MAXIMUM_FILE_BYTES
    ):
        raise ValueError(f"package file metadata differs: {relative}")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise ValueError(f"package file changed: {relative}")
        chunks: list[bytes] = []
        remaining = MAXIMUM_FILE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if len(data) > MAXIMUM_FILE_BYTES or (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError(f"package file changed: {relative}")
    return data


def _validate_tree(
    root: Path, *, directory_mode: int, file_mode: int
) -> dict[str, bytes]:
    root_metadata = os.lstat(root)
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_IMODE(root_metadata.st_mode) != directory_mode
        or (root_metadata.st_uid, root_metadata.st_gid) != (0, 0)
    ):
        raise ValueError("package root metadata differs")
    actual_directories: set[str] = set()
    actual_files: set[str] = set()
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in directories:
            path = current_path / name
            metadata = os.lstat(path)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != directory_mode
                or (metadata.st_uid, metadata.st_gid) != (0, 0)
            ):
                raise ValueError("package directory metadata differs")
            actual_directories.add(path.relative_to(root).as_posix())
        for name in files:
            actual_files.add((current_path / name).relative_to(root).as_posix())
    if actual_directories != set(DIRECTORIES) or actual_files != set(FILES):
        raise ValueError("package inventory differs")
    values = {
        relative: _read_regular(root, relative, expected_mode=file_mode)
        for relative in FILES
    }
    if sum(map(len, values.values())) > MAXIMUM_TOTAL_BYTES:
        raise ValueError("package byte limit exceeded")
    return values


def _write_regular(path: Path, data: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o444,
    )
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("variant write made no progress")
            view = view[written:]
        os.fchmod(descriptor, 0o444)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _variant_entries(values: dict[str, bytes]) -> list[dict[str, object]]:
    return [
        {
            "byte_count": len(values[relative]),
            "path": relative,
            "sha256": hashlib.sha256(values[relative]).hexdigest(),
        }
        for relative in FILES
    ]


def prepare(source: Path, destination: Path, head: str) -> None:
    if len(head) != 40 or any(
        character not in "0123456789abcdef" for character in head
    ):
        raise ValueError("proof head differs")
    source_values = _validate_tree(source, directory_mode=0o555, file_mode=0o444)
    if destination.exists() or destination.is_symlink():
        raise ValueError("variant destination must be absent")
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
    )
    published = False
    try:
        variants = []
        for name in sorted(VARIANTS):
            changed_path, replacement = VARIANTS[name]
            values = dict(source_values)
            if name == "reference-instability":
                values[changed_path] = values[changed_path] + INSTABILITY_SUFFIX
            else:
                assert replacement is not None
                values[changed_path] = replacement
            root = temporary / name
            root.mkdir(mode=0o755)
            for relative in DIRECTORIES:
                (root / relative).mkdir(mode=0o755)
            for relative in FILES:
                _write_regular(root / relative, values[relative])
            for relative in reversed(DIRECTORIES):
                os.chmod(root / relative, 0o555)
            os.chmod(root, 0o555)
            variants.append(
                {
                    "changed_path": changed_path,
                    "changed_sha256": hashlib.sha256(values[changed_path]).hexdigest(),
                    "entries": _variant_entries(values),
                    "name": name,
                }
            )
        inventory = {
            "head_sha": head,
            "schema_version": SCHEMA,
            "variants": variants,
        }
        _write_regular(
            temporary / ".inventory.json",
            (
                json.dumps(inventory, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode(),
        )
        os.chmod(temporary, 0o555)
        os.rename(temporary, destination)
        published = True
    finally:
        if not published:
            shutil.rmtree(temporary, ignore_errors=True)
    verify(destination, head)


def verify(root: Path, head: str) -> dict[str, object]:
    metadata = os.lstat(root)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o555
        or (metadata.st_uid, metadata.st_gid) != (0, 0)
    ):
        raise ValueError("variant root metadata differs")
    if set(os.listdir(root)) != {".inventory.json", *VARIANTS}:
        raise ValueError("variant root inventory differs")
    inventory = json.loads(
        _read_regular(root, ".inventory.json", expected_mode=0o444).decode("utf-8")
    )
    if (
        set(inventory) != {"head_sha", "schema_version", "variants"}
        or inventory.get("head_sha") != head
        or inventory.get("schema_version") != SCHEMA
        or not isinstance(inventory.get("variants"), list)
    ):
        raise ValueError("variant inventory header differs")
    observed = []
    for name in sorted(VARIANTS):
        values = _validate_tree(root / name, directory_mode=0o555, file_mode=0o444)
        changed_path, _ = VARIANTS[name]
        observed.append(
            {
                "changed_path": changed_path,
                "changed_sha256": hashlib.sha256(values[changed_path]).hexdigest(),
                "entries": _variant_entries(values),
                "name": name,
            }
        )
    if inventory["variants"] != observed:
        raise ValueError("variant inventory content differs")
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)
    for operation in ("prepare", "verify", "evidence"):
        subparser = subparsers.add_parser(operation)
        if operation == "prepare":
            subparser.add_argument("source", type=Path)
        subparser.add_argument("destination", type=Path)
        subparser.add_argument("head")
    arguments = parser.parse_args()
    if arguments.operation == "prepare":
        prepare(arguments.source, arguments.destination, arguments.head)
    else:
        inventory = verify(arguments.destination, arguments.head)
        if arguments.operation == "evidence":
            print(json.dumps(inventory, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
