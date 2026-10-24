"""GitHub App facts adapter: facts, bounded retries and credential custody."""

from __future__ import annotations

import hashlib
import json
import logging
import traceback

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.adapters.github import github_facts_adapter_factory
from app.adapters.github.app_facts import (
    GitHubAppFactsAdapter,
    GitHubAppFactsConfiguration,
    _InstallationToken,
)
from app.core.config import Settings
from app.interfaces.external_services import (
    ExternalServiceAdapterError,
    ExternalServiceConfigurationError,
)
from app.interfaces.github_facts import (
    GitHubFactsAccessDeniedError,
    GitHubFactsProtocolError,
    GitHubFactsUnavailableError,
    GitHubPullRequestFacts,
    GitHubPullRequestNotFoundError,
    GitHubRequiredChecksNotConfiguredError,
)

API = "https://api.github.test"
REPOSITORY = "acme/widgets"
HEAD_SHA = "a" * 40
MERGE_SHA = "b" * 40
TOKEN = "ghs_installationTokenSecretValue0001"
SECOND_TOKEN = "ghs_installationTokenSecretValue0002"
NOW = 1_800_000_000.0
APP_ID = 4242

PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_PEM = PRIVATE_KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
PEM_BODY_LINE = PRIVATE_PEM.splitlines()[1]
# Throwaway key generated per test run; no real key exists in the repository.


def _pull(**changes: object) -> dict:
    body = {
        "number": 12,
        "state": "closed",
        "merged": True,
        "merge_commit_sha": MERGE_SHA,
        "base": {"ref": "main", "repo": {"full_name": REPOSITORY}},
        "head": {"sha": HEAD_SHA},
    }
    body.update(changes)
    return body


class FakeGitHub:
    """Route-table GitHub fake that records every request it receives."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.bodies: dict[str, bytes] = {}
        self.tokens = [TOKEN, SECOND_TOKEN]
        self.routes: dict[tuple[str, str], list] = {}
        self.route("GET", f"/repos/{REPOSITORY}/installation", {"id": 77})
        self.route("POST", "/app/installations/77/access_tokens", self._token)
        self.route("GET", f"/repos/{REPOSITORY}/pulls/12", _pull())
        self.route(
            "GET",
            f"/repos/{REPOSITORY}/branches/main/protection/required_status_checks",
            {
                "strict": True,
                "contexts": ["backend", "lint"],
                "checks": [
                    {"context": "backend", "app_id": 15368},
                    {"context": "lint", "app_id": None},
                ],
            },
        )
        self.route(
            "GET",
            f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs",
            {
                "total_count": 1,
                "check_runs": [
                    {
                        "id": 10,
                        "name": "backend",
                        "status": "completed",
                        "conclusion": "success",
                        "app": {"id": 15368},
                    }
                ],
            },
        )
        self.route(
            "GET",
            f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/status",
            {"state": "success", "statuses": [{"id": 21, "context": "lint", "state": "success"}]},
        )

    def route(self, method: str, path: str, *responses: object) -> None:
        """Queue responses; the last one repeats once the queue is exhausted."""
        self.routes[(method, path)] = list(responses)

    def _token(self, _request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={"token": self.tokens.pop(0), "expires_at": "2027-01-15T09:00:00Z"},
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        queue = self.routes.get((request.method, request.url.path))
        if queue is None:
            return httpx.Response(404, json={"message": "Not Found"})
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        if callable(item):
            response = item(request)
        elif isinstance(item, httpx.Response):
            response = item
        else:
            response = httpx.Response(200, json=item)
        self.bodies[str(request.url)] = response.content
        return response

    def secrets(self) -> list[str]:
        """Every credential the adapter sent, plus the issued tokens."""
        sent = [
            request.headers["authorization"].removeprefix("Bearer ")
            for request in self.requests
            if "authorization" in request.headers
        ]
        return [*sent, TOKEN, SECOND_TOKEN, PEM_BODY_LINE]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _adapter(
    fake: FakeGitHub,
    clock: Clock | None = None,
    *,
    installation_id: int | None = None,
    deadline: float = 45.0,
    attempts: int = 3,
) -> GitHubAppFactsAdapter:
    clock = clock or Clock()
    return GitHubAppFactsAdapter(
        GitHubAppFactsConfiguration(
            app_id=APP_ID,
            installation_id=installation_id,
            api_base_url=API,
            request_timeout_seconds=10.0,
            total_deadline_seconds=deadline,
            maximum_attempts=attempts,
        ),
        PRIVATE_KEY,
        transport=httpx.MockTransport(fake.handler),
        wall_clock=lambda: NOW,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )


async def _fetch(adapter: GitHubAppFactsAdapter) -> GitHubPullRequestFacts:
    return await adapter.fetch_pull_request_facts(repository=REPOSITORY, pull_request_number=12)


def _sha(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


async def test_happy_path_returns_facts_with_response_digests() -> None:
    fake = FakeGitHub()
    facts = await _fetch(_adapter(fake))

    assert facts.model_dump(mode="json") == {
        "schema_version": "workstream.github_facts.v1",
        "repository": REPOSITORY,
        "pull_request_number": 12,
        "state": "closed",
        "merged": True,
        "merge_commit_sha": MERGE_SHA,
        "base_ref": "main",
        "head_sha": HEAD_SHA,
        "required_checks": [
            {"name": "backend", "app_id": 15368, "conclusion": "success"},
            {"name": "lint", "app_id": None, "conclusion": "success"},
        ],
        "fetched_at": "2027-01-15T08:00:00Z",
        "responses": [
            {
                "request": "pull_request",
                "sha256": _sha(fake.bodies[f"{API}/repos/{REPOSITORY}/pulls/12"]),
            },
            {
                "request": "required_status_checks",
                "sha256": _sha(
                    fake.bodies[
                        f"{API}/repos/{REPOSITORY}/branches/main/protection/"
                        "required_status_checks"
                    ]
                ),
            },
            {
                "request": "check_runs.page.1",
                "sha256": _sha(
                    fake.bodies[
                        f"{API}/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs?per_page=100"
                    ]
                ),
            },
            {
                "request": "commit_status.page.1",
                "sha256": _sha(
                    fake.bodies[f"{API}/repos/{REPOSITORY}/commits/{HEAD_SHA}/status?per_page=100"]
                ),
            },
        ],
    }
    lookup, exchange, *facts_requests = fake.requests
    claims = jwt.decode(
        lookup.headers["authorization"].removeprefix("Bearer "),
        PRIVATE_KEY.public_key(),
        algorithms=["RS256"],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert claims == {"iss": str(APP_ID), "iat": int(NOW) - 60, "exp": int(NOW) + 540}
    assert json.loads(exchange.content) == {"repositories": ["widgets"]}
    assert {request.headers["authorization"] for request in facts_requests} == {
        f"Bearer {TOKEN}"
    }
    assert all(request.headers["x-github-api-version"] for request in fake.requests)


async def test_installation_token_is_cached_per_repository_until_refresh() -> None:
    fake = FakeGitHub()
    adapter = _adapter(fake, installation_id=77)
    await _fetch(adapter)
    await _fetch(adapter)

    paths = [request.url.path for request in fake.requests]
    assert paths.count("/app/installations/77/access_tokens") == 1
    assert f"/repos/{REPOSITORY}/installation" not in paths


async def test_pagination_follows_same_origin_next_links() -> None:
    fake = FakeGitHub()
    runs_path = f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs"
    page_two = f"{API}{runs_path}?per_page=100&page=2"
    fake.route(
        "GET",
        runs_path,
        httpx.Response(
            200,
            json={
                "check_runs": [
                    {"id": 4, "name": "other", "status": "completed", "conclusion": "failure"}
                ]
            },
            headers={"link": f'<{page_two}>; rel="next"'},
        ),
        {
            "check_runs": [
                {
                    "id": 11,
                    "name": "backend",
                    "status": "completed",
                    "conclusion": "failure",
                    "app": {"id": 15368},
                }
            ]
        },
    )
    facts = await _fetch(_adapter(fake))

    assert facts.required_checks[0].conclusion == "failure"
    assert [item.request for item in facts.responses][2:4] == [
        "check_runs.page.1",
        "check_runs.page.2",
    ]


async def test_pagination_refuses_a_foreign_origin_link() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs",
        httpx.Response(
            200,
            json={"check_runs": []},
            headers={"link": '<https://attacker.test/collect?page=2>; rel="next"'},
        ),
    )
    with pytest.raises(GitHubFactsProtocolError):
        await _fetch(_adapter(fake))
    assert all(request.url.host == "api.github.test" for request in fake.requests)


async def test_required_check_conclusions_fail_closed() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/branches/main/protection/required_status_checks",
        {"contexts": ["backend", "lint", "docs", "e2e", "wrong-app"], "checks": []},
    )
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs",
        {
            "check_runs": [
                {"id": 1, "name": "backend", "status": "completed", "conclusion": "success"},
                {"id": 2, "name": "e2e", "status": "in_progress", "conclusion": None},
                {"id": 3, "name": "wrong-app", "status": "completed", "conclusion": "skipped"},
            ]
        },
    )
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/status",
        {
            "statuses": [
                {"id": 23, "context": "backend", "state": "failure"},
                {"id": 24, "context": "lint", "state": "error"},
            ]
        },
    )
    facts = await _fetch(_adapter(fake))

    assert {item.name: item.conclusion for item in facts.required_checks} == {
        "backend": "failure",
        "docs": "missing",
        "e2e": "pending",
        "lint": "error",
        "wrong-app": "skipped",
    }


@pytest.mark.parametrize(
    ("older", "newer", "expected"),
    [("failure", "success", "success"), ("success", "failure", "failure")],
    ids=("rerun-passed", "rerun-failed"),
)
async def test_only_the_latest_rerun_of_a_required_check_counts(
    older: str, newer: str, expected: str
) -> None:
    fake = FakeGitHub()
    runs_path = f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs"
    run = {"name": "backend", "status": "completed", "app": {"id": 15368}}
    # The newer run is on the first page and the older on the second, so
    # response order cannot decide the result.
    fake.route(
        "GET",
        runs_path,
        httpx.Response(
            200,
            json={"check_runs": [{**run, "id": 900, "conclusion": newer}]},
            headers={"link": f'<{API}{runs_path}?per_page=100&page=2>; rel="next"'},
        ),
        {"check_runs": [{**run, "id": 899, "conclusion": older}]},
    )
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/status",
        {
            "statuses": [
                {"id": 31, "context": "lint", "state": "failure"},
                {"id": 32, "context": "lint", "state": "success"},
            ]
        },
    )
    facts = await _fetch(_adapter(fake))
    assert {item.name: item.conclusion for item in facts.required_checks} == {
        "backend": expected,
        "lint": "success",
    }


async def test_required_checks_are_the_union_of_checks_and_contexts() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/branches/main/protection/required_status_checks",
        {
            "contexts": ["backend", "docs"],
            "checks": [{"context": "backend", "app_id": 15368}, {"context": "lint", "app_id": -1}],
        },
    )
    facts = await _fetch(_adapter(fake))
    assert [(item.name, item.app_id, item.conclusion) for item in facts.required_checks] == [
        ("backend", 15368, "success"),
        ("docs", None, "missing"),
        ("lint", None, "success"),
    ]


async def test_app_restricted_check_ignores_other_apps_and_statuses() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/check-runs",
        {
            "check_runs": [
                {
                    "id": 12,
                    "name": "backend",
                    "status": "completed",
                    "conclusion": "success",
                    "app": {"id": 999},
                }
            ]
        },
    )
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/commits/{HEAD_SHA}/status",
        {"statuses": [{"id": 22, "context": "backend", "state": "success"}, {"id": 21, "context": "lint", "state": "success"}]},
    )
    facts = await _fetch(_adapter(fake))
    assert facts.required_checks[0].conclusion == "missing"


async def test_unmerged_pull_request_reports_no_merge_commit() -> None:
    fake = FakeGitHub()
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", _pull(state="open", merged=False))
    facts = await _fetch(_adapter(fake))
    assert (facts.state, facts.merged, facts.merge_commit_sha) == ("open", False, None)


@pytest.mark.parametrize(
    "protection",
    [
        httpx.Response(404, json={"message": "Branch not protected"}),
        {"contexts": [], "checks": []},
    ],
    ids=("not-protected", "no-required-checks"),
)
async def test_missing_required_checks_fail_closed(protection: object) -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/branches/main/protection/required_status_checks",
        protection,
    )
    with pytest.raises(GitHubRequiredChecksNotConfiguredError) as caught:
        await _fetch(_adapter(fake))
    assert caught.value.retryable is False


async def test_unknown_pull_request_is_not_found() -> None:
    fake = FakeGitHub()
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", httpx.Response(404))
    with pytest.raises(GitHubPullRequestNotFoundError):
        await _fetch(_adapter(fake))


async def test_pull_request_from_another_repository_is_rejected() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12",
        _pull(base={"ref": "main", "repo": {"full_name": "acme/other"}}),
    )
    with pytest.raises(GitHubFactsProtocolError):
        await _fetch(_adapter(fake))


async def test_server_error_is_retried_then_succeeds() -> None:
    fake = FakeGitHub()
    clock = Clock()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12",
        httpx.Response(502),
        httpx.ConnectError("connection refused"),
        _pull(),
    )
    facts = await _fetch(_adapter(fake, clock))
    assert facts.merged is True
    assert clock.sleeps == [0.5, 1.0]


async def test_retries_exhausted_raise_facts_unavailable() -> None:
    fake = FakeGitHub()
    clock = Clock()
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", httpx.Response(503))
    with pytest.raises(GitHubFactsUnavailableError) as caught:
        await _fetch(_adapter(fake, clock))
    pulls = [r for r in fake.requests if r.url.path.endswith("/pulls/12")]
    assert len(pulls) == 3
    assert clock.sleeps == [0.5, 1.0]
    assert caught.value.retryable is True


async def test_total_deadline_bounds_retries() -> None:
    fake = FakeGitHub()
    clock = Clock()
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", httpx.Response(500))
    with pytest.raises(GitHubFactsUnavailableError):
        await _fetch(_adapter(fake, clock, deadline=1.0, attempts=5))
    assert sum(clock.sleeps) < 1.0


async def test_rate_limit_waits_for_reset_within_the_deadline() -> None:
    fake = FakeGitHub()
    clock = Clock()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12",
        httpx.Response(
            403,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": str(int(NOW) + 7)},
        ),
        httpx.Response(429, headers={"retry-after": "3"}),
        _pull(),
    )
    facts = await _fetch(_adapter(fake, clock))
    assert facts.merged is True
    assert clock.sleeps == [7.0, 3.0]


async def test_rate_limit_beyond_the_deadline_fails_without_waiting() -> None:
    fake = FakeGitHub()
    clock = Clock()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/pulls/12",
        httpx.Response(429, headers={"retry-after": "3600"}),
    )
    with pytest.raises(GitHubFactsUnavailableError):
        await _fetch(_adapter(fake, clock))
    assert clock.sleeps == []


async def test_forbidden_without_rate_limit_is_access_denied() -> None:
    fake = FakeGitHub()
    fake.route(
        "GET",
        f"/repos/{REPOSITORY}/branches/main/protection/required_status_checks",
        httpx.Response(403, json={"message": "Resource not accessible by integration"}),
    )
    with pytest.raises(GitHubFactsAccessDeniedError):
        await _fetch(_adapter(fake))


async def test_rejected_cached_token_is_refreshed_once() -> None:
    fake = FakeGitHub()
    adapter = _adapter(fake, installation_id=77)
    await _fetch(adapter)
    fake.route("GET", f"/repos/{REPOSITORY}/pulls/12", httpx.Response(401), _pull())
    await _fetch(adapter)
    exchanges = [r for r in fake.requests if r.url.path.endswith("/access_tokens")]
    assert len(exchanges) == 2
    assert fake.requests[-1].headers["authorization"] == f"Bearer {SECOND_TOKEN}"


@pytest.mark.parametrize(
    ("repository", "number"),
    [("acme", 12), ("acme/../x", 12), ("acme/widgets/extra", 12), (REPOSITORY, 0)],
)
async def test_invalid_request_is_refused_before_any_network_call(
    repository: str, number: int
) -> None:
    fake = FakeGitHub()
    with pytest.raises(ExternalServiceConfigurationError):
        await _adapter(fake).fetch_pull_request_facts(
            repository=repository, pull_request_number=number
        )
    assert fake.requests == []


def _assert_secret_free(text: str, secrets: list[str]) -> None:
    for secret in secrets:
        assert secret not in text


@pytest.mark.parametrize(
    "failure",
    ["unavailable", "access_denied", "not_found", "protocol", "token_exchange_denied"],
)
async def test_credentials_never_reach_errors_logs_or_reprs(
    failure: str, caplog: pytest.LogCaptureFixture
) -> None:
    fake = FakeGitHub()
    pulls = f"/repos/{REPOSITORY}/pulls/12"
    if failure == "unavailable":
        fake.route("GET", pulls, httpx.ConnectError(f"refused Bearer {TOKEN}"))
    elif failure == "access_denied":
        fake.route("GET", pulls, httpx.Response(401))
    elif failure == "not_found":
        fake.route("GET", pulls, httpx.Response(404))
    elif failure == "protocol":
        fake.route("GET", pulls, httpx.Response(200, content=f"not json {TOKEN}".encode()))
    else:
        fake.route("POST", "/app/installations/77/access_tokens", httpx.Response(403))
    adapter = _adapter(fake)
    caplog.set_level(logging.DEBUG)

    with pytest.raises(ExternalServiceAdapterError) as caught:
        await _fetch(adapter)

    error = caught.value
    rendered = "".join(traceback.format_exception(error))
    assert error.__cause__ is None and error.__suppress_context__ is True
    log_text = "\n".join(
        f"{record.getMessage()} {record.args!r} {record.__dict__!r}" for record in caplog.records
    )
    secrets = fake.secrets()
    assert len(secrets) > 3
    for text in (str(error), repr(error), rendered, log_text, repr(adapter)):
        _assert_secret_free(text, secrets)


async def test_successful_facts_and_token_holder_are_secret_free(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake = FakeGitHub()
    caplog.set_level(logging.DEBUG)
    adapter = _adapter(fake)
    facts = await _fetch(adapter)
    secrets = fake.secrets()
    texts = [
        facts.model_dump_json(),
        repr(facts),
        repr(adapter),
        repr(_InstallationToken(TOKEN, NOW)),
        "\n".join(record.getMessage() for record in caplog.records),
    ]
    for text in texts:
        _assert_secret_free(text, secrets)


def _settings(**values: object) -> Settings:
    configured: dict[str, object] = {
        "environment": "test",
        "github_app_id": APP_ID,
        "github_app_private_key": PRIVATE_PEM,
        "github_api_base_url": API,
    }
    configured.update(values)
    return Settings(_env_file=None, **configured)


async def test_factory_registers_the_github_app_provider() -> None:
    fake = FakeGitHub()
    factory = github_facts_adapter_factory(
        _settings(github_app_installation_id=77),
        transport=httpx.MockTransport(fake.handler),
    )
    adapter = factory.create("github_app")
    assert (adapter.identity.capability_key, adapter.identity.provider_key) == (
        "github_facts",
        "github_app",
    )
    facts = await _fetch(adapter)
    assert facts.repository == REPOSITORY


def test_factory_refuses_missing_or_unusable_credentials() -> None:
    unconfigured = Settings(_env_file=None, environment="test")
    with pytest.raises(ExternalServiceConfigurationError):
        github_facts_adapter_factory(unconfigured).create("github_app")
    unusable = "-----BEGIN PRIVATE KEY-----\nnot-a-key\n-----END PRIVATE KEY-----\n"
    with pytest.raises(ExternalServiceConfigurationError) as caught:
        github_facts_adapter_factory(_settings(github_app_private_key=unusable)).create(
            "github_app"
        )
    assert caught.value.__cause__ is None


def test_private_key_setting_is_redacted_and_accepts_escaped_newlines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    assert settings.github_app_private_key is not None
    assert settings.github_app_private_key.get_secret_value() == PRIVATE_PEM
    for text in (repr(settings), str(settings.model_dump()), settings.model_dump_json()):
        assert PEM_BODY_LINE not in text
    monkeypatch.setenv("WORKSTREAM_GITHUB_APP_PRIVATE_KEY", PRIVATE_PEM.replace("\n", "\\n"))
    from_environment = Settings(_env_file=None, environment="test", github_app_id=APP_ID)
    assert from_environment.github_app_private_key is not None
    assert from_environment.github_app_private_key.get_secret_value() == PRIVATE_PEM


def test_invalid_private_key_setting_error_omits_the_value() -> None:
    bogus = "not-a-pem-secret-value-0123456789"
    with pytest.raises(ValueError) as caught:
        _settings(github_app_private_key=bogus)
    assert bogus not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize(
    "values",
    [
        {"github_app_private_key": None},
        {"github_app_id": None},
        {"github_api_base_url": "http://api.github.example"},
        {"github_api_base_url": "https://user:pass@api.github.com"},
        {"github_api_base_url": "https://api.github.com/"},
        {"github_api_base_url": "http://127.0.0.1:8080", "environment": "production"},
        {"github_facts_total_deadline_seconds": 5.0},
        {"github_facts_total_deadline_seconds": 121.0},
    ],
)
def test_settings_reject_incomplete_or_unsafe_configuration(values: dict) -> None:
    with pytest.raises(ValueError):
        _settings(**values)


def test_settings_accept_loopback_http_only_for_local_and_test() -> None:
    settings = _settings(github_api_base_url="http://127.0.0.1:8080")
    assert settings.github_api_base_url == "http://127.0.0.1:8080"
