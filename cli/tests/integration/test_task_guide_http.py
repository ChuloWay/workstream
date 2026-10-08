"""Built CLI guide reads and safe publication against hostile HTTP boundaries."""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from uuid import uuid4

import pytest

from test_http_boundary import TOKEN, ACTOR
from test_task_context_http import CONTEXT
from test_task_http_boundary import TASK

ORIGINAL = b"%PDF-1.7\n" + b"Read the project guide.\n" * 4000
DOCUMENT = {
    "document_id": ACTOR,
    "order": 0,
    "label": "../unsafe\n\x1b[31m\u202e.pdf",
    "media_type": "application/pdf",
    "byte_count": len(ORIGINAL),
    "sha256": "sha256:" + hashlib.sha256(ORIGINAL).hexdigest(),
    "read_reference": f"/api/v1/tasks/{TASK}/guide/documents/{ACTOR}/content",
}


@contextmanager
def guide_http():
    context = deepcopy(CONTEXT)
    context["lifecycle"] = {"assigned_to_current_actor": True, "next_actions": []}
    context["guide_documents"] = [deepcopy(DOCUMENT)]
    state = {
        "context": context,
        "bytes": ORIGINAL,
        "status": 200,
        "headers": {"Content-Type": "application/pdf"},
    }
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            requests.append((self.path, self.headers.get("Authorization")))
            if self.path.endswith("/work-context"):
                status, body, headers = (
                    200,
                    json.dumps(state["context"]).encode(),
                    {"Content-Type": "application/json"},
                )
            else:
                status, body, headers = (
                    state["status"],
                    state["bytes"],
                    state["headers"],
                )
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_assigned_guide_list_and_verified_private_download(cli, tmp_path):
    with guide_http() as (origin, state, requests):
        listed = cli(origin, TOKEN, "task", "guide", TASK, "-o", "json")
        assert listed.returncode == 0 and json.loads(listed.stdout) == [DOCUMENT], (
            listed.stderr
        )
        terminal = cli(origin, TOKEN, "task", "guide", TASK)
        assert (
            terminal.returncode == 0
            and "\x1b" not in terminal.stdout
            and "\u202e" not in terminal.stdout
        )
        destination = tmp_path / "guides"
        destination.mkdir()
        downloaded = cli(
            origin,
            TOKEN,
            "task",
            "guide",
            TASK.replace("-", ""),
            "--download",
            str(destination),
            "-o",
            "json",
        )
        assert downloaded.returncode == 0, downloaded.stderr
        target = destination / f"{ACTOR}.pdf"
        assert (
            target.read_bytes() == ORIGINAL and target.stat().st_mode & 0o777 == 0o600
        )
        assert list(destination.iterdir()) == [target]
        assert requests[-1] == (DOCUMENT["read_reference"], "Bearer " + TOKEN)
        before = len(requests)
        refused = cli(
            origin, TOKEN, "task", "guide", TASK, "--download", str(destination)
        )
        assert refused.returncode != 0 and target.read_bytes() == ORIGINAL
        assert len(requests) == before + 1  # No second download attempt or overwrite.


def test_full_document_list_uses_bounded_context_not_small_page_limit(cli):
    with guide_http() as (origin, state, requests):
        documents = []
        for order in range(100):
            document = dict(
                DOCUMENT,
                document_id=str(uuid4()),
                order=order,
                label="\U0001f9ea" * 500,
            )
            document["read_reference"] = (
                f"/api/v1/tasks/{TASK}/guide/documents/{document['document_id']}/content"
            )
            documents.append(document)
        state["context"]["guide_documents"] = documents
        assert len(json.dumps(state["context"]).encode()) > 64 * 1024
        result = cli(origin, TOKEN, "task", "guide", TASK, "-o", "json")
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == documents and len(requests) == 1


@pytest.mark.parametrize("damage", ("hash", "short", "long", "content_type"))
def test_unverified_download_is_not_published(cli, tmp_path, damage):
    with guide_http() as (origin, state, _):
        if damage == "hash":
            state["bytes"] = b"X" + ORIGINAL[1:]
        elif damage == "short":
            state["bytes"] = ORIGINAL[:-1]
        elif damage == "long":
            state["bytes"] = ORIGINAL + b"EXTRA"
        else:
            state["headers"]["Content-Type"] = "text/plain"
        result = cli(
            origin,
            TOKEN,
            "task",
            "guide",
            TASK,
            "--download",
            str(tmp_path),
            "-o",
            "json",
        )
        assert result.returncode != 0 and result.stdout == ""
        assert (
            json.loads(result.stderr)["error"]["code"]
            == "guide_document_integrity_mismatch"
        )
        assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "field,value",
    (
        ("read_reference", "https://evil.invalid/steal"),
        ("document_id", "../outside"),
        ("sha256", "sha256:" + "z" * 64),
        ("byte_count", 0),
        ("byte_count", 512 * 1024 * 1024 + 1),
        ("order", -1),
        ("media_type", "text/html"),
        ("storage_key", "private"),
    ),
)
def test_malformed_guide_metadata_never_dispatches_download(
    cli, tmp_path, field, value
):
    with guide_http() as (origin, state, requests):
        state["context"]["guide_documents"][0][field] = value
        result = cli(
            origin,
            TOKEN,
            "task",
            "guide",
            TASK,
            "--download",
            str(tmp_path),
            "-o",
            "json",
        )
        assert result.returncode != 0 and result.stdout == ""
        assert json.loads(result.stderr)["error"]["code"] == "invalid_api_response"
        assert len(requests) == 1 and list(tmp_path.iterdir()) == []


def test_canonical_duplicate_document_ids_are_rejected(cli):
    with guide_http() as (origin, state, requests):
        duplicate = deepcopy(DOCUMENT) | {
            "document_id": ACTOR.replace("-", ""),
            "order": 1,
        }
        state["context"]["guide_documents"].append(duplicate)
        result = cli(origin, TOKEN, "task", "guide", TASK, "-o", "json")
        assert (
            result.returncode != 0
            and json.loads(result.stderr)["error"]["code"] == "invalid_api_response"
        )
        assert len(requests) == 1


def test_assignment_and_symlink_targets_fail_without_download(cli, tmp_path):
    with guide_http() as (origin, state, requests):
        state["context"]["lifecycle"]["assigned_to_current_actor"] = False
        state["context"]["guide_documents"] = []
        denied = cli(
            origin,
            TOKEN,
            "task",
            "guide",
            TASK,
            "--download",
            str(tmp_path),
            "-o",
            "json",
        )
        assert (
            denied.returncode != 0
            and json.loads(denied.stderr)["error"]["code"] == "task_assignment_required"
        )
        assert len(requests) == 1
        state["context"]["lifecycle"]["assigned_to_current_actor"] = True
        state["context"]["guide_documents"] = [deepcopy(DOCUMENT)]
        outside = tmp_path / "outside"
        outside.write_bytes(b"UNTOUCHED")
        (tmp_path / f"{ACTOR}.pdf").symlink_to(outside)
        denied = cli(origin, TOKEN, "task", "guide", TASK, "--download", str(tmp_path))
        assert denied.returncode != 0 and outside.read_bytes() == b"UNTOUCHED"
        assert len(requests) == 2


@pytest.mark.parametrize("status", (401, 404, 302, 503))
def test_download_reauthorizes_and_preserves_bounded_errors(cli, tmp_path, status):
    with guide_http() as (origin, state, requests):
        state["status"] = status
        state["bytes"] = json.dumps(
            {"error": {"code": "permission_not_granted"}}
        ).encode()
        state["headers"] = {
            "Content-Type": "application/json",
            "Location": "https://evil.invalid/steal",
        }
        result = cli(
            origin,
            TOKEN,
            "task",
            "guide",
            TASK,
            "--download",
            str(tmp_path),
            "-o",
            "json",
        )
        assert result.returncode != 0 and result.stdout == ""
        error = json.loads(result.stderr)["error"]
        assert error["status"] == status and error["code"] == (
            "redirect_refused" if status == 302 else "permission_not_granted"
        )
        assert len(requests) == 2 and list(tmp_path.iterdir()) == []
