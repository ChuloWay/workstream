"""PostgreSQL proof for the local project-points provisioning operator script."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterator
import importlib
import json
from pathlib import Path
import subprocess
import sys
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.compensation.models import ProjectCompensationAdapterBinding
from app.modules.contributions.models import ProjectCompensationUnit
from app.modules.contributions.units.models import ProjectCompensationUnitCreationEvent
from project_create_fixtures import insert_historical_project
from tests.projects.guide_compilation.proposals.pg_support import seed_review_actor

script = importlib.import_module("scripts.provision_project_points")


@pytest.fixture(name="points_database_env")
def _points_database_env(
    monkeypatch: pytest.MonkeyPatch, clean_postgres_database: str
) -> Iterator[str]:
    monkeypatch.setenv("WORKSTREAM_DATABASE_URL", clean_postgres_database)
    monkeypatch.setenv("WORKSTREAM_ENVIRONMENT", "test")
    get_settings.cache_clear()
    try:
        yield clean_postgres_database
    finally:
        get_settings.cache_clear()


async def _project() -> UUID:
    project_id = new_record_id()
    async with db_session.get_session_factory()() as session, session.begin():
        await insert_historical_project(
            session, project_id=str(project_id), name="Points script project",
            slug=f"points-script-{project_id.hex}",
        )
    return project_id


async def _insert_adapter_actor() -> UUID:
    """Test setup only: stand in for the Access Administrator route."""
    actor_id = new_record_id()
    async with db_session.get_session_factory()() as session, session.begin():
        session.add(ActorProfile(
            id=str(actor_id), actor_kind="service", status="active",
            provisioning_method="manual_service_provisioning",
            service_identity=ServiceIdentity.COMPENSATION_ADAPTER.value,
            created_by="points-script-test",
        ))
        await session.flush()
        session.add(ActorIdentityLink(
            id=str(new_record_id()), actor_profile_id=str(actor_id), issuer="workstream-internal",
            subject=f"points-adapter-{actor_id}", subject_kind="service", status="active",
            linked_by="points-script-test",
        ))
    return actor_id


async def _finance(project_id: UUID, role: str = "finance_authority") -> UUID:
    actor, _ = await seed_review_actor(db_session.get_session_factory(), project_id, role=role)
    return actor.actor_profile_id


def _args(project_id: UUID, finance: UUID, **changes) -> argparse.Namespace:
    values = dict(
        project_id=project_id, finance_actor_profile_id=finance,
        unit_code=script.DEFAULT_UNIT_CODE, route_key=script.DEFAULT_ROUTE_KEY,
        admin_subject=None, api_url="http://127.0.0.1:8000", subject_prefix="local-agent-loop",
    )
    values.update(changes)
    return argparse.Namespace(**values)


async def _state(project_id: UUID) -> tuple[int, int, int]:
    async with db_session.get_session_factory()() as session:
        units = await session.scalar(select(func.count()).select_from(ProjectCompensationUnit).where(
            ProjectCompensationUnit.project_id == str(project_id)))
        events = await session.scalar(
            select(func.count()).select_from(ProjectCompensationUnitCreationEvent))
        bindings = await session.scalar(
            select(func.count()).select_from(ProjectCompensationAdapterBinding).where(
                ProjectCompensationAdapterBinding.project_id == str(project_id)))
    return units, events, bindings


def test_defaults_name_the_flow_points_unit_and_operation_ids_are_stable() -> None:
    project = new_record_id()
    assert script.DEFAULT_UNIT_CODE == "FLOW"
    assert script.operation_id("unit", project, "FLOW") == script.operation_id("unit", project, "FLOW")
    assert script.operation_id("unit", project, "FLOW") != script.operation_id(
        "binding", project, "FLOW"
    )


@pytest.mark.asyncio
async def test_fresh_run_provisions_actor_unit_and_binding_then_rerun_changes_nothing(
    points_database_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = await _project()
    finance = await _finance(project_id)
    calls = []

    async def provision(api_url: str, admin_subject: str, subject_prefix: str) -> str:
        calls.append((api_url, admin_subject, subject_prefix))
        await _insert_adapter_actor()
        return "provisioned"

    monkeypatch.setattr(script, "_provision_adapter_actor", provision)
    output: dict = {}
    first = await script.run(_args(project_id, finance, admin_subject="admin"), output)

    assert calls == [("http://127.0.0.1:8000", "admin", "local-agent-loop")]
    assert (first["result_code"], first["adapter_actor"], first["unit"], first["binding"]) == (
        "ready", "provisioned", "created", "created"
    )
    assert first["unit_code"] == "FLOW" and await _state(project_id) == (1, 1, 1)

    second = await script.run(_args(project_id, finance, admin_subject="admin"), {})
    assert (second["adapter_actor"], second["unit"], second["binding"]) == (
        "existing", "existing", "existing"
    )
    assert second["adapter_binding_id"] == first["adapter_binding_id"]
    assert second["adapter_actor_id"] == first["adapter_actor_id"]
    assert len(calls) == 1 and await _state(project_id) == (1, 1, 1)


@pytest.mark.asyncio
async def test_existing_actor_without_unit_creates_unit_and_binding(
    points_database_env: str,
) -> None:
    project_id = await _project()
    finance = await _finance(project_id)
    adapter = await _insert_adapter_actor()

    result = await script.run(_args(project_id, finance), {})

    assert (result["adapter_actor"], result["unit"], result["binding"]) == (
        "existing", "created", "created"
    )
    assert result["adapter_actor_id"] == str(adapter)
    async with db_session.get_session_factory()() as session:
        binding = await session.get(
            ProjectCompensationAdapterBinding, UUID(result["adapter_binding_id"])
        )
    assert binding is not None and binding.adapter_actor_id == str(adapter)
    assert (binding.instrument_type, binding.route_key, binding.status) == (
        "project_points", "flow_points.local", "active"
    )


@pytest.mark.asyncio
async def test_existing_unit_without_binding_creates_only_the_binding(
    points_database_env: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = await _project()
    finance = await _finance(project_id)
    await _insert_adapter_actor()

    original_ensure_binding = script._ensure_binding

    async def no_binding(*args) -> tuple[str, UUID]:
        raise RuntimeError("stop after unit")

    monkeypatch.setattr(script, "_ensure_binding", no_binding)
    with pytest.raises(RuntimeError, match="stop after unit"):
        await script.run(_args(project_id, finance), {})
    assert await _state(project_id) == (1, 1, 0)
    monkeypatch.setattr(script, "_ensure_binding", original_ensure_binding)

    result = await script.run(_args(project_id, finance), {})

    assert (result["unit"], result["binding"]) == ("existing", "created")
    assert await _state(project_id) == (1, 1, 1)


def _argv(project_id: UUID, finance: UUID, *extra: str) -> list[str]:
    return ["--project-id", str(project_id), "--finance-actor-profile-id", str(finance), *extra]


@pytest.mark.asyncio
async def test_missing_actor_without_admin_subject_is_unavailable(
    points_database_env: str, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    project_id = await _project()
    finance = await _finance(project_id)
    await db_session.dispose_engine()

    code, output = await _run_main(monkeypatch, capsys, _argv(project_id, finance))

    assert code == 3 and output["result_code"] == "unavailable"
    assert output["detail"] == "adapter_actor_missing_and_no_admin_subject"
    assert await _state(project_id) == (0, 0, 0)


async def _run_main(monkeypatch, capsys, argv):
    """Run the synchronous entrypoint off the test loop, as the CLI does."""
    code = await asyncio.to_thread(script.main, argv)
    return code, json.loads(capsys.readouterr().out)


@pytest.mark.asyncio
async def test_failed_actor_provisioning_is_unavailable(
    points_database_env: str, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    project_id = await _project()
    finance = await _finance(project_id)
    await db_session.dispose_engine()

    async def failed(*args) -> str:
        return "failed:403:permission_denied"

    monkeypatch.setattr(script, "_provision_adapter_actor", failed)
    code, output = await _run_main(
        monkeypatch, capsys, _argv(project_id, finance, "--admin-subject", "admin")
    )

    assert code == 3 and output["detail"] == "adapter_actor_failed:403:permission_denied"
    assert await _state(project_id) == (0, 0, 0)


@pytest.mark.asyncio
async def test_finance_actor_without_one_active_identity_is_unavailable(
    points_database_env: str, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    project_id = await _project()
    await _insert_adapter_actor()
    await db_session.dispose_engine()

    code, output = await _run_main(monkeypatch, capsys, _argv(project_id, new_record_id()))

    assert code == 3 and output["detail"] == "finance_identity_unavailable"
    assert output["adapter_actor"] == "existing"


@pytest.mark.asyncio
async def test_non_finance_actor_fails_with_bounded_error_and_no_unit(
    points_database_env: str, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    project_id = await _project()
    manager = await _finance(project_id, role="project_manager")
    await _insert_adapter_actor()
    await db_session.dispose_engine()

    code, output = await _run_main(monkeypatch, capsys, _argv(project_id, manager))

    assert code == 1 and output == {
        "result_code": "failed", "error_type": "ContributionPolicyAuthorizationDenied",
        "project_id": str(project_id), "adapter_actor": "existing",
        "adapter_actor_id": output["adapter_actor_id"],
    }
    assert await _state(project_id) == (0, 0, 0)


@pytest.mark.asyncio
async def test_main_prints_ready_summary(
    points_database_env: str, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    project_id = await _project()
    finance = await _finance(project_id)
    await _insert_adapter_actor()
    await db_session.dispose_engine()

    code, output = await _run_main(
        monkeypatch, capsys, _argv(project_id, finance, "--unit-code", "PARTNER")
    )

    assert code == 0 and output["result_code"] == "ready" and output["unit_code"] == "PARTNER"


@pytest.mark.asyncio
async def test_actor_provisioning_uses_the_existing_route_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def provision(client, admin_subject, identities, prefix):
        calls.append((str(client.base_url), admin_subject, identities, prefix))
        return {identities[0]: "provisioned"}

    monkeypatch.setattr(script, "provision_service_actors", provision)
    assert await script._provision_adapter_actor("http://127.0.0.1:8000", "admin", "loop") == (
        "provisioned"
    )
    assert calls == [(
        "http://127.0.0.1:8000", "admin", ("workstream.compensation.adapter",), "loop"
    )]
    with pytest.raises(script.ProvisioningUnavailable, match="invalid_api_url"):
        await script._provision_adapter_actor("http://example.com", "admin", "loop")


def test_documented_direct_invocation_imports_its_sibling_helper() -> None:
    """``python scripts/provision_project_points.py`` runs without package context."""
    backend = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/provision_project_points.py", "--help"],
        cwd=backend, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--finance-actor-profile-id" in result.stdout


@pytest.mark.asyncio
async def test_existing_binding_with_another_route_is_reported_as_mismatch(
    points_database_env: str, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    project_id = await _project()
    finance = await _finance(project_id)
    await _insert_adapter_actor()
    first = await script.run(_args(project_id, finance), {})
    await db_session.dispose_engine()

    code, output = await _run_main(
        monkeypatch, capsys, _argv(project_id, finance, "--route-key", "other.route")
    )

    assert code == 3 and output["detail"] == "active_binding_mismatch"
    assert output["unit"] == "existing" and "adapter_binding_id" not in output
    assert first["binding"] == "created" and await _state(project_id) == (1, 1, 1)


@pytest.mark.asyncio
async def test_binding_failure_after_unit_reports_the_committed_steps(
    points_database_env: str, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    project_id = await _project()
    finance = await _finance(project_id)
    await _insert_adapter_actor()
    await db_session.dispose_engine()

    async def no_binding(*args):
        raise RuntimeError("binding store unavailable")

    monkeypatch.setattr(script, "_ensure_binding", no_binding)
    code, output = await _run_main(monkeypatch, capsys, _argv(project_id, finance))

    assert code == 1 and output["error_type"] == "RuntimeError"
    assert (output["adapter_actor"], output["unit"], output["unit_code"]) == (
        "existing", "created", "FLOW"
    )
    assert await _state(project_id) == (1, 1, 0)


@pytest.mark.parametrize("environment", ["staging", "preview", "prod", "production"])
def test_production_like_environments_are_refused_before_any_database_access(
    monkeypatch: pytest.MonkeyPatch, capsys, environment: str
) -> None:
    from types import SimpleNamespace

    async def unexpected():
        raise AssertionError("database must not be read")

    monkeypatch.setattr(script, "get_settings", lambda: SimpleNamespace(environment=environment))
    monkeypatch.setattr(script, "_adapter_actor_id", unexpected)
    monkeypatch.setattr(script, "dispose_engine", lambda: asyncio.sleep(0))

    code = script.main(_argv(new_record_id(), new_record_id()))

    assert code == 3
    assert json.loads(capsys.readouterr().out)["detail"] == "production_like_environment"
