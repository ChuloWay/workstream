"""Built TUI -> PTY -> adversarial socket; no model/runtime substitution."""

from copy import deepcopy
import os
import re
import subprocess
from threading import Event
from urllib.parse import parse_qs, urlsplit

import pytest

from test_contributor_reads_http import ASSIGNMENT_ROW, PROJECT_ROW, SUBMISSION_ROW
from test_contributor_task_http import CONTRIBUTOR, READY
from test_http_boundary import ACTOR, PROFILE, PROJECT, TOKEN
from test_submission_http import HISTORY, SUBMISSION
from test_task_context_http import CONTEXT, REQUIREMENTS
from test_task_http_boundary import TASK
from tui_terminal_support import Terminal, environment, executable, socket_peer

OTHER_PROJECT = "018f0ebc-7966-7e8d-bc4d-1cae1e000099"
OTHER_TASK = "018f0ebc-7966-7e8d-bc4d-1cae1e000098"
CURSOR = "opaque+/=&?#next"
READY_PATH = f"/api/v1/projects/{PROJECT}/tasks/ready"
TASK_PATH = f"/api/v1/tasks/{TASK}"
SECRET = "EXACT_PRIVATE_INSTRUCTIONS"
HOSTILE = "label\x1b]52;c;c2VjcmV0\x07\x1b]8;;https://evil.invalid\x1b\\link\x1b]8;;\x1b\\\x1b[31m\u202e\u2066\x85\u2028"


def page(row, cursor=None):
    return {"items": [row], "next_cursor": cursor}


class Reads:
    """Only the nine existing public reads; unexpected routes/writes fail."""

    def __init__(self):
        self.projects = page(PROJECT_ROW | {"name": "Terminal project"})
        self.ready = page(READY | {"title": "Ready terminal task"}, CURSOR) | {
            "project_id": PROJECT
        }
        self.mine = page(
            ASSIGNMENT_ROW
            | {"title": "Assigned terminal task", "locked_guide_version": "guide-1"}
        )
        self.submissions = page(
            SUBMISSION_ROW
            | {"title": "Owned terminal attempt", "submission_id": SUBMISSION}
        )
        self.task = CONTRIBUTOR | {
            "title": "Fresh terminal task",
            "description": SECRET,
        }
        self.context = deepcopy(CONTEXT)
        self.context["task"] = self.task
        self.context["contribution_policy_version_id"] = self.task["compensation"][
            "contribution_policy_version_id"
        ]
        self.requirements = deepcopy(REQUIREMENTS)
        self.submission = HISTORY | {
            "task_id": TASK,
            "summary": "Exact owned submission summary",
        }
        self.overrides = {}

    def __call__(self, method, target, authorization):
        assert method == "GET", "TUI attempted product mutation"
        assert authorization == "Bearer " + TOKEN
        parsed = urlsplit(target)
        path = parsed.path
        query = parse_qs(parsed.query)
        routes = {
            "/api/v1/actors/me": PROFILE,
            "/api/v1/actors/me/projects": self.projects,
            READY_PATH: self.ready,
            "/api/v1/actors/me/assignments": self.mine,
            "/api/v1/actors/me/submissions": self.submissions,
            TASK_PATH: self.task,
            TASK_PATH + "/work-context": self.context,
            TASK_PATH + "/submission-requirements": self.requirements,
            f"/api/v1/submissions/{SUBMISSION}": self.submission,
        }
        assert path in routes or path in self.overrides, f"unlisted TUI read: {path}"
        if path in self.overrides:
            return self.overrides[path](query)
        if path == "/api/v1/actors/me/projects":
            assert query == {"limit": ["50"]}
        elif path == READY_PATH:
            assert query in ({"limit": ["50"]}, {"limit": ["50"], "cursor": [CURSOR]})
        elif path == "/api/v1/actors/me/assignments":
            assert query == {
                "limit": ["50"],
                "project_id": [PROJECT],
                "state": ["active"],
            }
        elif path == "/api/v1/actors/me/submissions":
            assert query == {"limit": ["50"], "project_id": [PROJECT]}
        else:
            assert query == {}
        return 200, routes[path]


def open_ready(terminal, project_name="Terminal project"):
    terminal.wait(project_name)
    terminal.send("\r")
    terminal.wait("Ready terminal task")


def denial(status=404):
    return status, {
        "error": {
            "code": "resource_not_found",
            "message": TOKEN + HOSTILE,
            "correlation_id": ACTOR,
            "details": {},
            "retryable": False,
        }
    }


def test_keyboard_journey_uses_only_nine_fresh_public_reads():
    reads = Reads()
    with (
        socket_peer(reads) as (origin, requests),
        Terminal(origin, TOKEN, "--plain") as terminal,
    ):
        open_ready(terminal)
        assert len(requests) == 3  # actor binding, membership, one selected list
        terminal.send("?")
        terminal.wait("KEYBOARD HELP")
        assert len(requests) == 3
        terminal.send("\x1b")
        terminal.wait("Ready terminal task")
        terminal.send("\r")
        terminal.wait(SECRET)
        assert TASK in terminal.screen and PROJECT in terminal.screen
        assert "2.125000000000000001" in terminal.screen
        assert "unpaid" in terminal.screen
        terminal.send("\t")
        terminal.pump(0.2)
        assert len(requests) == 4, "Ready eagerly fetched assignment context"
        terminal.send("c")
        terminal.wait("workstream")
        assert "task" in terminal.screen and TASK in terminal.screen
        assert len(requests) == 4, "inert argv issued a request"
        terminal.send("c\x1b")
        terminal.wait("Ready terminal task")
        terminal.send("\t")
        terminal.wait("Assigned terminal task")
        terminal.send("\r")
        terminal.wait(SECRET)
        terminal.send("\t")
        terminal.wait("CONTEXT")
        terminal.wait("guide-1")
        terminal.send("\t")
        terminal.wait("INTAKE")
        terminal.wait("answer.md")
        terminal.send("\x1b")
        terminal.wait("Assigned terminal task")
        terminal.send("\t")
        terminal.wait("Owned terminal attempt")
        terminal.send("\r")
        terminal.wait("Exact owned submission summary")
        assert SUBMISSION in terminal.screen and TASK in terminal.screen
        terminal.send("c")
        terminal.wait("findings")
        assert "manual" in terminal.screen.lower()
        terminal.quit()
        assert [urlsplit(target).path for _, target, _ in requests] == [
            "/api/v1/actors/me",
            "/api/v1/actors/me/projects",
            READY_PATH,
            TASK_PATH,
            "/api/v1/actors/me/assignments",
            TASK_PATH,
            TASK_PATH + "/work-context",
            TASK_PATH + "/submission-requirements",
            "/api/v1/actors/me/submissions",
            f"/api/v1/submissions/{SUBMISSION}",
        ]
        assert TOKEN.encode() not in terminal.raw


def test_startup_retry_binds_profile_before_any_project_read():
    reads = Reads()
    profile_reads = 0

    def profile(_):
        nonlocal profile_reads
        profile_reads += 1
        return denial(503) if profile_reads == 1 else (200, PROFILE)

    reads.overrides["/api/v1/actors/me"] = profile
    with (
        socket_peer(reads) as (origin, requests),
        Terminal(origin, TOKEN, "--plain") as terminal,
    ):
        terminal.wait("Unavailable")
        terminal.pump(0.2)
        assert len(requests) == 1, "failed actor binding must not fetch projects"
        terminal.send("r")
        terminal.wait("Terminal project")
        assert [urlsplit(target).path for _, target, _ in requests] == [
            "/api/v1/actors/me",
            "/api/v1/actors/me",
            "/api/v1/actors/me/projects",
        ]
        terminal.quit()


def test_explicit_pagination_refresh_and_local_filter_do_not_walk_pages():
    reads = Reads()

    def ready(query):
        assert query.get("limit") == ["50"]
        if "cursor" in query:
            assert query["cursor"] == [CURSOR]
            return 200, page(READY | {"title": "Second page only"}) | {
                "project_id": PROJECT
            }
        return 200, reads.ready

    reads.overrides[READY_PATH] = ready
    with (
        socket_peer(reads) as (origin, requests),
        Terminal(origin, TOKEN, "--plain") as terminal,
    ):
        open_ready(terminal)
        terminal.pump(0.2)
        assert len(requests) == 3
        terminal.send("/nothing-matches\r")
        terminal.pump(0.2)
        assert "Ready terminal task" not in terminal.screen
        assert "local" in terminal.screen.lower()
        assert len(requests) == 3
        terminal.send("/\x1b")
        terminal.pump(0.2)  # a lone Escape must not combine with n as Alt+n
        terminal.send("n")
        terminal.wait("Second page only")
        assert "Ready terminal task" not in terminal.screen
        terminal.send("n")
        terminal.pump(0.2)
        assert len(requests) == 4, "no continuation must not repeat/walk a page"
        terminal.send("r")
        terminal.wait("Ready terminal task")
        assert parse_qs(urlsplit(requests[-1][1]).query) == {"limit": ["50"]}
        terminal.quit()


@pytest.mark.parametrize("status", [401, 403, 404, 503])
def test_fresh_failure_clears_private_detail_and_never_prints_reflected_body(status):
    reads = Reads()
    with (
        socket_peer(reads) as (origin, requests),
        Terminal(origin, TOKEN, "--plain") as terminal,
    ):
        open_ready(terminal)
        terminal.send("\r")
        terminal.wait(SECRET)
        reads.overrides[TASK_PATH] = lambda _: denial(status)
        terminal.send("r")
        terminal.wait("Unavailable" if status == 503 else "Denied")
        assert SECRET not in terminal.screen
        assert TOKEN.encode() not in terminal.raw
        assert b"\x1b]52;c;" not in terminal.raw
        before = len(requests)
        if status == 401:
            terminal.send("g\tnr\r")
            terminal.pump(0.2)
            assert len(requests) == before, "auth-failed session retried automatically"
        terminal.quit()


@pytest.mark.parametrize(
    "field,replacement", [("task_id", OTHER_TASK), ("project_id", OTHER_PROJECT)]
)
def test_fresh_task_identity_substitution_is_not_rendered(field, replacement):
    reads = Reads()
    reads.task = reads.task | {
        field: replacement,
        "description": "SUBSTITUTED_PRIVATE_CONTENT",
    }
    with (
        socket_peer(reads) as (origin, _),
        Terminal(origin, TOKEN, "--plain") as terminal,
    ):
        open_ready(terminal)
        terminal.send("\r")
        terminal.wait("Unavailable")
        assert "SUBSTITUTED_PRIVATE_CONTENT" not in terminal.screen
        terminal.quit()


@pytest.mark.parametrize("second_denied", [False, True])
def test_late_project_success_cannot_replace_current_project_or_resurrect_denial(
    second_denied,
):
    reads = Reads()
    reads.projects["items"].append(
        PROJECT_ROW | {"project_id": OTHER_PROJECT, "name": "Second project"}
    )
    started, release, finished = Event(), Event(), Event()

    def delayed(_):
        started.set()
        assert release.wait(10), "test failed to release held HTTP response"
        finished.set()
        return 200, reads.ready | {"items": [READY | {"title": "STALE_PROJECT_SECRET"}]}

    reads.overrides[READY_PATH] = delayed
    reads.overrides[f"/api/v1/projects/{OTHER_PROJECT}/tasks/ready"] = lambda _: (
        denial()
        if second_denied
        else (
            200,
            page(READY | {"project_id": OTHER_PROJECT, "title": "Current project row"})
            | {"project_id": OTHER_PROJECT},
        )
    )
    with (
        socket_peer(reads) as (origin, _),
        Terminal(origin, TOKEN, "--plain") as terminal,
    ):
        try:
            terminal.wait("Terminal project")
            terminal.send("\r")
            assert started.wait(5)
            terminal.send("g")
            terminal.wait("Second project")
            terminal.send("\x1b[B\r")
            terminal.wait("Denied" if second_denied else "Current project row")
            release.set()
            assert finished.wait(5)
            terminal.pump(0.3)
            assert "STALE_PROJECT_SECRET" not in terminal.screen
            assert (
                "Denied" if second_denied else "Current project row"
            ) in terminal.screen
            terminal.quit()
        finally:
            release.set()


@pytest.mark.parametrize(
    "surface,field",
    [
        ("submission", "id"),
        ("submission", "task_id"),
        ("context", "contribution_policy_version_id"),
        ("context", "guide_project"),
        ("intake", "task_id"),
        ("intake", "project_id"),
        ("intake", "guide_version"),
    ],
)
def test_detail_sections_refuse_cross_resource_and_locked_lineage_substitution(
    surface, field
):
    reads = Reads()
    if surface == "submission":
        reads.submission[field] = OTHER_TASK
        reads.submission["summary"] = "SUBSTITUTED_PRIVATE_CONTENT"
    elif surface == "context":
        if field == "guide_project":
            reads.context["guide"]["project_id"] = OTHER_PROJECT
        else:
            reads.context[field] = OTHER_TASK
        reads.context["guide"]["change_summary"] = "SUBSTITUTED_PRIVATE_CONTENT"
    else:
        reads.requirements[field] = (
            "wrong-guide" if field == "guide_version" else OTHER_TASK
        )
        reads.requirements["attestation_terms"] = ["SUBSTITUTED_PRIVATE_CONTENT"]
    with (
        socket_peer(reads) as (origin, _),
        Terminal(origin, TOKEN, "--plain") as terminal,
    ):
        open_ready(terminal)
        terminal.send("\t")
        terminal.wait("Assigned terminal task")
        if surface == "submission":
            terminal.send("\t")
            terminal.wait("Owned terminal attempt")
            terminal.send("\r")
        else:
            terminal.send("\r")
            terminal.wait(SECRET)
            terminal.send("\t")
            if surface == "intake":
                terminal.wait("guide-1")
                terminal.send("\t")
        terminal.wait("Unavailable")
        assert "SUBSTITUTED_PRIVATE_CONTENT" not in terminal.screen
        assert SECRET not in terminal.screen
        terminal.quit()


@pytest.mark.parametrize(
    "columns,rows,args,extra",
    [
        (120, 40, (), {}),
        (80, 24, (), {"NO_COLOR": "1"}),
        (60, 18, ("--plain",), {}),
    ],
)
def test_hostile_text_resizing_plain_and_ctrl_c_restore_terminal(
    columns, rows, args, extra
):
    reads = Reads()
    reads.projects["items"][0]["name"] = "Terminal" + HOSTILE
    reads.task["description"] = SECRET + HOSTILE
    with (
        socket_peer(reads) as (origin, requests),
        Terminal(
            origin, TOKEN, *args, columns=columns, rows=rows, extra_env=extra
        ) as terminal,
    ):
        open_ready(terminal, "Terminal")
        terminal.send("\r")
        terminal.wait(SECRET)
        before = len(requests)
        terminal.resize(80, 24)
        terminal.wait(SECRET)
        assert TASK in terminal.screen
        assert len(requests) == before
        for forbidden in (
            b"\x1b]52;c;",
            b"\x1b]8;;https://evil",
            b"\x1b[31m",
            "\u202e".encode(),
            "\u2066".encode(),
            b"\xc2\x85",
            "\u2028".encode(),
        ):
            assert forbidden not in terminal.raw
        assert TOKEN.encode() not in terminal.raw
        if args:
            assert b"\x1b[?1049h" not in terminal.raw
        if args or extra:
            assert not re.search(
                rb"\x1b\[[0-9;]*(?:3[0-9]|4[0-9]|[34]8)[0-9;]*m", terminal.raw
            )
        terminal.quit(b"\x03")


@pytest.mark.parametrize("surface", ["profile", "project", "task"])
def test_reflected_bearer_in_success_body_is_never_displayed(surface):
    reads = Reads()
    if surface == "profile":
        reads.overrides["/api/v1/actors/me"] = lambda _: (
            200,
            PROFILE | {"display_name": TOKEN},
        )
    elif surface == "project":
        reads.projects["items"][0]["name"] += TOKEN
    else:
        reads.task["description"] += TOKEN
    with (
        socket_peer(reads) as (origin, _),
        Terminal(origin, TOKEN, "--plain") as terminal,
    ):
        if surface == "task":
            open_ready(terminal)
            terminal.send("\r")
        terminal.wait(
            {
                "profile": "Terminal project",
                "project": "Unavailable",
                "task": "[redacted]",
            }[surface]
        )
        assert TOKEN.encode() not in terminal.raw
        if surface != "task":
            assert SECRET not in terminal.screen
        terminal.quit()


def test_too_small_terminal_makes_no_requests_until_usable_resize():
    reads = Reads()
    with (
        socket_peer(reads) as (origin, requests),
        Terminal(origin, TOKEN, "--plain", columns=30, rows=8) as terminal,
    ):
        terminal.wait("Resize")
        terminal.pump(0.2)
        assert requests == []
        terminal.resize(80, 24)
        terminal.wait("Terminal project")
        terminal.quit()


def test_invalid_configuration_leaves_interactive_terminal_untouched():
    with (
        socket_peer(Reads()) as (origin, requests),
        Terminal(
            origin,
            TOKEN,
            extra_env={"WORKSTREAM_API_URL": "http://user:private-origin@127.0.0.1"},
        ) as terminal,
    ):
        terminal.wait_exit(expected=2)
        assert requests == []
        assert b"\x1b" not in terminal.raw
        assert b"private-origin" not in terminal.raw
        assert TOKEN.encode() not in terminal.raw


def test_quit_while_http_read_is_pending_restores_terminal_without_late_redraw():
    reads = Reads()
    started, release = Event(), Event()

    def delayed(_):
        started.set()
        assert release.wait(10)
        return 200, reads.ready

    reads.overrides[READY_PATH] = delayed
    with socket_peer(reads) as (origin, _), Terminal(origin, TOKEN) as terminal:
        try:
            terminal.wait("Terminal project")
            terminal.send("\r")
            assert started.wait(5)
            terminal.quit()
            output_at_exit = bytes(terminal.raw)
            release.set()
            terminal.pump(0.2)
            assert bytes(terminal.raw) == output_at_exit
        finally:
            release.set()


def test_manual_handoffs_name_existing_commands_without_invoking_them(cli):
    with socket_peer(Reads()) as (origin, requests):
        for args in (
            ("task", "show"),
            ("task", "context"),
            ("task", "requirements"),
            ("me", "assignments"),
            ("me", "submissions"),
            ("submission", "show"),
            ("submission", "findings"),
            ("contributions",),
        ):
            result = cli(origin, TOKEN, *args, "--help")
            assert result.returncode == 0 and result.stderr == ""
            assert "Usage:" in result.stdout
        assert requests == []


def test_redirected_input_output_and_json_are_rejected_without_network(cli):
    with socket_peer(Reads()) as (origin, requests):
        result = cli(origin, TOKEN, "tui")
        assert result.returncode == 2 and "\x1b" not in result.stdout + result.stderr
        result = cli(origin, TOKEN, "tui", "--output", "json")
        assert result.returncode == 2 and result.stdout == ""
        assert "invalid_output" in result.stderr
        if os.name == "posix":
            import pty
            import termios

            master, slave = pty.openpty()
            original = termios.tcgetattr(slave)
            try:
                for redirect_input in (False, True):
                    result = subprocess.run(  # noqa: S603 - built binary, fixed argv
                        [executable(), "tui"],
                        stdin=subprocess.DEVNULL if redirect_input else slave,
                        stdout=slave if redirect_input else subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=environment(origin, TOKEN),
                        timeout=10,
                        check=False,
                    )
                    assert result.returncode == 2
                    assert termios.tcgetattr(slave) == original
            finally:
                os.close(master)
                os.close(slave)
        assert requests == []
