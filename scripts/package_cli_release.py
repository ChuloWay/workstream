"""Build and verify deterministic Workstream CLI release archives."""

from __future__ import annotations

import argparse
import hashlib
import io
import os
from pathlib import Path
import re
import subprocess
import tarfile
import zipfile


PLATFORMS = ("linux-amd64", "darwin-amd64", "darwin-arm64", "windows-amd64")
TAG = re.compile(r"cli-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


def validate(tag: str, commit: str, platform: str) -> tuple[str, str]:
    match = TAG.fullmatch(tag)
    if not match or not SHA.fullmatch(commit) or platform not in PLATFORMS:
        raise ValueError("invalid release tag, commit or platform")
    version = f"v{match.group(1)}.{match.group(2)}.{match.group(3)}+g{commit}"
    extension = "zip" if platform.startswith("windows-") else "tar.gz"
    return version, f"workstream-{tag}-{platform}.{extension}"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(source: Path, out: Path, tag: str, commit: str, platform: str) -> Path:
    version, name = validate(tag, commit, platform)
    source = source.resolve()
    out = out.resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError("output directory must be empty")
    out.mkdir(parents=True, exist_ok=True)
    executable = "workstream.exe" if platform.startswith("windows-") else "workstream"
    binary = out / executable
    env = os.environ.copy()
    env.update(
        CGO_ENABLED="0", GOOS=platform.split("-")[0], GOARCH=platform.split("-")[1]
    )
    command = [
        "go",
        "build",
        "-trimpath",
        "-buildvcs=false",
        "-ldflags",
        f"-buildid= -X main.version={version}",
        "-o",
        str(binary),
        "./cmd/workstream",
    ]
    subprocess.run(command, cwd=source / "cli", env=env, check=True)
    first = digest(binary)
    second = out / f"second-{executable}"
    command[command.index(str(binary))] = str(second)
    subprocess.run(command, cwd=source / "cli", env=env, check=True)
    if first != digest(second):
        raise ValueError("repeat build produced different bytes")
    second.unlink()
    license_bytes = (source / "LICENSE").read_bytes()
    archive = out / name
    if name.endswith(".zip"):
        with zipfile.ZipFile(
            archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as writer:
            for member, data, mode in (
                (executable, binary.read_bytes(), 0o755),
                ("LICENSE", license_bytes, 0o644),
            ):
                info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = mode << 16
                writer.writestr(
                    info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9
                )
    else:
        import gzip

        with (
            archive.open("wb") as raw,
            gzip.GzipFile(
                filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9
            ) as compressed,
        ):
            with tarfile.open(
                fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT
            ) as writer:
                for member, data, mode in (
                    (executable, binary.read_bytes(), 0o755),
                    ("LICENSE", license_bytes, 0o644),
                ):
                    info = tarfile.TarInfo(member)
                    info.size, info.mode, info.uid, info.gid, info.mtime = (
                        len(data),
                        mode,
                        0,
                        0,
                        0,
                    )
                    writer.addfile(info, io.BytesIO(data))
    binary.unlink()
    (out / f"{name}.sha256").write_text(
        f"{digest(archive)}  {name}\n", encoding="ascii"
    )
    return archive


def verify(root: Path, tag: str, commit: str, *, assembled: bool) -> list[Path]:
    expected = {validate(tag, commit, platform)[1] for platform in PLATFORMS}
    members = list(root.iterdir())
    if any(not member.is_file() or member.is_symlink() for member in members):
        raise ValueError("non-file release asset")
    if assembled:
        actual = {p.name for p in members}
        if actual != expected | {"SHA256SUMS"}:
            raise ValueError("incomplete or extra release assets")
        manifest = root / "SHA256SUMS"
        lines = manifest.read_text(encoding="ascii").splitlines()
        if lines != [f"{digest(root / name)}  {name}" for name in sorted(expected)]:
            raise ValueError("release checksum manifest mismatch")
    else:
        actual = {p.name for p in members}
        if actual != expected | {name + ".sha256" for name in expected}:
            raise ValueError("incomplete or extra native artifacts")
        for name in expected:
            if (root / f"{name}.sha256").read_text(
                encoding="ascii"
            ) != f"{digest(root / name)}  {name}\n":
                raise ValueError("native archive checksum mismatch")
    version = validate(tag, commit, "linux-amd64")[0].encode("ascii")
    for name in expected:
        binary_name = "workstream.exe" if name.endswith(".zip") else "workstream"
        archive = root / name
        if name.endswith(".zip"):
            with zipfile.ZipFile(archive) as reader:
                if reader.namelist() != [binary_name, "LICENSE"]:
                    raise ValueError("unexpected Windows archive members")
                binary_bytes = reader.read(binary_name)
        else:
            with tarfile.open(archive, "r:gz") as reader:
                members = reader.getmembers()
                if [member.name for member in members] != [
                    binary_name,
                    "LICENSE",
                ] or any(not member.isfile() for member in members):
                    raise ValueError("unexpected Unix archive members")
                binary_bytes = reader.extractfile(binary_name).read()
        if not re.search(
            rb"(?<![A-Za-z0-9_.+\-])" + re.escape(version) + rb"(?![A-Za-z0-9_.+\-])",
            binary_bytes,
        ):
            raise ValueError("embedded CLI version does not match release source")
    return [root / name for name in sorted(expected)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "assemble", "verify"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--platform", choices=PLATFORMS)
    arguments = parser.parse_args()
    if arguments.mode == "build":
        if not arguments.platform:
            parser.error("build requires --platform")
        build(
            arguments.root,
            arguments.out,
            arguments.tag,
            arguments.commit,
            arguments.platform,
        )
    elif arguments.mode == "assemble":
        sources = verify(
            arguments.root, arguments.tag, arguments.commit, assembled=False
        )
        if arguments.out.exists() and any(arguments.out.iterdir()):
            raise ValueError("output directory must be empty")
        arguments.out.mkdir(parents=True, exist_ok=True)
        for source in sources:
            (arguments.out / source.name).write_bytes(source.read_bytes())
        (arguments.out / "SHA256SUMS").write_text(
            "".join(f"{digest(source)}  {source.name}\n" for source in sources),
            encoding="ascii",
        )
        verify(arguments.out, arguments.tag, arguments.commit, assembled=True)
    else:
        verify(arguments.out, arguments.tag, arguments.commit, assembled=True)


if __name__ == "__main__":
    main()
