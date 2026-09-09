"""The real automatic worker reaches both projections through one invocation."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.modules.projects.api.guide_compilation import ProjectGuideCompilationDelivery
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
from app.modules.projects.api.guide_compilation import ProjectGuideCompilationDeliveryError
from tests.verified_guide_fixtures import create_verified_material_fixture
from tests.projects.client_fixtures import (
    project_client as project_client,
    project_database_env as project_database_env,
)
from .test_automatic_request import automatic_source as automatic_source
from .helpers import runtime_configuration, result


async def _delivery(factory, setup_id):
    async with factory() as session, session.begin():
        row = (
            await session.execute(
                text(
                    "select project_id,guide_id,source_snapshot_id,setup_generation from project_setup_runs where id=:id"
                ),
                {"id": str(setup_id)},
            )
        ).one()
        task_id = project_guide_compilation_task_id(str(setup_id), row.setup_generation)
        await session.execute(
            text(
                "update project_setup_runs set status='dispatch_pending',current_step='dispatch',celery_task_id=:task where id=:id"
            ),
            {"id": str(setup_id), "task": task_id},
        )
    return ProjectGuideCompilationDelivery(
        project_id=row.project_id,
        guide_id=row.guide_id,
        source_snapshot_id=row.source_snapshot_id,
        setup_run_id=setup_id,
        setup_generation=row.setup_generation,
        task_id=task_id,
    )


class Runtime:
    outcome = result()
    identity = runtime_configuration().adapter_identity
    calls = 0

    async def compile_project_guide(self, context):
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest.mark.parametrize("status", ["draft_ready", "draft_ready_with_warnings", "guide_blocked"])
async def test_pending_exact_delivery_compiles_once_and_replays_finalization(
    automatic_source, monkeypatch, status, project_client
):  # noqa: F811
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = automatic_source
    await create_verified_material_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    runtime = Runtime()
    if status != "draft_ready":
        from app.interfaces.project_agents import CompilationFinding

        runtime.outcome = result().model_copy(
            update={
                "status": status,
                "findings": (
                    CompilationFinding(
                        severity="blocking_gap" if status == "guide_blocked" else "warning",
                        code="guide.finding",
                        message="Review the guide requirement.",
                    ),
                ),
                "submission_artifact_policy": None
                if status == "guide_blocked"
                else result().submission_artifact_policy,
            }
        )
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    monkeypatch.setattr(
        worker, "project_guide_runtime_configuration", lambda settings: runtime_configuration()
    )
    coordinator = worker._coordinator(factory)
    first = await coordinator.run(delivery)
    assert first["status"] == (
        "sufficiency_blocked" if status == "guide_blocked" else "policy_draft_ready"
    )
    assert runtime.calls == 1
    async with factory() as session:
        before = await session.scalar(text("select count(*) from audit_events"))
        assert (
            await session.scalar(text("select count(*) from project_guide_compilation_attempts"))
            == 1
        )
        assert await session.scalar(
            text("select count(*) from project_guide_component_projection_operations")
        ) == (1 if status == "guide_blocked" else 2)
        assert (
            await session.scalar(text("select count(*) from project_guide_setup_finalizations"))
            == 1
        )
    if status != "guide_blocked":
        from tests.projects.client_fixtures import auth_headers

        async with factory() as session:
            policy_id = await session.scalar(
                text(
                    "select output_submission_artifact_policy_id from project_setup_runs where id=:id"
                ),
                {"id": str(setup_id)},
            )
        response = await project_client.post(
            f"/api/v1/projects/{delivery.project_id}/guides/{delivery.guide_id}/submission-artifact-policies/{policy_id}/approve",
            headers=auth_headers(),
            json={"approval_note": "Attempt approval before POL05."},
        )
        assert response.status_code == 422, response.text
        assert response.json()["detail"] == "unified compilation policy approval is unavailable"
        async with factory() as session:
            for table in [
                "effective_project_submission_artifact_policies",
                "pre_submit_checker_policies",
            ]:
                assert await session.scalar(text("select count(*) from " + table)) == 0

    def forbidden(*args):
        pytest.fail("finalized replay reached request configuration or runtime construction")

    monkeypatch.setattr(worker, "create_project_guide_runtime", forbidden)
    monkeypatch.setattr(worker, "project_guide_runtime_configuration", forbidden)
    replay = await worker._coordinator(factory).run(delivery)
    assert replay == first
    assert runtime.calls == 1
    async with factory() as session:
        assert await session.scalar(text("select count(*) from audit_events")) == before
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "update actor_identity_links set status='revoked',revoked_at=now(),"
                "revoked_by='test',revoked_reason='finalized replay probe' where id=:id"
            ),
            {"id": str(actor.identity_link_id)},
        )
    from app.modules.projects.api import ProjectGuideSetupFinalizationError

    with pytest.raises(ProjectGuideSetupFinalizationError) as denied:
        await worker._coordinator(factory).run(delivery)
    assert denied.value.code == "service_authority_denied"
    assert runtime.calls == 1


@pytest.mark.parametrize(
    "field",
    ["project_id", "guide_id", "source_snapshot_id", "setup_run_id", "setup_generation", "task_id"],
)
async def test_stale_delivery_rejects_before_any_compilation_effect(
    automatic_source, monkeypatch, field
):
    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = automatic_source
    await create_verified_material_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)

    def forbidden(*args):
        pytest.fail("stale delivery reached configuration or runtime")

    monkeypatch.setattr(worker, "create_project_guide_runtime", forbidden)
    monkeypatch.setattr(worker, "project_guide_runtime_configuration", forbidden)
    changed = delivery.model_copy(update={field: 2 if field == "setup_generation" else uuid4()})
    async with factory() as session:
        before = await session.scalar(text("select count(*) from audit_events"))
    with pytest.raises(ProjectGuideCompilationDeliveryError, match="^stale compilation delivery$"):
        await worker._coordinator(factory).run(changed)
    async with factory() as session:
        assert await session.scalar(text("select count(*) from audit_events")) == before
        for table in [
            "project_guide_compilation_request_operations",
            "project_guide_compilation_attempts",
            "project_guide_component_projection_operations",
            "project_guide_setup_finalizations",
        ]:
            assert await session.scalar(text("select count(*) from " + table)) == 0


@pytest.mark.parametrize("outcome", ["invalid", "uncertain"])
async def test_invalid_or_uncertain_attempt_reports_durable_diagnostics_without_projection(
    automatic_source, monkeypatch, outcome
):
    from app.core.config import get_settings
    from app.interfaces.project_agents import (
        ProjectAgentRuntimeError,
        ProjectGuideCompilationInvalidOutputError,
    )
    from app.modules.projects.guide_compilation.diagnostics import compilation_setup_response
    from app.modules.projects.models import ProjectSetupRun

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = automatic_source
    await create_verified_material_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    runtime = Runtime()
    runtime.outcome = (
        ProjectGuideCompilationInvalidOutputError("schema_invalid")
        if outcome == "invalid"
        else ProjectAgentRuntimeError("private-provider-detail")
    )
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    monkeypatch.setattr(
        worker, "project_guide_runtime_configuration", lambda settings: runtime_configuration()
    )
    coordinator = worker._coordinator(factory)
    first = await coordinator.run(delivery)
    replay = await coordinator.run(delivery)
    assert first == replay
    assert runtime.calls == 1
    assert first["status"] == (
        "compilation_invalid_terminal" if outcome == "invalid" else "provider_outcome_unresolved"
    )
    assert first["error_code"] == (
        "schema_invalid" if outcome == "invalid" else "provider_outcome_unresolved"
    )
    assert (first["finished_at"] is not None) == (outcome == "invalid")
    assert "private-provider-detail" not in str(first)
    async with factory() as session:
        setup = await session.get(ProjectSetupRun, str(setup_id))
        assert setup.status == "queued" and setup.current_step == "queued"
        assert setup.output_sufficiency_report_id is None
        diagnostic = await compilation_setup_response(session, setup)
        assert diagnostic.status == first["status"] and diagnostic.error_code == first["error_code"]
        for table in [
            "project_guide_compilations",
            "project_guide_component_projection_operations",
            "project_guide_setup_finalizations",
        ]:
            assert await session.scalar(text("select count(*) from " + table)) == 0


async def test_publisher_acknowledgement_cannot_overwrite_worker_finalization(
    automatic_source, monkeypatch
):
    import asyncio
    import threading
    from app.core.config import get_settings
    from app.modules.projects import setup_queue

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = automatic_source
    await create_verified_material_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "update project_setup_runs set status='queued',current_step='queued',celery_task_id=null where id=:id"
            ),
            {"id": str(setup_id)},
        )
    published, acknowledge = threading.Event(), threading.Event()

    def publish(**kwargs):
        assert kwargs["task_id"] == str(delivery.task_id)
        published.set()
        assert acknowledge.wait(30), (
            "worker did not reach finalization before publication acknowledgement"
        )
        return kwargs["task_id"]

    monkeypatch.setattr(setup_queue, "enqueue_project_guide_compilation", publish)
    runtime = Runtime()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    monkeypatch.setattr(
        worker, "project_guide_runtime_configuration", lambda settings: runtime_configuration()
    )

    async def dispatch():
        async with factory() as session:
            return await setup_queue.dispatch_project_guide_compilation_after_commit(
                session,
                project_id=str(delivery.project_id),
                guide_id=str(delivery.guide_id),
                source_snapshot_id=str(delivery.source_snapshot_id),
                setup_run_id=str(setup_id),
                setup_generation=delivery.setup_generation,
            )

    publisher = asyncio.create_task(dispatch())
    try:
        assert await asyncio.to_thread(published.wait, 10)
        receipt = await worker._coordinator(factory).run(delivery)
        assert receipt["status"] == "policy_draft_ready"
        async with factory() as session:
            before = await session.scalar(
                text("select to_jsonb(s) from project_setup_runs s where id=:id"),
                {"id": str(setup_id)},
            )
        acknowledge.set()
        assert await asyncio.wait_for(publisher, 10) == str(delivery.task_id)
        async with factory() as session:
            after = await session.scalar(
                text("select to_jsonb(s) from project_setup_runs s where id=:id"),
                {"id": str(setup_id)},
            )
        assert after == before
        assert runtime.calls == 1
    finally:
        acknowledge.set()
        if not publisher.done():
            publisher.cancel()
        await asyncio.gather(publisher, return_exceptions=True)


@pytest.mark.parametrize("boundary", ["persisted", "sufficiency", "both_projections"])
async def test_phase_crash_recovers_same_attempt_without_reinference(
    automatic_source, monkeypatch, boundary
):
    from app.core.config import get_settings

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = automatic_source
    await create_verified_material_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    runtime = Runtime()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    monkeypatch.setattr(
        worker, "project_guide_runtime_configuration", lambda settings: runtime_configuration()
    )
    coordinator = worker._coordinator(factory)
    projections = coordinator._projections

    class Crash(Exception):
        pass

    class InterruptedProjections:
        async def project_guide_sufficiency(self, command):
            if boundary == "persisted":
                raise Crash()
            await projections.project_guide_sufficiency(command)
            if boundary == "sufficiency":
                raise Crash()

        async def project_submission_artifact_policy(self, command):
            await projections.project_submission_artifact_policy(command)
            raise Crash()

    coordinator._projections = InterruptedProjections()
    with pytest.raises(Crash):
        await coordinator.run(delivery)
    coordinator._projections = projections
    receipt = await coordinator.run(delivery)
    assert receipt["status"] == "policy_draft_ready"
    assert runtime.calls == 1
    async with factory() as session:
        assert (
            await session.scalar(text("select count(*) from project_guide_compilation_attempts"))
            == 1
        )
        assert await session.scalar(text("select count(*) from project_guide_compilations")) == 1
        assert (
            await session.scalar(
                text("select count(*) from project_guide_component_projection_operations")
            )
            == 2
        )
        assert (
            await session.scalar(text("select count(*) from project_guide_setup_finalizations"))
            == 1
        )


@pytest.mark.parametrize("phase", ["request", "fence", "sufficiency", "policy", "finalization"])
async def test_each_phase_rechecks_service_authority_and_restoration_reuses_attempt(
    automatic_source, monkeypatch, phase
):
    from app.core.config import get_settings
    from app.modules.authorization.api import AuthorizationDenied
    from app.modules.projects.api import (
        ProjectGuideCompilationExecutionError,
        ProjectGuideSetupFinalizationError,
    )
    from app.modules.projects.api.guide_compilation_projections import ProjectGuideProjectionError

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = automatic_source
    await create_verified_material_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    runtime = Runtime()
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda configuration: runtime)
    monkeypatch.setattr(
        worker, "project_guide_runtime_configuration", lambda settings: runtime_configuration()
    )
    coordinator = worker._coordinator(factory)

    async def revoke():
        async with factory() as session, session.begin():
            await session.execute(
                text(
                    "update actor_identity_links set status='revoked',revoked_at=now(),revoked_by='test',revoked_reason='phase revocation' where id=:id"
                ),
                {"id": str(actor.identity_link_id)},
            )

    owners = {
        "fence": (coordinator._execution._backend, "fence"),
        "sufficiency": (coordinator._projections, "project_guide_sufficiency"),
        "policy": (coordinator._projections, "project_submission_artifact_policy"),
        "finalization": (coordinator, "_finalize"),
    }
    if phase == "request":
        await revoke()
    else:
        owner, name = owners[phase]
        original = getattr(owner, name)

        async def revoked_call(*args, **kwargs):
            await revoke()
            return await original(*args, **kwargs)

        monkeypatch.setattr(owner, name, revoked_call)
    with pytest.raises(
        (
            AuthorizationDenied,
            ProjectGuideCompilationExecutionError,
            ProjectGuideProjectionError,
            ProjectGuideSetupFinalizationError,
        )
    ) as error:
        await coordinator.run(delivery)
    if phase != "request":
        assert error.value.code == "service_authority_denied"
    assert runtime.calls == (0 if phase in {"request", "fence"} else 1)
    async with factory() as session:
        assert (
            await session.scalar(text("select count(*) from project_guide_setup_finalizations"))
            == 0
        )
        assert (
            await session.scalar(
                text("select count(*) from project_guide_component_projection_operations")
            )
            == {"request": 0, "fence": 0, "sufficiency": 0, "policy": 1, "finalization": 2}[phase]
        )
    if phase != "request":
        monkeypatch.setattr(owner, name, original)
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "update actor_identity_links set status='active',revoked_at=null,revoked_by=null,revoked_reason=null,reactivated_at=now(),reactivated_by='test',reactivation_reason='restore phase authority' where id=:id"
            ),
            {"id": str(actor.identity_link_id)},
        )
    receipt = await coordinator.run(delivery)
    assert receipt["status"] == "policy_draft_ready"
    assert runtime.calls == 1
    async with factory() as session:
        assert (
            await session.scalar(text("select count(*) from project_guide_compilation_attempts"))
            == 1
        )
        assert (
            await session.scalar(text("select count(*) from project_guide_setup_finalizations"))
            == 1
        )


async def test_concurrent_live_deliveries_share_one_provider_and_finalization(
    automatic_source, monkeypatch
):
    import asyncio
    from app.core.config import get_settings

    monkeypatch.setenv("WORKSTREAM_CELERY_TASK_ALWAYS_EAGER", "true")
    get_settings.cache_clear()
    from app.workers import project_setup as worker

    factory, actor, setup_id, snapshot = automatic_source
    await create_verified_material_fixture(snapshot["id"])
    delivery = await _delivery(factory, setup_id)
    entered, release = asyncio.Event(), asyncio.Event()
    runtime = Runtime()
    original = runtime.compile_project_guide

    async def blocked_provider(context):
        entered.set()
        await release.wait()
        return await original(context)

    monkeypatch.setattr(runtime, "compile_project_guide", blocked_provider)
    monkeypatch.setattr(worker, "create_project_guide_runtime", lambda config: runtime)
    monkeypatch.setattr(
        worker, "project_guide_runtime_configuration", lambda settings: runtime_configuration()
    )
    first = asyncio.create_task(worker._coordinator(factory).run(delivery))
    try:
        await asyncio.wait_for(entered.wait(), timeout=20)
        duplicate = await asyncio.wait_for(worker._coordinator(factory).run(delivery), timeout=20)
        assert duplicate["error_code"] == "provider_outcome_unresolved"
    finally:
        release.set()
    receipt = await asyncio.wait_for(first, timeout=30)
    assert receipt["status"] == "policy_draft_ready"
    assert runtime.calls == 1
    assert await worker._coordinator(factory).run(delivery) == receipt
    async with factory() as session:
        for table in [
            "project_guide_compilation_attempts",
            "project_guide_compilations",
            "project_guide_setup_finalizations",
        ]:
            assert await session.scalar(text("select count(*) from " + table)) == 1
