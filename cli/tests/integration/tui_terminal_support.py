"""Bounded POSIX terminal process driver; no application/model imports.

These tests exercise Linux/macOS PTYs, not Windows ConPTY. A passing native
package/install smoke test must not be reported as interactive terminal proof.
"""

from __future__ import annotations

from contextlib import contextmanager
import codecs
import errno
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import select
import signal
import struct
import subprocess
from threading import Thread
import time
import unicodedata

import pytest

if os.name == "posix":
    import fcntl
    import pty
    import termios


def executable():
    binary = os.environ.get("WORKSTREAM_CLI_EXECUTABLE")
    assert binary and Path(binary).is_file(), "build and set WORKSTREAM_CLI_EXECUTABLE"
    return binary


def environment(origin, token, extra=None):
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG"}}
    env.update(
        WORKSTREAM_API_URL=origin,
        WORKSTREAM_TOKEN=token,
        TERM="xterm-256color",
    )
    env.update(extra or {})
    return env


class Terminal:
    """A real child on a PTY with a bounded, minimal VT screen observer.

    The screen observer only handles renderer movement/erase/SGR, never executes
    OSC. Raw output is retained too, so hostile terminal controls cannot hide
    behind a screen parser that ignores them.
    """

    def __init__(self, origin, token, *args, columns=120, rows=40, extra_env=None):
        if os.name != "posix":
            pytest.skip("POSIX PTY proof; Windows requires independent ConPTY proof")
        self.master, self.slave = pty.openpty()
        self.original = termios.tcgetattr(self.slave)
        self.columns, self.rows = columns, rows
        self.resize(columns, rows, notify=False)
        self.raw = bytearray()
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.pending = ""
        self.sent_after = None
        self.x = self.y = 0
        self.cells = [[" "] * columns for _ in range(rows)]
        self.process = subprocess.Popen(  # noqa: S603 - built binary, fixed test argv
            [executable(), "tui", *args],
            stdin=self.slave,
            stdout=self.slave,
            stderr=self.slave,
            env=environment(origin, token, extra_env),
            start_new_session=True,
        )

    def resize(self, columns, rows, *, notify=True):
        fcntl.ioctl(
            self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0)
        )
        self.columns, self.rows = columns, rows
        if notify:
            self.cells = [[" "] * columns for _ in range(rows)]
            self.x = self.y = 0
            self.process.send_signal(signal.SIGWINCH)

    @property
    def screen(self):
        return "\n".join("".join(row).rstrip() for row in self.cells)

    def _render(self, text):
        self.pending += text
        while self.pending:
            if self.pending.startswith("\x1b"):
                match = re.match(r"\x1b\[([0-?]*)([ -/]*)([@-~])", self.pending)
                if match:
                    self.pending = self.pending[match.end() :]
                    params, _, command = match.groups()
                    values = [
                        int(part) if part.isdecimal() else 0
                        for part in params.lstrip("?<>=!").split(";")
                    ]
                    n = values[0] or 1
                    if command in {"H", "f"}:
                        self.y = min(self.rows - 1, n - 1)
                        self.x = min(
                            self.columns - 1,
                            (values[1] or 1) - 1 if len(values) > 1 else 0,
                        )
                    elif command == "A":
                        self.y = max(0, self.y - n)
                    elif command == "B":
                        self.y = min(self.rows - 1, self.y + n)
                    elif command == "d":
                        self.y = min(self.rows - 1, n - 1)
                    elif command in {"E", "F"}:
                        self.y = (
                            min(self.rows - 1, self.y + n)
                            if command == "E"
                            else max(0, self.y - n)
                        )
                        self.x = 0
                    elif command == "C":
                        self.x = min(self.columns - 1, self.x + n)
                    elif command == "D":
                        self.x = max(0, self.x - n)
                    elif command == "G":
                        self.x = min(self.columns - 1, n - 1)
                    elif command == "J":
                        if values[0] in {2, 3}:
                            self.cells = [
                                [" "] * self.columns for _ in range(self.rows)
                            ]
                        else:
                            self.cells[self.y][self.x :] = [" "] * (
                                self.columns - self.x
                            )
                            for row in range(self.y + 1, self.rows):
                                self.cells[row] = [" "] * self.columns
                    elif command == "K":
                        start, end = (
                            (0, self.columns)
                            if values[0] == 2
                            else (self.x, self.columns)
                        )
                        self.cells[self.y][start:end] = [" "] * (end - start)
                    elif command == "n" and params == "6":
                        os.write(self.master, b"\x1b[1;1R")
                    continue
                if self.pending.startswith("\x1b]"):
                    match = re.match(r"\x1b\].*?(?:\x07|\x1b\\)", self.pending, re.S)
                    if not match:
                        return
                    sequence = match.group()
                    self.pending = self.pending[match.end() :]
                    if sequence.startswith("\x1b]11;?"):
                        os.write(self.master, b"\x1b]11;rgb:0000/0000/0000\x1b\\")
                    elif sequence.startswith("\x1b]10;?"):
                        os.write(self.master, b"\x1b]10;rgb:ffff/ffff/ffff\x1b\\")
                    continue
                if len(self.pending) < 3 or self.pending.startswith("\x1b["):
                    return
                self.pending = self.pending[2:]
                continue
            character, self.pending = self.pending[0], self.pending[1:]
            if character == "\r":
                self.x = 0
            elif character == "\t":
                self.x = min(self.columns - 1, (self.x // 8 + 1) * 8)
            elif character == "\n":
                self.y += 1
                if self.y == self.rows:
                    self.cells.pop(0)
                    self.cells.append([" "] * self.columns)
                    self.y -= 1
            elif character == "\b":
                self.x = max(0, self.x - 1)
            elif character >= " " and not unicodedata.combining(character):
                if self.x >= self.columns:
                    self.x = 0
                    self.y = min(self.rows - 1, self.y + 1)
                self.cells[self.y][self.x] = character
                self.x += (
                    2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
                )

    def pump(self, seconds=0.1):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            ready, _, _ = select.select(
                [self.master], [], [], max(0, deadline - time.monotonic())
            )
            if not ready:
                break
            try:
                data = os.read(self.master, 65536)
            except OSError as error:
                if error.errno == errno.EIO:
                    break
                raise
            if not data:
                break
            self.raw.extend(data)
            assert len(self.raw) < 4 * 1024 * 1024, "unbounded terminal output"
            self._render(self.decoder.decode(data))

    def wait(self, text, timeout=10):
        deadline = time.monotonic() + timeout
        while (
            text not in self.screen
            or (self.sent_after is not None and len(self.raw) <= self.sent_after)
        ) and time.monotonic() < deadline:
            self.pump()
            assert self.process.poll() is None, f"TUI exited: {self.screen}"
        assert text in self.screen, f"missing {text!r} on screen:\n{self.screen}"
        assert self.sent_after is None or len(self.raw) > self.sent_after, (
            "no new terminal frame after input"
        )
        self.sent_after = None
        return self.screen

    def send(self, keys):
        # Observe output already queued before this input. Otherwise an expect
        # could mistake the previous project/detail's frame for the new result.
        self.pump(0.02)
        self.sent_after = len(self.raw)
        os.write(self.master, keys.encode() if isinstance(keys, str) else keys)

    def quit(self, key="q"):
        self.send(key)
        self.wait_exit()

    def wait_exit(self, expected=0):
        deadline = time.monotonic() + 10
        while self.process.poll() is None and time.monotonic() < deadline:
            self.pump()
        assert self.process.poll() == expected, f"TUI exit mismatch: {self.screen}"
        self.pump()
        restored = termios.tcgetattr(self.slave)
        assert restored == self.original, "terminal settings were not restored"
        for enabled, disabled in (
            (b"\x1b[?25l", b"\x1b[?25h"),
            (b"\x1b[?1049h", b"\x1b[?1049l"),
        ):
            if enabled in self.raw:
                assert self.raw.rfind(disabled) > self.raw.rfind(enabled), (
                    "terminal mode left active"
                )

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=5)
        os.close(self.master)
        os.close(self.slave)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


@contextmanager
def socket_peer(respond):
    """Threaded hostile HTTP peer: every unexpected request is recorded/fails."""
    requests = []
    failures = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - HTTP handler interface
            request = (self.command, self.path, self.headers.get("Authorization"))
            requests.append(request)
            try:
                status, body = respond(*request)
            except Exception as error:  # fixture errors must reach the test thread
                failures.append(error)
                status, body = 500, {"unexpected": True}
            encoded = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            try:
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError):
                pass  # cancellation closes the connection, not the test response

        do_POST = do_GET
        do_PUT = do_GET
        do_PATCH = do_GET
        do_DELETE = do_GET

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
        assert not failures, failures
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
