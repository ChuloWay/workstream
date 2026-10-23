"""Production-boundary PostgreSQL tests for hidden unified compilation."""

from __future__ import annotations

from tests.projects.guide_compilation.helpers import runtime_configuration

from app.modules.authorization.api import ProjectGuideCompilationRequestOrigin
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts import (
    guide_document_manifest_port,
)
from app.interfaces.project_agents import (
    ProjectAgentRuntimeError,
    ProjectGuideCompilationInvalidOutputError,
)
from app.modules.authorization.api import (
    ActorIdentityFacts,
    ActorKind,
    AuthorizationDenied,
    AuthorizationUnavailable,
)
from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.guide_compilation import (
    ProjectGuideCompilationAuthorizationAdapter,
)
from app.modules.authorization.prepared import fixed_service_prepared_authorization
from app.modules.authorization.runtime import PreparedAuthorizationUnsupported
from app.modules.projects.api import (
    ProjectGuideCompilationExecutionClassification,
    ProjectGuideCompilationExecutionCommand,
    ProjectGuideCompilationExecutionError,
)
from app.modules.projects.guide_compilation.orchestrator import (
    GuideCompilationOrchestrator,
    SqlAlchemyGuideCompilationExecutionBackend,
    project_guide_compilation_execution_port,
)
from tests.checkers.external.support import capability_projection

from .helpers import (
    context,
    generated_result,
    identity,
    manager_runtime_configuration,
    result,
    seed_database,
)
from .runtime_fixtures import document_access, record_scripted_document_access
from .test_authorized_request_service import _authorized_service, _request, _seed_human


class _Runtime:
    identity = runtime_configuration().adapter_identity

    def __init__(self, outcome=generated_result(), *, delay: float = 0) -> None:
        self.outcome = outcome
        self.delay = delay
        self.calls = 0

    def admit_execution(self):
        pass

    async def aclose(self):
        pass

    async def compile_project_guide(self, _context, capabilities):
        self.calls += 1
        await record_scripted_document_access(_context, capabilities)
        if self.delay:
            await asyncio.sleep(self.delay)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class _FailFirstPersist:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.failed = False

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def persist(self, state, compilation_context):
        if not self.failed:
            self.failed = True
            raise ProjectGuideCompilationExecutionError("storage_unavailable")
        return await self.inner.persist(state, compilation_context)


class _DelayedFence:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.waiting = asyncio.Event()
        self.release = asyncio.Event()

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def fence(self, state):
        self.waiting.set()
        await self.release.wait()
        return await self.inner.fence(state)


def _backend(factory):
    return SqlAlchemyGuideCompilationExecutionBackend(
        factory,
        material_factory=guide_document_manifest_port,
        document_access_factory=document_access,
        checker_capabilities=capability_projection(),
        authorization_context=_fixed_service_authorization,
    )


def _port(factory, runtime, *, checker_capabilities=None):
    return project_guide_compilation_execution_port(
        factory,
        material_factory=guide_document_manifest_port,
        document_access_factory=document_access,
        checker_capabilities=checker_capabilities or capability_projection(),
        authorization_context=_fixed_service_authorization,
        runtime_factory=lambda configuration: runtime,
    )


async def _authorized_attempt(database_url: str, values, configuration=None, *, compilation_context=None):
    actor_id, link_id, _grant_id = await _seed_human(database_url, values)
    actor = ActorIdentityFacts(actor_id, link_id, ActorKind.HUMAN)
    selected_context = compilation_context or context(values, configuration=configuration)
    selected_identity = identity(selected_context)
    request_facts = _request(values, configuration)
    if compilation_context is not None:
        request_facts = replace(
            request_facts,
            **{
                name: getattr(selected_identity, name)
                for name in type(selected_identity).model_fields
            },
        )
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            return await _authorized_service(session, actor).authorize_request(
                origin=ProjectGuideCompilationRequestOrigin(trigger="project_manager"),
                actor=actor,
                facts=request_facts,
                identity=selected_identity,
                runtime_configuration=configuration or runtime_configuration(),
            )
    finally:
        await engine.dispose()


@asynccontextmanager
async def _fixed_service_authorization(session, state):
    facts = state.preflight_facts
    try:
        async with fixed_service_prepared_authorization(
            session,
            service_identity=ServiceIdentity.PROJECT_SETUP,
            request_id=facts.operation_id,
            correlation_id=facts.attempt_id,
        ) as authority:
            await session.rollback()
            yield (
                ProjectGuideCompilationAuthorizationAdapter.from_prepared(authority.service),
                ActorIdentityFacts(
                    authority.actor_profile_id,
                    authority.identity_link_id,
                    ActorKind.SERVICE,
                    ServiceIdentity.PROJECT_SETUP.value,
                ),
            )
    except PreparedAuthorizationUnsupported as exc:
        raise AuthorizationDenied("compilation service authority denied") from exc


@asynccontextmanager
async def _unavailable_service_authorization(_session, _state):
    raise AuthorizationUnavailable("private database detail")
    yield  # pragma: no cover - required only to define an async context manager


@pytest.mark.asyncio
async def test_hidden_command_persists_one_complete_result_and_no_projections(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    runtime = _Runtime()
    try:
        port = _port(factory, runtime)
        receipt = await port.execute(
            ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
        )
        assert receipt.classification is ProjectGuideCompilationExecutionClassification.PERSISTED
        assert receipt.compilation_id is not None
        assert runtime.calls == 1
        async with factory() as session:
            counts = (
                await session.execute(
                    text(
                        "select "
                        "(select count(*) from project_guide_compilations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_compilation.request'),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_compilation.execute'),"
                        "(select count(*) from guide_sufficiency_reports),"
                        "(select count(*) from submission_artifact_policies),"
                        "(select count(*) from pre_submit_checker_policies),"
                        "(select count(*) from checker_policies),"
                        "(select count(*) from outbox_events)"
                    )
                )
            ).one()
            setup = (
                await session.execute(
                    text(
                        "select status,output_sufficiency_report_id,"
                        "output_submission_artifact_policy_id,"
                        "output_post_submit_checker_policy_id "
                        "from project_setup_runs where id=:id"
                    ),
                    {"id": str(values["setup_1"])},
                )
            ).one()
            await session.rollback()
        assert counts == (1, 1, 1, 0, 0, 0, 0, 0)
        assert setup == ("queued", None, None, None)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_commands_commit_one_dispatch_and_one_provider_call(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    runtime = _Runtime(delay=0.05)
    try:
        port = _port(factory, runtime)
        command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
        receipts = await asyncio.gather(port.execute(command), port.execute(command))
        assert runtime.calls == 1
        assert {receipt.classification for receipt in receipts} == {
            ProjectGuideCompilationExecutionClassification.PERSISTED,
            ProjectGuideCompilationExecutionClassification.PROVIDER_UNRESOLVED,
        }
        async with factory() as session:
            row = (
                await session.execute(
                    text(
                        "select count(*),(select count(*) from audit_events where "
                        "action_id='project.guide_compilation.execute') from "
                        "project_guide_compilations"
                    )
                )
            ).one()
            await session.rollback()
        assert row == (1, 1)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("winner_outcome", "expected_classification", "expected_compilations"),
    [
        (
            generated_result(),
            ProjectGuideCompilationExecutionClassification.PERSISTED,
            1,
        ),
        (
            ProjectGuideCompilationInvalidOutputError("schema_invalid"),
            ProjectGuideCompilationExecutionClassification.INVALID_TERMINAL,
            0,
        ),
    ],
)
async def test_loser_fencing_after_winner_converges_without_second_provider_call(
    clean_postgres_database: str,
    winner_outcome,
    expected_classification: ProjectGuideCompilationExecutionClassification,
    expected_compilations: int,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    backend = _backend(factory)
    delayed = _DelayedFence(backend)
    winner_runtime = _Runtime(winner_outcome)
    loser_runtime = _Runtime(ProjectAgentRuntimeError("must not run"))
    command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
    try:
        loser = asyncio.create_task(
            GuideCompilationOrchestrator(
                delayed,
                lambda configuration: loser_runtime,
            ).execute(command)
        )
        await delayed.waiting.wait()
        winner = await GuideCompilationOrchestrator(
            backend,
            lambda configuration: winner_runtime,
        ).execute(command)
        delayed.release.set()
        recovered = await loser

        assert winner.classification is expected_classification
        assert recovered == winner
        assert winner_runtime.calls == 1
        assert loser_runtime.calls == 0
        async with factory() as session:
            counts = (
                await session.execute(
                    text(
                        "select (select count(*) from project_guide_compilations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_compilation.execute')"
                    )
                )
            ).one()
            await session.rollback()
        assert counts == (expected_compilations, expected_compilations)
    finally:
        delayed.release.set()
        await engine.dispose()


@pytest.mark.asyncio
async def test_loser_persists_an_accepted_winner_without_second_provider_call(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    backend = _backend(factory)
    delayed = _DelayedFence(backend)
    winner_runtime = _Runtime()
    loser_runtime = _Runtime(ProjectAgentRuntimeError("must not run"))
    command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
    try:
        loser = asyncio.create_task(
            GuideCompilationOrchestrator(
                delayed,
                lambda configuration: loser_runtime,
            ).execute(command)
        )
        await delayed.waiting.wait()
        with pytest.raises(ProjectGuideCompilationExecutionError) as failure:
            await GuideCompilationOrchestrator(
                _FailFirstPersist(backend),
                lambda configuration: winner_runtime,
            ).execute(command)
        assert failure.value.code == "storage_unavailable"

        delayed.release.set()
        recovered = await loser

        assert recovered.classification is ProjectGuideCompilationExecutionClassification.PERSISTED
        assert recovered.compilation_id is not None
        assert winner_runtime.calls == 1
        assert loser_runtime.calls == 0
        async with factory() as session:
            counts = (
                await session.execute(
                    text(
                        "select (select count(*) from project_guide_compilations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_compilation.execute')"
                    )
                )
            ).one()
            await session.rollback()
        assert counts == (1, 1)
    finally:
        delayed.release.set()
        await engine.dispose()


@pytest.mark.asyncio
async def test_accepted_result_recovers_without_a_second_provider_call(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    first_runtime = _Runtime()
    backend = _backend(factory)
    failing = _FailFirstPersist(backend)
    command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
    try:
        with pytest.raises(ProjectGuideCompilationExecutionError) as failure:
            await GuideCompilationOrchestrator(
                failing,
                lambda configuration: first_runtime,
            ).execute(command)
        assert failure.value.code == "storage_unavailable"
        assert first_runtime.calls == 1

        recovery_runtime = _Runtime(ProjectAgentRuntimeError("must not run"))
        receipt = await GuideCompilationOrchestrator(
            backend,
            lambda configuration: recovery_runtime,
        ).execute(command)
        assert receipt.classification is ProjectGuideCompilationExecutionClassification.PERSISTED
        assert recovery_runtime.calls == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [
        ProjectGuideCompilationInvalidOutputError("schema_invalid"),
        ProjectGuideCompilationInvalidOutputError("unsafe_text"),
        generated_result().model_copy(update={"agent_version": "v2"}),
    ],
)
async def test_known_invalid_output_terminalizes_without_compilation(
    clean_postgres_database: str,
    outcome,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    runtime = _Runtime(outcome)
    command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
    try:
        port = _port(factory, runtime)
        receipt = await port.execute(command)
        replay = await port.execute(command)
        assert (
            receipt.classification
            is ProjectGuideCompilationExecutionClassification.INVALID_TERMINAL
        )
        assert replay == receipt
        assert runtime.calls == 1
        async with factory() as session:
            row = (
                await session.execute(
                    text(
                        "select status,failure_code,"
                        "(select count(*) from project_guide_compilations),"
                        "(select count(*) from audit_events where action_id="
                        "'project.guide_compilation.execute') "
                        "from project_guide_compilation_attempts where id=:id"
                    ),
                    {"id": requested.attempt_id},
                )
            ).one()
            await session.rollback()
        assert row[0] == "compilation_invalid_terminal"
        assert row[1] in {"schema_invalid", "unsafe_text"}
        assert row[2:] == (0, 0)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_uncertain_provider_failure_never_redispatches(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    runtime = _Runtime(ProjectAgentRuntimeError("transport failed"))
    command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
    try:
        port = _port(factory, runtime)
        first = await port.execute(command)
        second = await port.execute(command)
        assert first == second
        assert (
            first.classification
            is ProjectGuideCompilationExecutionClassification.PROVIDER_UNRESOLVED
        )
        assert runtime.calls == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_hosted_provider_fence_cannot_be_reopened(
    clean_postgres_database: str,
) -> None:
    """Only a provider-free attempt may return to reservation; hosted uncertainty is final."""
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        backend = _backend(factory)
        state = await backend.load(requested.attempt_id)
        assert (await backend.fence(state)).dispatch_permitted
        with pytest.raises(ProjectGuideCompilationExecutionError, match="context_unavailable"):
            await backend.release_provider_free(state)
        async with factory() as session, session.begin():
            with pytest.raises(DBAPIError, match="provider uncertainty timestamp is immutable"):
                await session.execute(text(
                    "update project_guide_compilation_attempts set status='compilation_reserved',"
                    "provider_uncertain_at=null where id=:id"), {"id": requested.attempt_id})
    finally:
        await engine.dispose()


class _ManagerRuntime(_Runtime):
    identity = manager_runtime_configuration().adapter_identity

    async def compile_project_guide(self, _context, capabilities):
        self.calls += 1
        raise self.outcome


@pytest.mark.asyncio
async def test_provider_free_transient_failure_reopens_the_attempt_for_retry(
    clean_postgres_database: str,
) -> None:
    """A provider-free attempt has no uncertain provider outcome, so delivery can retry it."""
    values = await seed_database(clean_postgres_database)
    configuration = manager_runtime_configuration()
    requested = await _authorized_attempt(clean_postgres_database, values, configuration)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
    transient = _ManagerRuntime(ProjectAgentRuntimeError("project guide document access failed"))
    try:
        with pytest.raises(ProjectGuideCompilationExecutionError, match="runtime_unavailable"):
            await _port(factory, transient).execute(command)
        async with factory() as session:
            row = (await session.execute(text(
                "select status,provider_uncertain_at from project_guide_compilation_attempts "
                "where id=:id"), {"id": requested.attempt_id})).one()
            await session.rollback()
        assert tuple(row) == ("compilation_reserved", None)
        invalid = _ManagerRuntime(ProjectGuideCompilationInvalidOutputError("schema_invalid"))
        retried = await _port(factory, invalid).execute(command)
        assert (
            retried.classification
            is ProjectGuideCompilationExecutionClassification.INVALID_TERMINAL
        )
        assert (transient.calls, invalid.calls) == (1, 1)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_provider_free_cancellation_reopens_the_attempt(
    clean_postgres_database: str,
) -> None:
    """Cancellation propagates, but never strands a provider-free attempt."""
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(
        clean_postgres_database, values, manager_runtime_configuration())
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
    try:
        with pytest.raises(asyncio.CancelledError):
            await _port(factory, _ManagerRuntime(asyncio.CancelledError())).execute(command)
        async with factory() as session:
            status = await session.scalar(text(
                "select status from project_guide_compilation_attempts where id=:id"),
                {"id": requested.attempt_id})
            await session.rollback()
        assert status == "compilation_reserved"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_recovery_reopens_only_a_stale_provider_free_fence(
    clean_postgres_database: str, monkeypatch,
) -> None:
    """A fence left by a crashed worker reopens after its run deadline, not before."""
    from datetime import UTC, datetime, timedelta

    from app.modules.projects.guide_compilation import orchestrator

    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(
        clean_postgres_database, values, manager_runtime_configuration())
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
    try:
        backend = _backend(factory)
        assert (await backend.fence(await backend.load(requested.attempt_id))).dispatch_permitted
        fresh = _ManagerRuntime(ProjectGuideCompilationInvalidOutputError("schema_invalid"))
        unresolved = await _port(factory, fresh).execute(command)
        assert (
            unresolved.classification
            is ProjectGuideCompilationExecutionClassification.PROVIDER_UNRESOLVED
        )
        assert fresh.calls == 0

        class _Later(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.now(tz or UTC) + timedelta(hours=3)

        monkeypatch.setattr(orchestrator, "datetime", _Later)
        stale = _ManagerRuntime(ProjectGuideCompilationInvalidOutputError("schema_invalid"))
        retried = await _port(factory, stale).execute(command)
        assert (
            retried.classification
            is ProjectGuideCompilationExecutionClassification.INVALID_TERMINAL
        )
        assert stale.calls == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_provider_free_run_ignores_the_hosted_prompt_limit(
    clean_postgres_database: str,
) -> None:
    """The prompt limit bounds a hosted model request; a provider-free run sends none."""
    from app.interfaces.project_agents import project_guide_compilation_prompt_bytes

    configuration = manager_runtime_configuration().model_copy(
        update={"maximum_manifest_bytes": 1024})
    values = await seed_database(clean_postgres_database)
    assert len(project_guide_compilation_prompt_bytes(
        context(values, configuration=configuration))) > 1024
    requested = await _authorized_attempt(clean_postgres_database, values, configuration)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    runtime = _ManagerRuntime(ProjectGuideCompilationInvalidOutputError("schema_invalid"))
    try:
        receipt = await _port(factory, runtime).execute(
            ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id))
        assert (
            receipt.classification
            is ProjectGuideCompilationExecutionClassification.INVALID_TERMINAL
        )
        assert runtime.calls == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_revoked_service_authority_is_bounded_before_provider_call(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    runtime = _Runtime()
    try:
        async with engine.begin() as connection:
            await connection.execute(text("alter table actor_identity_links disable trigger user"))
            await connection.execute(
                text(
                    "update actor_identity_links set status='revoked',revoked_by='test',"
                    "revoked_at=clock_timestamp(),revoked_reason='test revocation' "
                    "where id=:id"
                ),
                {"id": str(values["link"])},
            )
            await connection.execute(text("alter table actor_identity_links enable trigger user"))

        port = _port(factory, runtime)
        with pytest.raises(ProjectGuideCompilationExecutionError) as failure:
            await port.execute(
                ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
            )
        assert failure.value.code == "service_authority_denied"
        assert runtime.calls == 0
        async with factory() as session:
            row = (
                await session.execute(
                    text(
                        "select status,(select count(*) from audit_events where "
                        "action_id='project.guide_compilation.execute') "
                        "from project_guide_compilation_attempts where id=:id"
                    ),
                    {"id": requested.attempt_id},
                )
            ).one()
        assert row == ("compilation_reserved", 0)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_unavailable_authority_returns_only_the_safe_public_code(
    clean_postgres_database: str,
) -> None:
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    runtime = _Runtime()
    try:
        port = project_guide_compilation_execution_port(
            factory,
            material_factory=guide_document_manifest_port,
            document_access_factory=document_access,
            checker_capabilities=capability_projection(),
            authorization_context=_unavailable_service_authorization,
            runtime_factory=lambda configuration: runtime,
        )
        with pytest.raises(ProjectGuideCompilationExecutionError) as failure:
            await port.execute(
                ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
            )
        assert failure.value.code == "service_authority_denied"
        assert str(failure.value) == "service_authority_denied"
        assert "private database detail" not in str(failure.value)
        assert runtime.calls == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind, failure_code",
    [
        ("malformed", "schema_invalid"),
        ("schema", "schema_invalid"),
        ("unsafe", "schema_invalid"),
    ],
)
async def test_sdk_parser_rejection_persists_terminal_without_reinvocation(
    clean_postgres_database,
    monkeypatch,
    kind,
    failure_code,
):
    """Real SDK rejection persists its exact terminal class and replay makes no call."""
    import json
    from types import SimpleNamespace
    from agents import Runner
    from app.adapters.project_agents.openai_agent_sdk import OpenAIAgentSdkProjectGuideRuntime

    from agents import _debug

    monkeypatch.setattr(_debug, "DONT_LOG_MODEL_DATA", True)
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-only")
    payload = result().model_dump(mode="json")
    if kind == "schema":
        payload["status"] = "not-a-status"
    if kind == "unsafe":
        payload["findings"] = [{"severity": "info", "code": "bad", "message": "token=secret123"}]
    raw = "{invalid" if kind == "malformed" else json.dumps(payload)
    calls = []

    async def run(agent, *args, **kwargs):
        calls.append(1)
        return SimpleNamespace(final_output=agent.output_type.validate_json(raw))

    monkeypatch.setattr(Runner, "run", run)

    class ScriptedWorkspace:
        container_id = "cntr_scripted"

        def __init__(self, client, configuration, manifest, capabilities):
            self.context = SimpleNamespace(material=manifest)
            self.capabilities = capabilities

        async def start(self):
            await record_scripted_document_access(self.context, self.capabilities)

        async def close(self):
            await self.capabilities.documents.close()

    monkeypatch.setattr(
        "app.adapters.project_agents.openai_agent_sdk.OpenAIGuideWorkspace",
        ScriptedWorkspace,
    )
    values = await seed_database(clean_postgres_database)
    requested = await _authorized_attempt(clean_postgres_database, values)
    engine = create_async_engine(clean_postgres_database)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    command = ProjectGuideCompilationExecutionCommand(attempt_id=requested.attempt_id)
    try:
        port = _port(factory, OpenAIAgentSdkProjectGuideRuntime(runtime_configuration()))
        first = await port.execute(command)
        assert (
            first.classification is ProjectGuideCompilationExecutionClassification.INVALID_TERMINAL
        )
        assert await port.execute(command) == first
        assert calls == [1]
        async with factory() as session:
            row = (
                await session.execute(
                    text(
                        "select status,failure_code,canonical_result, "
                        "(select count(*) from project_guide_compilations) "
                        "from project_guide_compilation_attempts where id=:id"
                    ),
                    {"id": requested.attempt_id},
                )
            ).one()
        assert row == ("compilation_invalid_terminal", failure_code, None, 0)
    finally:
        await engine.dispose()
