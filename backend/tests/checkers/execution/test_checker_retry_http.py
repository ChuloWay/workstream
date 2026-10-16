"""Focused HTTP and public-port boundaries for Operator checker recovery."""

from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient
import pytest

from app.api.deps import checker_recovery as checker_recovery_deps
from app.api.deps.api_controls import (
    enforce_admin_mutation_rate_limit,
    enforce_authorization_read_rate_limit,
)
from app.api.deps.authorization import get_authorization_actor
from app.api.deps.checker_recovery import (
    get_checker_retry_commands,
    get_checker_retry_reads,
    require_checker_retry_human,
)
from app.core.api_controls import StructuredHTTPException
from app.core.config import Settings
from app.core.identifiers import new_record_id
from app.db.session import get_db_session
from app.main import create_app
from app.modules.checkers.api.execution import (
    CheckerRetryOperationUnavailable,
    CheckerRetrySource,
)
from app.modules.checkers.checker_retry import _append_retry_event
from app.modules.outbox.api import (
    OutboxIdempotencyConflict,
    OutboxInputError,
    OutboxPersistenceError,
)


@pytest.mark.parametrize(
    ("method", "path", "rate_dependency", "operation_dependency", "request_kwargs"),
    (
        (
            "GET",
            f"/api/v1/operations/projects/{new_record_id()}/checker-retry-sources",
            enforce_authorization_read_rate_limit,
            get_checker_retry_reads,
            {},
        ),
        (
            "POST",
            f"/api/v1/operations/projects/{new_record_id()}"
            f"/checker-runs/{new_record_id()}/retry",
            enforce_admin_mutation_rate_limit,
            get_checker_retry_commands,
            {
                "headers": {"Idempotency-Key": str(new_record_id())},
                "json": {"reason": "Restore verified checker infrastructure"},
            },
        ),
    ),
)
async def test_recovery_rate_gates_precede_auth_and_checker_lookup(
    method, path, rate_dependency, operation_dependency, request_kwargs,
):
    app = create_app(Settings(environment="test"))
    calls = []

    async def refuse_rate():
        calls.append("rate")
        raise StructuredHTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            error_code="rate_limit_exceeded",
            error_message="Rate limit exceeded",
            retryable=True,
            headers={"Retry-After": "1"},
        )

    async def forbidden_recovery_lookup():
        calls.append("recovery")
        raise AssertionError("AUTH and CHECKERS lookup must not run")

    app.dependency_overrides[rate_dependency] = refuse_rate
    app.dependency_overrides[operation_dependency] = forbidden_recovery_lookup
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver",
    ) as client:
        response = await client.request(method, path, **request_kwargs)

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "1"
    assert response.json()["error"]["code"] == "rate_limit_exceeded"
    assert calls == ["rate"]


async def test_recovery_internal_unavailability_rolls_back_and_returns_retryable_503(
    monkeypatch,
):
    class Session:
        def __init__(self):
            self.rollbacks = 0
            self.commits = 0

        async def rollback(self):
            self.rollbacks += 1

        async def commit(self):
            self.commits += 1

        def in_transaction(self):
            return False

    class Service:
        async def retry(self, _command):
            raise CheckerRetryOperationUnavailable(
                "checker_retry_reservation_unavailable"
            )

    session = Session()
    service = Service()
    actor_id, link_id = new_record_id(), new_record_id()
    resolved = SimpleNamespace(
        profile=SimpleNamespace(
            id=str(actor_id), status="active", actor_kind="human",
            service_identity=None,
        ),
        identity_link=SimpleNamespace(id=str(link_id), status="active"),
    )
    app = create_app(Settings(environment="test"))
    app.dependency_overrides[enforce_admin_mutation_rate_limit] = lambda: None
    app.dependency_overrides[require_checker_retry_human] = lambda: None
    app.dependency_overrides[get_authorization_actor] = lambda: resolved
    app.dependency_overrides[get_db_session] = lambda: session
    monkeypatch.setattr(
        checker_recovery_deps,
        "checker_retry_service",
        lambda *_args, **_kwargs: service,
    )
    path = (
        f"/api/v1/operations/projects/{new_record_id()}"
        f"/checker-runs/{new_record_id()}/retry"
    )
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            path,
            headers={"Idempotency-Key": str(new_record_id())},
            json={"reason": "Restore verified checker infrastructure"},
        )

    assert response.status_code == 503
    assert response.json()["error"] | {"correlation_id": "redacted"} == {
        "code": "checker_recovery_unavailable",
        "message": "Checker recovery unavailable",
        "details": {},
        "correlation_id": "redacted",
        "retryable": True,
    }
    assert session.rollbacks == 2
    assert session.commits == 0


@pytest.mark.parametrize(
    "error_type",
    (OutboxIdempotencyConflict, OutboxInputError, OutboxPersistenceError),
)
async def test_retry_translates_exact_outbox_failures(error_type):
    class Events:
        async def append(self, _event):
            raise error_type("private outbox detail")

    source = CheckerRetrySource(
        project_id=new_record_id(), task_id=new_record_id(),
        assignment_id=new_record_id(), submission_id=new_record_id(),
        submission_version=1, source_run_id=new_record_id(),
        source_request_id=new_record_id(),
        source_request_digest="sha256:" + "0" * 64,
        source_result_id=new_record_id(),
        source_result_digest="sha256:" + "1" * 64,
        source_finalize_evidence_id=new_record_id(), source_generation=1,
        failure_code="material_unavailable",
    )
    with pytest.raises(
        CheckerRetryOperationUnavailable,
        match="checker_retry_outbox_unavailable",
    ) as raised:
        await _append_retry_event(
            Events(), source, receipt_id=new_record_id(),
            request_id=new_record_id(), request_digest="sha256:" + "2" * 64,
            run_id=new_record_id(), result_id=new_record_id(),
        )
    assert isinstance(raised.value.__cause__, error_type)
