"""Native installation smoke for a packaged Workstream CLI."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import platform as host_platform
import shutil
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
import tarfile
import zipfile

from package_cli_release import digest, validate


PROFILE = {
    "actor_profile_id": "018f0ebc-7966-7e8d-bc4d-1cae1e000001",
    "actor_kind": "human",
    "status": "active",
    "domains": ["contributor"],
    "admin_roles": [],
    "project_role_grants": [],
    "display_name": "Release smoke",
    "contact_email": None,
    "created_at": "2026-10-01T00:00:00Z",
    "updated_at": "2026-10-01T00:00:00Z",
    "last_seen_at": None,
}


def native_platform() -> str:
    system = {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}.get(
        host_platform.system()
    )
    machine = {
        "x86_64": "amd64",
        "AMD64": "amd64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }.get(host_platform.machine())
    return f"{system}-{machine}"


def run(
    binary: Path, args: list[str], env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [str(binary), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode:
        raise AssertionError(
            f"installed command failed: {args}: exit {result.returncode}"
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    version, expected_name = validate(args.tag, args.commit, args.platform)
    if native_platform() != args.platform or args.archive.name != expected_name:
        raise AssertionError("archive does not match native runner")
    check_path = args.archive.with_name(args.archive.name + ".sha256")
    if (
        check_path.read_text(encoding="ascii")
        != f"{digest(args.archive)}  {args.archive.name}\n"
    ):
        raise AssertionError("archive checksum mismatch")
    executable = (
        "workstream.exe" if args.platform.startswith("windows-") else "workstream"
    )
    with TemporaryDirectory(prefix="workstream-cli-release-") as directory:
        root = Path(directory)
        install_dir = root / "bin"
        install_dir.mkdir()
        old = root / f"old-{executable}"
        environment = os.environ.copy()
        environment.update(
            CGO_ENABLED="0",
            GOOS=args.platform.split("-")[0],
            GOARCH=args.platform.split("-")[1],
        )
        subprocess.run(
            [
                "go",
                "build",
                "-trimpath",
                "-buildvcs=false",
                "-ldflags",
                "-buildid= -X main.version=v0.0.0+smoke",
                "-o",
                str(old),
                "./cmd/workstream",
            ],
            cwd=args.source / "cli",
            env=environment,
            check=True,
        )
        with (root / "staged").open("wb") as staged:
            if args.archive.name.endswith(".zip"):
                with zipfile.ZipFile(args.archive) as archive:
                    if archive.namelist() != [executable, "LICENSE"]:
                        raise AssertionError("archive member mismatch")
                    staged.write(archive.read(executable))
            else:
                with tarfile.open(args.archive, "r:gz") as archive:
                    if archive.getnames() != [executable, "LICENSE"]:
                        raise AssertionError("archive member mismatch")
                    staged.write(archive.extractfile(executable).read())
        staged = root / "staged"
        staged.chmod(0o755)
        installed = install_dir / executable

        # A fresh install and a prior-version overwrite are separate observations.
        shutil.copy2(staged, installed)
        assert version in run(installed, ["--version"]).stdout
        installed.unlink()
        shutil.copy2(old, installed)
        assert "v0.0.0+smoke" in run(installed, ["--version"]).stdout
        shutil.copy2(staged, installed)
        assert version in run(installed, ["--version"]).stdout
        shutil.copy2(old, installed)
        assert "v0.0.0+smoke" in run(installed, ["--version"]).stdout
        shutil.copy2(staged, installed)

        received: list[tuple[str, str]] = []
        token = "local-smoke-token-do-not-log"

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                received.append((self.path, self.headers.get("Authorization", "")))
                body = json.dumps(PROFILE).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            call_env = os.environ.copy()
            call_env.update(
                WORKSTREAM_API_URL=f"http://127.0.0.1:{server.server_port}",
                WORKSTREAM_TOKEN=token,
            )
            result = run(installed, ["whoami", "--output", "json"], call_env)
            assert json.loads(result.stdout) == PROFILE
            assert received == [("/api/v1/actors/me", f"Bearer {token}")]
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        installed.unlink()
        assert not installed.exists()
    print(
        f"native install, version, authenticated API, upgrade, rollback and removal passed: {args.platform}"
    )


if __name__ == "__main__":
    main()
