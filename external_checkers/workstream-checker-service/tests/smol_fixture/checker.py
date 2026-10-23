"""Adversarial runtime fixture. Never registered as a project evaluator."""
import errno
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import sys
import time


def denied(operation):
    try:
        value = operation()
    except OSError:
        return
    if hasattr(value, "close"):
        value.close()
    raise AssertionError("operation was allowed")


def evaluate(request):
    case = request["configuration"]["case"]
    if case == "sleep":
        time.sleep(30)
    elif case == "output":
        sys.stdout.write("x" * 1024 * 1024)
        sys.stdout.flush()
        time.sleep(30)
    elif case == "memory":
        # Incremental committed pages reach the cgroup ceiling. One huge mmap
        # can instead be refused by kernel overcommit before that boundary.
        allocated = []
        for _ in range(128):
            allocated.append(bytearray(4 * 1024 * 1024))
    elif case == "pids":
        children = []
        try:
            for _ in range(512):
                try:
                    pid = os.fork()
                except OSError as error:
                    assert error.errno == errno.EAGAIN
                    limit = max(16, min(256, request["registry"]["resources"]["memory_bytes"] // (16 * 1024 * 1024)))
                    assert len(children) == limit - 1
                    break
                if pid == 0:
                    time.sleep(30)
                    os._exit(0)
                children.append(pid)
            else:
                raise AssertionError("PID ceiling not enforced")
        finally:
            for pid in children:
                os.kill(pid, signal.SIGKILL)
            for pid in children:
                os.waitpid(pid, 0)
    elif case == "cpu":
        start = time.monotonic()
        cpu = time.process_time()
        while time.monotonic() - start < 3:
            pass
        ratio = (time.process_time() - cpu) / (time.monotonic() - start)
        assert ratio <= request["registry"]["resources"]["cpu_millis"] / 1000 + 0.15
    elif case == "disk":
        try:
            with open("/tmp/fill", "wb") as output:
                for _ in range(32):
                    output.write(b"x" * 1024 * 1024)
        except OSError as error:
            assert error.errno == errno.ENOSPC
        else:
            raise AssertionError("scratch disk ceiling not enforced")
        finally:
            Path("/tmp/fill").unlink(missing_ok=True)
    elif case == "isolation":
        assert os.getuid() != 0 and os.getgid() != 0
        assert all(int(line.split()[1], 16) == 0 for line in Path("/proc/self/status").read_text().splitlines() if line.startswith("Cap"))
        assert os.statvfs("/").f_flag & os.ST_RDONLY
        assert os.statvfs("/work/input").f_flag & os.ST_RDONLY
        assert not list(Path("/sys").iterdir())
        assert not list(Path("/run").iterdir())
        assert Path("/work/input/material.txt").read_bytes() == b"verified material"
        denied(lambda: open("/work/input/material.txt", "wb"))
        denied(lambda: open("/etc/passwd", "ab"))
        denied(lambda: open("/image-owned-device", "rb"))
        denied(lambda: socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM))
        denied(lambda: socket.create_connection(("1.1.1.1", 443), timeout=0.3))
        with open("/tmp/private", "wb") as temporary:
            temporary.write(b"scratch")
    elif case != "pass":
        raise AssertionError("unknown fixture case")


def main():
    request = json.load(sys.stdin)
    evaluate(request)
    body = {"schema_version": "external_checker_result.v1",
            "request_digest": request["request_digest"],
            "registry_entry_id": request["registry"]["registry_entry_id"],
            "registry_entry_digest": request["registry"]["entry_digest"],
            "phase": request["identity"]["phase"], "outcome": "completed", "verdict": "passed",
            "findings": [], "infrastructure_failure_code": None}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    body["result_digest"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    print(json.dumps(body, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
