"""Built CLI -> signed public API -> PostgreSQL project catalogue custody."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from uuid import UUID, uuid4

import httpx
import pytest

from test_public_self_service import _ready

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(BACKEND / "tests"))
from api_contract_e2e import (  # noqa: E402
    api_environment,
    assert_isolated_database_url,
    find_free_port,
    flow_settings,
    issue_flow_token,
)
from app.db.session import dispose_engine  # noqa: E402
from scripts.bootstrap_access_administrator import _run as run_bootstrap  # noqa: E402
from tests.authorization.admin_access.support import create_project  # noqa: E402
from tests.conftest import (  # noqa: E402
    clean_postgres_database as clean_postgres_database,
    postgres_database_url as postgres_database_url,
)


@pytest.mark.asyncio
async def test_built_cli_reads_real_system_catalogue(
    tmp_path: Path,
    cli,
    clean_postgres_database,
) -> None:
    env = api_environment()
    assert env["WORKSTREAM_DATABASE_URL"] == clean_postgres_database
    env["WORKSTREAM_E2E_FLOW_ISSUER"] = "https://identity.flowresearch.tech"
    env["WORKSTREAM_FLOW_AUTH_ISSUER"] = env["WORKSTREAM_E2E_FLOW_ISSUER"]
    assert_isolated_database_url(env["WORKSTREAM_DATABASE_URL"])
    issuer, audience, secret = flow_settings(env)
    tokens = {
        name: issue_flow_token(
            "catalogue-" + name,
            [],
            issuer=issuer,
            audience=audience,
            secret=secret,
        )
        for name in ("admin", "reader")
    }
    origin = f"http://127.0.0.1:{find_free_port()}"
    with (tmp_path / "catalogue-api.log").open("wb") as log:
        process = subprocess.Popen(  # noqa: S603 - fixed local API fixture
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                origin.rsplit(":", 1)[1],
                "--log-level",
                "error",
                "--no-access-log",
            ],
            cwd=BACKEND,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            await _ready(origin + "/api/v1/health", process)
            async with httpx.AsyncClient(
                base_url=origin,
                trust_env=False,
                timeout=20,
                limits=httpx.Limits(max_keepalive_connections=0),
            ) as direct:
                profiles = {}
                for name, token in tokens.items():
                    result = cli(origin, token, "whoami", "-o", "json")
                    assert result.returncode == 0, result.stderr
                    profiles[name] = json.loads(result.stdout)["actor_profile_id"]
                bootstrap_code, bootstrap = await run_bootstrap(
                    UUID(profiles["admin"]),
                    execute=True,
                )
                assert bootstrap_code == 0 and bootstrap["result_code"] == "bootstrapped"
                grant = await direct.post(
                    "/api/v1/admin-role-grants",
                    headers={
                        "Authorization": "Bearer " + tokens["admin"],
                        "Idempotency-Key": str(uuid4()),
                    },
                    json={
                        "target_actor_profile_id": profiles["reader"],
                        "role": "audit_authority",
                        "scope_type": "system",
                        "scope_project_id": None,
                        "reason": "Native catalogue read proof",
                    },
                )
                assert grant.status_code == 201, grant.text
                project_id = str(await create_project("Catalogue native API"))
                result = cli(
                    origin, tokens["reader"], "-o", "json", "project", "list", "--limit", "1"
                )
                assert result.returncode == 0 and result.stderr == "", result.stderr
                assert json.loads(result.stdout) == {
                    "items": [
                        {
                            "project_id": project_id,
                            "name": "Catalogue native API",
                            "status": "draft",
                        }
                    ],
                    "next_cursor": None,
                }
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=20)
            await dispose_engine()
