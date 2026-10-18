"""Built CLI download uses only public source reads and publishes verified bytes."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

from test_http_boundary import PROJECT, TOKEN
from test_task_batch_sources_http import RAW, SOURCE, source


@contextmanager
def source_server():
    state = {
        "metadata": source(),
        "status_code": 200,
        "content_code": 200,
        "content": RAW,
        "content_headers": {"Content-Type": "application/json"},
        "requests": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - standard HTTP handler interface
            state["requests"].append((self.path, self.headers.get("Authorization")))
            is_content = self.path.endswith("/content")
            if is_content:
                status = state["content_code"]
                body = state["content"]
                headers = state["content_headers"]
            else:
                status = state["status_code"]
                body = json.dumps(state["metadata"]).encode()
                headers = {"Content-Type": "application/json"}
                callback = state.pop("before_status", None)
                if callback is not None:
                    callback()
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def invoke(cli, origin, directory, *, project=PROJECT, selector=SOURCE, output="json"):
    return cli(
        origin, TOKEN, "-o", output, "project", "task-batch", "source-download",
        project, selector, "--download", str(directory),
    )


def failure(result, code, *, exit_code=1):
    assert result.returncode == exit_code and result.stdout == "", result.stderr
    assert json.loads(result.stderr)["error"]["code"] == code


def test_verified_original_exact_public_reads_and_private_no_overwrite(cli, tmp_path):
    destination = tmp_path / "downloads"
    destination.mkdir()
    name = SOURCE + ".json"
    with source_server() as (origin, state):
        result = invoke(cli, origin, destination)
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert json.loads(result.stdout) == {"downloaded": name, "source": source()}
        assert (destination / name).read_bytes() == RAW
        prefix = f"/api/v1/projects/{PROJECT}/task-import-sources/{SOURCE}"
        assert state["requests"] == [
            (prefix, "Bearer " + TOKEN),
            (prefix + "/content", "Bearer " + TOKEN),
        ]
        assert [path.name for path in destination.iterdir()] == [name]

        failure(invoke(cli, origin, destination), "invalid_arguments", exit_code=2)
        assert state["requests"][-1] == (prefix, "Bearer " + TOKEN)
        assert (destination / name).read_bytes() == RAW

        (destination / name).unlink()
        text = invoke(cli, origin, destination, output="text")
        assert text.returncode == 0 and text.stdout == f"Downloaded: {name}\n"
        assert (destination / name).read_bytes() == RAW


def test_compact_selector_preserves_wire_identity_but_canonicalizes_filename(cli, tmp_path):
    compact = SOURCE.replace("-", "")
    with source_server() as (origin, state):
        result = invoke(cli, origin, tmp_path, selector=compact)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["downloaded"] == SOURCE + ".json"
        assert (tmp_path / (SOURCE + ".json")).read_bytes() == RAW
        assert state["requests"] == [
            (f"/api/v1/projects/{PROJECT}/task-import-sources/{compact}", "Bearer " + TOKEN),
            (f"/api/v1/projects/{PROJECT}/task-import-sources/{compact}/content", "Bearer " + TOKEN),
        ]


def test_unsafe_destination_and_invalid_selectors_never_contact_api(cli, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with source_server() as (origin, state):
        for destination, project, selector in (
            (link, PROJECT, SOURCE),
            (tmp_path / "missing", PROJECT, SOURCE),
            (real, "../private", SOURCE),
            (real, PROJECT, "../private"),
        ):
            result = invoke(cli, origin, destination, project=project, selector=selector)
            assert result.returncode == 2 and result.stdout == "", result.stderr
        assert state["requests"] == []
        assert list(real.iterdir()) == []


def test_metadata_identity_status_and_content_authority_fail_closed(cli, tmp_path):
    with source_server() as (origin, state):
        for metadata in (
            source() | {"source_id": PROJECT},
            source() | {"project_id": SOURCE},
            source() | {"sha256": "invalid"},
            source() | {"byte_count": 8388609},
            source() | {"storage_key": "private"},
        ):
            state["metadata"] = metadata
            failure(invoke(cli, origin, tmp_path), "invalid_api_response")
            assert state["requests"][-1][0].endswith(SOURCE)
        state["metadata"] = source("declared")
        failure(invoke(cli, origin, tmp_path), "task_import_source_not_verified")
        assert state["requests"][-1][0].endswith(SOURCE)
        state["metadata"] = source()
        state["content_code"] = 404
        state["content"] = b'{"error":{"code":"resource_not_found"}}'
        failure(invoke(cli, origin, tmp_path), "resource_not_found")
        assert list(tmp_path.iterdir()) == []


def test_mismatched_content_never_publishes_partial_file(cli, tmp_path):
    with source_server() as (origin, state):
        variants = (
            (RAW, {"Content-Type": "text/plain"}),
            (RAW, {"Content-Type": "application/json", "Content-Length": str(len(RAW) + 1)}),
            (RAW[:-1] + b" ", {"Content-Type": "application/json"}),
            (RAW + b" ", {"Content-Type": "application/json"}),
            (RAW[:-1], {"Content-Type": "application/json"}),
            (RAW, {"Content-Type": "application/json", "Content-Encoding": "gzip"}),
        )
        for body, headers in variants:
            state["content"], state["content_headers"] = body, headers
            failure(invoke(cli, origin, tmp_path), "task_import_source_integrity_mismatch")
            assert list(tmp_path.iterdir()) == []


def test_broken_content_stream_removes_private_partial_file(cli, tmp_path):
    with source_server() as (origin, state):
        state["content"] = RAW[:10]
        state["content_headers"] = {
            "Content-Type": "application/json", "Content-Length": str(len(RAW)),
        }
        failure(invoke(cli, origin, tmp_path), "task_import_source_download_failed")
        assert list(tmp_path.iterdir()) == []


def test_content_redirect_is_not_followed_or_published(cli, tmp_path):
    with source_server() as (origin, state):
        state["content_code"] = 302
        state["content_headers"] = {"Location": "https://storage.invalid/private"}
        state["content"] = b""
        failure(invoke(cli, origin, tmp_path), "redirect_refused")
        assert len(state["requests"]) == 2
        assert list(tmp_path.iterdir()) == []


def test_existing_symlink_or_different_uuid_spelling_cannot_replace_target(cli, tmp_path):
    target = tmp_path / (SOURCE + ".json")
    keep = tmp_path / "keep"
    keep.write_bytes(b"preserve")
    target.symlink_to(keep)
    with source_server() as (origin, state):
        failure(invoke(cli, origin, tmp_path, selector=SOURCE.replace("-", "")), "invalid_arguments", exit_code=2)
        assert target.is_symlink() and keep.read_bytes() == b"preserve"
        assert len(state["requests"]) == 1


def test_status_time_directory_swap_cannot_redirect_verified_source(cli, tmp_path):
    selected = tmp_path / "selected"
    selected.mkdir()
    original = tmp_path / "original-renamed"
    replacement = tmp_path / "replacement"
    replacement.mkdir()

    def swap():
        selected.rename(original)
        selected.symlink_to(replacement, target_is_directory=True)

    with source_server() as (origin, state):
        state["before_status"] = swap
        result = invoke(cli, origin, selected)
        assert result.returncode == 0 and result.stderr == "", result.stderr
        assert (original / (SOURCE + ".json")).read_bytes() == RAW
        assert list(replacement.iterdir()) == []
        assert selected.is_symlink()
        assert len(state["requests"]) == 2
