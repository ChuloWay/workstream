"""Bounded host processes for the checker image engineering command."""

from __future__ import annotations

import os
import selectors
import signal
import subprocess
import tempfile
import time


class ImageError(RuntimeError):
    """A publish prerequisite failed; messages never include child output."""


def run(
    argv: list[str],
    *,
    step: str,
    timeout: float = 120,
    limit: int = 8 * 1024 * 1024,
    data: bytes = b"",
    env: dict[str, str] | None = None,
) -> bytes:
    """Drain both pipes within one byte/time budget and kill owned processes on failure."""
    with tempfile.TemporaryFile() as source:
        source.write(data)
        source.seek(0)
        try:
            process = subprocess.Popen(
                argv,
                stdin=source,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                start_new_session=True,
            )
        except OSError as exc:
            raise ImageError(f"{step}: could not start the required command") from exc
        output = bytearray()
        consumed = 0
        deadline = time.monotonic() + timeout
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, True)
                selector.register(process.stderr, selectors.EVENT_READ, False)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise ImageError(f"{step}: deadline exceeded")
                    for key, _ in selector.select(min(remaining, 0.1)):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        consumed += len(chunk)
                        if consumed > limit:
                            raise ImageError(f"{step}: output limit exceeded")
                        if key.data:
                            output.extend(chunk)
                code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
                if code:
                    raise ImageError(f"{step}: command exited {code}")
                return bytes(output)
        except subprocess.TimeoutExpired as exc:
            raise ImageError(f"{step}: deadline exceeded") from exc
        finally:
            # Kill the process group even if its leader exited before a child.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            process.stdout.close()
            process.stderr.close()
