"""Built CLI download through real FastAPI, AUTH, PostgreSQL and ArtifactStore."""

import asyncio
import json
from pathlib import Path
import sys

import httpx
import pytest
import pytest_asyncio
import uvicorn

BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND / "tests"))
sys.path.insert(0, str(BACKEND / "scripts"))

from api_contract_e2e import find_free_port  # noqa: E402
from app.main import create_app  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from tests.conftest import (  # noqa: E402
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
    pagination_cursor_hmac_secret as pagination_cursor_hmac_secret,
)
from tests.tasks.guide_document_fixtures import (  # noqa: E402
    base_task_database_env as base_task_database_env,
    task_client as _task_client,
    guide_world as _guide_world,
)
from tests.test_tasks import auth_headers, set_dev_actor  # noqa: E402


@pytest.fixture
def task_database_env(base_task_database_env, monkeypatch, tmp_path):
    # Backend owner proof uses real MinIO; the independent CLI workflow already
    # supplies PostgreSQL and can exercise the same public read with local ART.
    (tmp_path / "originals").mkdir(mode=0o700)
    values = {
        "ARTIFACT_STORE_BACKEND": "local",
        "ARTIFACT_LOCAL_ROOT": str(tmp_path / "originals"),
        "ARTIFACT_SCRATCH_ROOT": str(tmp_path / "scratch"),
        "CELERY_BROKER_URL": "memory://",
        "CELERY_TASK_ALWAYS_EAGER": "false",
    }
    for scope in ("TASK", "PRODUCER", "PROJECT", "DEPLOYMENT"):
        values[f"ARTIFACT_ADMISSION_{scope}_MAXIMUM_BYTES"] = str(1024 * 1024)
    for name, value in values.items():
        monkeypatch.setenv("WORKSTREAM_" + name, value)
    get_settings.cache_clear()
    yield base_task_database_env
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def task_client(task_database_env):
    async for client in _task_client.__wrapped__(task_database_env):
        yield client


@pytest_asyncio.fixture
async def guide_world(task_client, monkeypatch):
    return await _guide_world.__wrapped__(task_client, monkeypatch)


@pytest.mark.asyncio
async def test_installed_cli_reads_and_downloads_real_assigned_originals(
    cli, guide_world, task_client, tmp_path, monkeypatch
):
    port = find_free_port()
    origin = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(),
            host="127.0.0.1",
            port=port,
            log_level="error",
            access_log=False,
        )
    )
    serving = asyncio.create_task(server.serve())
    try:
        async with httpx.AsyncClient(timeout=1, trust_env=False) as client:
            for _ in range(100):
                if serving.done():
                    await serving
                    raise AssertionError("API exited before readiness")
                try:
                    if (await client.get(origin + "/api/v1/health")).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.1)
            else:
                raise AssertionError("API readiness timeout")
        directory = tmp_path / "downloaded"
        directory.mkdir()
        result = await asyncio.to_thread(
            cli,
            origin,
            "task-token",
            "task",
            "guide",
            guide_world.task["id"],
            "--download",
            str(directory),
            "-o",
            "json",
        )
        assert result.returncode == 0, result.stderr
        documents = json.loads(result.stdout)
        assert len(documents) == len(guide_world.originals) == 2
        for document, original, extension in zip(
            documents, guide_world.originals, ("md", "pdf"), strict=True
        ):
            assert (
                directory / f"{document['document_id']}.{extension}"
            ).read_bytes() == original
        assert (
            "task_examples" not in result.stdout
            and "PRIVATE SETUP EXAMPLE" not in result.stdout
        )
        set_dev_actor(
            monkeypatch, roles="project_manager", subject="project-manager-subject"
        )
        revoke = await task_client.post(
            f"/api/v1/projects/{guide_world.project['id']}/role-grants/{guide_world.grant['grant_id']}/revoke",
            headers=auth_headers(),
            json={"reason": "Live CLI document revocation control"},
        )
        assert revoke.status_code == 200, revoke.text
        set_dev_actor(monkeypatch, roles="viewer", subject="pilot13-alice")
        denied = await asyncio.to_thread(
            cli,
            origin,
            "task-token",
            "task",
            "guide",
            guide_world.task["id"],
            "-o",
            "json",
        )
        assert denied.returncode == 1 and denied.stdout == ""
        assert json.loads(denied.stderr)["error"]["status"] == 404
    finally:
        server.should_exit = True
        await asyncio.wait_for(serving, timeout=10)
