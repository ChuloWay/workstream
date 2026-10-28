#!/usr/bin/env bash
# Build the pinned, static filesystem formatter used by the trusted Smol guest.
set -euo pipefail
umask 077

readonly SOURCE_COMMIT=7ee1d505ef3b37831215f490411f346fe57e9053
readonly SOURCE_VERSION=1.47.4
if [[ "$#" != 2 ]]; then
  echo "usage: $0 <clean-e2fsprogs-source> <new-output-directory>" >&2
  exit 2
fi
readonly source_root="$(realpath -- "$1")"
readonly output_root="$(realpath -m -- "$2")"
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || {
  echo "the Smol filesystem tool requires a Linux x86-64 build host" >&2
  exit 1
}
[[ "$(git -C "$source_root" rev-parse HEAD)" == "$SOURCE_COMMIT" ]] || {
  echo "source must be e2fsprogs $SOURCE_VERSION at $SOURCE_COMMIT" >&2
  exit 1
}
[[ -z "$(git -C "$source_root" status --porcelain --untracked-files=all)" ]] || {
  echo "source must be clean" >&2
  exit 1
}
[[ ! -e "$output_root" && ! -L "$output_root" ]] || {
  echo "output directory already exists" >&2
  exit 1
}
readonly build_root="$(mktemp -d)"
trap 'rm -rf -- "$build_root"' EXIT
mkdir "$build_root/home"
readonly source_epoch="$(git -C "$source_root" show -s --format=%ct HEAD)"
(
  cd "$build_root"
  env -i PATH=/usr/bin:/bin HOME="$build_root/home" CONFIG_SITE=/dev/null \
    SOURCE_DATE_EPOCH="$source_epoch" \
    "$source_root/configure" --disable-elf-shlibs --disable-nls \
    --disable-fuse2fs --disable-uuidd --disable-fsck --without-libarchive --enable-libuuid \
    --enable-libblkid CFLAGS=-O2 LDFLAGS=-static
  env -i PATH=/usr/bin:/bin HOME="$build_root/home" SOURCE_DATE_EPOCH="$source_epoch" \
    make -j1 libs
  env -i PATH=/usr/bin:/bin HOME="$build_root/home" SOURCE_DATE_EPOCH="$source_epoch" \
    make -j1 -C misc mke2fs.static
)
if readelf -l "$build_root/misc/mke2fs.static" | rg -q INTERP; then
  echo "formatter is dynamically linked" >&2
  exit 1
fi
[[ "$(git -C "$source_root" rev-parse HEAD)" == "$SOURCE_COMMIT" && \
   -z "$(git -C "$source_root" status --porcelain --untracked-files=all)" ]] || {
  echo "source changed during build" >&2
  exit 1
}
mkdir -- "$output_root"
install -m 0755 "$build_root/misc/mke2fs.static" "$output_root/mkfs.ext4"
python3 - "$output_root" "$SOURCE_COMMIT" "$SOURCE_VERSION" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
binary = root / "mkfs.ext4"
manifest = {
    "schema_version": "workstream.smol_filesystem_tool.v1",
    "source_repository": "https://git.kernel.org/pub/scm/fs/ext2/e2fsprogs.git",
    "source_commit": sys.argv[2],
    "source_version": sys.argv[3],
    "platform": "linux/amd64",
    "binary": binary.name,
    "sha256": "sha256:" + hashlib.sha256(binary.read_bytes()).hexdigest(),
    "byte_count": binary.stat().st_size,
}
with (root / "manifest.json").open("x") as stream:
    json.dump(manifest, stream, sort_keys=True, indent=2)
    stream.write("\n")
print(manifest["sha256"])
PY
