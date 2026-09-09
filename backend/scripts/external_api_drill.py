"""Exercise current public APIs over real HTTP without product-state fixtures.

Run only through run_isolated_tests.py; see docs/engineering/external-api-drill.md.
This is a field-accounted integration probe, not production Flow certification.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import asyncpg
import httpx

ROOT = Path(__file__).resolve().parents[1]
METHODS = {"get", "post", "put", "patch", "delete"}


class ProbeFailure(Exception):
    """A named assertion failed; never include response bodies or credentials."""


class TokenIssuer:
    """Ephemeral local issuer; no authority grants and no production credentials."""

    def __init__(self):
        self.secret = os.urandom(32).hex()
        self.issuer = "https://flow.invalid/external-api-drill"
        self.audience = "workstream-external-api-drill"

    def issue(self, subject: str, **overrides) -> str:
        now = int(time.time())
        claims = dict(iss=self.issuer, aud=self.audience, sub=subject,
                      jti=str(uuid4()), subject_kind="human", scope="workstream:access",
                      iat=now, nbf=now - 5, exp=now + 600, roles=[])
        claims.update(overrides)

        def encode(value):
            return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=")

        content = encode({"alg": "HS256", "typ": "JWT"}) + b"." + encode(claims)
        signature = hmac.new(self.secret.encode(), content, hashlib.sha256).digest()
        return (content + b"." + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode()


def schema_fields(schema, document, prefix, seen=()):
    """Inventory nested fields; recursion stops, never silently grants coverage."""
    result = {prefix}
    ref = schema.get("$ref")
    if ref:
        if ref in seen or not ref.startswith("#/"):
            return result
        target = document
        for part in ref[2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        result |= schema_fields(target, document, prefix, (*seen, ref))
    for name, value in schema.get("properties", {}).items():
        result |= schema_fields(value, document, f"{prefix}.{name}", seen)
    if "items" in schema:
        result |= schema_fields(schema["items"], document, prefix + "[]", seen)
    for kind in ("anyOf", "allOf", "oneOf"):
        for value in schema.get(kind, []):
            result |= schema_fields(value, document, prefix, seen)
    return result


def inventory(document):
    """Build a method/path manifest of request and response schema fields."""
    operations = {}
    for path, item in document.get("paths", {}).items():
        for method, operation in item.items():
            if method not in METHODS:
                continue
            fields = set()
            for parameter in item.get("parameters", []) + operation.get("parameters", []):
                fields |= schema_fields(parameter.get("schema", {}), document,
                                        f'{parameter["in"]}.{parameter["name"]}')
            for value in operation.get("requestBody", {}).get("content", {}).values():
                fields |= schema_fields(value.get("schema", {}), document, "body")
            for status, response in operation.get("responses", {}).items():
                for value in response.get("content", {}).values():
                    fields |= schema_fields(value.get("schema", {}), document,
                                            f"response.{status}")
            operations[f"{method.upper()} {path}"] = {
                "schema_fields": sorted(fields), "cases": [], "status": "untested",
                "field_cases": {}, "uncovered_fields": sorted(fields),
            }
    return operations


def verify_response(response, expected_status, expected_values):
    """Assert explicit status and values; malformed JSON is not a passing body."""
    if response.status_code != expected_status:
        raise ProbeFailure("unexpected_status")
    try:
        body = response.json()
    except ValueError as exc:
        raise ProbeFailure("invalid_json") from exc
    for path, expected in expected_values.items():
        value = body
        for part in path.split("."):
            if not isinstance(value, dict) or part not in value:
                raise ProbeFailure("missing_response_field")
            value = value[part]
        if value != expected or type(value) is not type(expected):
            raise ProbeFailure("response_value_mismatch")
    return body


class Drill:
    """Record actual assertions separately from schema presence and denials."""

    def __init__(self, client, document, report):
        self.client, self.report = client, report
        report["operations"] = inventory(document)
        self.results = report["cases"] = []

    async def call(self, name, method, route, *, path=None, token=None, payload=None,
                   expected=200, values=None, fields=(), headers=None):
        operation = self.report["operations"][f"{method} {route}"]
        request_headers = {"X-Request-ID": str(uuid4()), "X-Correlation-ID": str(uuid4())}
        if token:
            request_headers["Authorization"] = f"Bearer {token}"
        if payload is not None:
            request_headers["Idempotency-Key"] = str(uuid4())
        request_headers.update(headers or {})
        row = {"name": name, "operation": f"{method} {route}", "expected": expected,
               "actual": None, "result": "failed", "asserted_fields": list(fields)}
        self.results.append(row)
        operation["cases"].append(name)
        try:
            response = await self.client.request(method, path or route, json=payload,
                                                 headers=request_headers)
            row["actual"] = response.status_code
            body = verify_response(response, expected, values or {})
            for header in ("X-Request-ID", "X-Correlation-ID"):
                if response.headers.get(header) != request_headers[header]:
                    raise ProbeFailure("request_provenance_mismatch")
            row["result"] = "success" if expected < 300 else "expected_denial"
            if operation["status"] != "failed":
                operation["status"] = (
                    "partial_positive" if row["result"] == "success"
                    or operation["status"] == "partial_positive" else "denial_only"
                )
            for field in fields:
                operation["field_cases"].setdefault(field, []).append(name)
            operation["uncovered_fields"] = sorted(
                set(operation["schema_fields"]) - operation["field_cases"].keys()
            )
            print(f'{row["result"]}: {name}: {method} {route} -> {response.status_code}', flush=True)
            return body
        except Exception:
            operation["status"] = "failed"
            raise


async def profile_cases(drill, issuer, token):
    route = "/api/v1/actors/me"
    for name, bad in (("missing", None), ("signature", TokenIssuer().issue("outsider")),
                      ("expired", issuer.issue("outsider", exp=int(time.time()) - 60)),
                      ("issuer", issuer.issue("outsider", iss="https://wrong.invalid")),
                      ("audience", issuer.issue("outsider", aud="wrong")),
                      ("not_before", issuer.issue("outsider", nbf=int(time.time()) + 300))):
        await drill.call("token_" + name, "GET", route, token=bad, expected=401)
    actor = await drill.call("profile_self", "GET", route, token=token,
                             values={"actor_kind": "human", "status": "active"},
                             fields=("response.200.actor_kind", "response.200.status"))
    for field, limit in (("display_name", 200), ("contact_email", 320)):
        for label, value in (("text", "example"), ("limit", "x" * limit), ("null", None)):
            await drill.call(f"{field}_{label}", "PATCH", route, token=token,
                             payload={field: value}, values={field: value},
                             fields=(f"body.{field}", f"response.200.{field}"))
            await drill.call(f"{field}_{label}_readback", "GET", route, token=token,
                             values={field: value}, fields=(f"response.200.{field}",))
        for label, value in (("too_long", "x" * (limit + 1)), ("blank", "  "),
                             ("type", {"unexpected": True})):
            await drill.call(f"{field}_{label}", "PATCH", route, token=token,
                             payload={field: value}, expected=422, fields=(f"body.{field}",))
            await drill.call(f"{field}_{label}_unchanged", "GET", route, token=token,
                             values={field: None}, fields=(f"response.200.{field}",))
    await drill.call("empty_profile_patch", "PATCH", route, token=token, payload={}, expected=422)
    await drill.call("unknown_profile_field", "PATCH", route, token=token,
                     payload={"admin_roles": ["access_administrator"]}, expected=422)
    return actor["actor_profile_id"]


async def project_cases(drill, admin, manager, outsider, manager_id):
    grant = await drill.call("grant_manager", "POST", "/api/v1/admin-role-grants", token=admin,
        payload={"target_actor_profile_id": manager_id, "role": "project_manager",
                 "scope_type": "system", "reason": "Isolated external API drill"}, expected=201)
    for route in ("/api/v1/authorization/permissions", "/api/v1/authorization/admin-role-definitions"):
        await drill.call("read_" + route.rsplit("/", 1)[1], "GET", route, token=admin)
    await drill.call("list_system_grants", "GET", "/api/v1/admin-role-grants",
                     path="/api/v1/admin-role-grants?scope_type=system", token=admin)
    payload = {"name": "External drill", "slug": "drill-" + uuid4().hex,
               "description": "Disposable HTTP-only project"}
    key = {"Idempotency-Key": str(uuid4())}
    project = await drill.call("create_project", "POST", "/api/v1/projects", token=manager,
        payload=payload, headers=key, expected=201, values=payload,
        fields=("body.name", "body.slug", "body.description", "header.Idempotency-Key"))
    await drill.call("replay_project", "POST", "/api/v1/projects", token=manager,
        payload=payload, headers=key, expected=201, values={"id": project["id"]})
    await drill.call("conflicting_project_replay", "POST", "/api/v1/projects", token=manager,
        payload=payload | {"name": "Changed"}, headers=key, expected=409)
    route, path = "/api/v1/projects/{project_id}", f'/api/v1/projects/{project["id"]}'
    await drill.call("read_project", "GET", route, path=path, token=manager, values=payload)
    await drill.call("ungranted_project_denied", "GET", route, path=path, token=outsider, expected=404)
    guide_route = route + "/guides"
    guide = await drill.call("create_guide", "POST", guide_route, path=path + "/guides",
        token=manager, expected=201, payload={"version": "initial", "content_markdown": "# Task guide",
                                            "change_summary": "Initial draft"},
        values={"version": "initial", "content_markdown": "# Task guide", "status": "draft"},
        fields=("body.version", "body.content_markdown", "body.change_summary"))
    gpath, groute = path + "/guides/" + guide["id"], guide_route + "/{guide_id}"
    await drill.call("patch_guide", "PATCH", groute, path=gpath, token=manager,
        payload={"content_markdown": "# Updated guide", "change_summary": "Updated"},
        values={"content_markdown": "# Updated guide", "change_summary": "Updated"},
        fields=("body.content_markdown", "body.change_summary"))
    await policy_cases(drill, manager, groute, gpath)
    await authority_cases(drill, admin, manager, outsider, manager_id, project)
    await drill.call("revoke_manager", "POST", "/api/v1/admin-role-grants/{grant_id}/revoke",
        path=f'/api/v1/admin-role-grants/{grant["resource_id"]}/revoke', token=admin,
        payload={"reason": "Verify authority revocation"})
    await drill.call("revoked_project_creation", "POST", "/api/v1/projects", token=manager,
        payload=payload | {"slug": "revoked-" + uuid4().hex}, expected=403)


async def policy_cases(drill, manager, groute, gpath):
    """Exercise explicit policy fields, defaults, validation and stored replay."""
    policies = {
        "review-policy": {"human_review_required": True, "review_preference_window_seconds": 3600,
                          "review_lease_duration_seconds": 1800},
        "revision-policy": {"max_revision_rounds": 2, "revision_deadline_hours": 24},
    }
    defaults = {
        "review-policy": {"max_active_review_leases_per_reviewer": 1, "self_review_allowed": False,
            "reject_policy": "close_task", "finding_evidence_requirement": "optional",
            "requires_second_review": False, "allowed_decisions": ["accept", "needs_revision", "reject"],
            "minimum_finding_fields": []},
        "revision-policy": {"allowed_resubmission_states": ["needs_revision"],
                            "reviewer_reassignment_rule": None},
    }
    for suffix, body in policies.items():
        key = {"If-Match": '"no-current-policy"', "Idempotency-Key": str(uuid4())}
        result = await drill.call("create_" + suffix, "PUT", groute + "/" + suffix,
            path=gpath + "/" + suffix, token=manager, payload=body, headers=key,
            values=body | defaults[suffix] | {"policy_generation": 1},
            fields=tuple("body." + field for field in body))
        await drill.call("stored_replay_" + suffix, "PUT", groute + "/" + suffix,
            path=gpath + "/" + suffix, token=manager, payload=body, headers=key, values=result)
        invalids = [("unknown", body | {"unexpected": 1})]
        for field in body:
            if field != "human_review_required":
                invalids.append((field + "_missing", {k: v for k, v in body.items() if k != field}))
                invalids.append((field + "_zero", body | {field: 0}))
            invalids.append((field + "_null", body | {field: None}))
            invalids.append((field + "_type", body | {field: {"bad": True}}))
        invalids += [(field + "_enum", body | {field: "invalid"}) for field in defaults[suffix]
                     if field not in {"reviewer_reassignment_rule"}]
        for label, invalid in invalids:
            await drill.call(suffix + "_" + label, "PUT", groute + "/" + suffix,
                path=gpath + "/" + suffix, token=manager, payload=invalid,
                headers={"If-Match": '"no-current-policy"'}, expected=422)
        await drill.call("after_rejections_" + suffix, "PUT", groute + "/" + suffix,
            path=gpath + "/" + suffix, token=manager, payload=body, headers=key, values=result)
        await drill.call("stale_selector_" + suffix, "PUT", groute + "/" + suffix,
            path=gpath + "/" + suffix, token=manager, payload=body,
            headers={"If-Match": '"no-current-policy"'}, expected=409)


async def authority_cases(drill, admin, manager, outsider, manager_id, project):
    """Prove scoped authority against a real second project and lifecycle reads."""
    other = await drill.call("second_project", "POST", "/api/v1/projects", token=manager,
        payload={"name": "Foreign project", "slug": "foreign-" + uuid4().hex}, expected=201)
    outsider_body = await drill.call("scoped_actor", "GET", "/api/v1/actors/me", token=outsider)
    scoped_id = outsider_body["actor_profile_id"]
    await drill.call("grant_scoped_manager", "POST", "/api/v1/admin-role-grants", token=admin,
        payload={"target_actor_profile_id": scoped_id, "role": "project_manager",
                 "scope_type": "project", "scope_project_id": project["id"],
                 "reason": "Exact-project test"}, expected=201)
    route = "/api/v1/projects/{project_id}"
    await drill.call("scoped_project_control", "GET", route,
                     path=f'/api/v1/projects/{project["id"]}', token=outsider,
                     values={"id": project["id"]})
    await drill.call("foreign_project_denial", "GET", route,
                     path=f'/api/v1/projects/{other["id"]}', token=outsider, expected=404)
    await drill.call("scoped_authorization_context", "GET", "/api/v1/actors/me/authorization-context",
        path=f'/api/v1/actors/me/authorization-context?project_id={project["id"]}', token=outsider,
        values={"project_id": project["id"], "admin_roles": ["project_manager"]})
    for suffix in ("contributor-candidates", "role-grants"):
        await drill.call("list_" + suffix, "GET", route + "/" + suffix,
            path=f'/api/v1/projects/{project["id"]}/{suffix}?limit=1', token=outsider)
        await drill.call("invalid_limit_" + suffix, "GET", route + "/" + suffix,
            path=f'/api/v1/projects/{project["id"]}/{suffix}?limit=0', token=outsider, expected=422,
            fields=("query.limit",))
    for suffix in ("", "/identity-links", "/admin-role-grants"):
        await drill.call("admin_actor_read" + suffix, "GET", "/api/v1/actors/{actor_profile_id}" + suffix,
            path=f"/api/v1/actors/{manager_id}" + suffix + ("?scope_type=system" if suffix == "/admin-role-grants" else ""),
            token=admin)
    for action in ("suspend", "reactivate", "deactivate"):
        await drill.call("actor_" + action, "POST", "/api/v1/actors/{actor_profile_id}/" + action,
            path=f"/api/v1/actors/{scoped_id}/" + action, token=admin,
            payload={"reason": "Isolated lifecycle probe"})
        state = {"suspend": "suspended", "reactivate": "active", "deactivate": "deactivated"}[action]
        await drill.call("actor_" + action + "_readback", "GET", "/api/v1/actors/{actor_profile_id}",
            path=f"/api/v1/actors/{scoped_id}", token=admin, values={"status": state})


async def isolation(metadata_path):
    """Read-only preflight; never use a shared or populated database."""
    metadata = json.loads(metadata_path.read_text())
    url = os.environ.get("WORKSTREAM_DATABASE_URL", "")
    parsed = urlsplit(url)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if not (parsed.scheme == "postgresql+asyncpg" and parsed.hostname == "127.0.0.1"
            and not parsed.query and not parsed.fragment
            and re.fullmatch(r"workstream_test_[a-f0-9]{12}", parsed.path[1:])
            and re.fullmatch(r"workstream_role_[a-f0-9]{12}", unquote(parsed.username or ""))
            and metadata.get("schema_version") == 2 and metadata.get("database_provisioned") is True
            and metadata.get("database_cleanup_complete") is False
            and metadata.get("tree_sha") == sha
            and metadata.get("database_name") == parsed.path[1:]
            and metadata.get("database_role") == unquote(parsed.username or "")):
        raise ProbeFailure("isolation_required")
    connection = await asyncpg.connect(url.replace("postgresql+asyncpg:", "postgresql:", 1))
    try:
        row = await connection.fetchrow("select current_database() as db, current_user as role, "
                                        "(select count(*) from actor_profiles) as actors")
        if row["db"] != metadata["database_name"] or row["role"] != metadata["database_role"] or row["actors"]:
            raise ProbeFailure("fresh_owned_database_required")
    finally:
        await connection.close()
    return url, sha


async def run(args, report):
    url, sha = await isolation(args.isolation_metadata)
    if (ROOT / ".env").exists():
        raise ProbeFailure("ambient_backend_env_file_forbidden")
    issuer = TokenIssuer()
    env = {"WORKSTREAM_DATABASE_URL": url, "WORKSTREAM_ENVIRONMENT": "local",
           "WORKSTREAM_AUTH_PROVIDER": "flow", "WORKSTREAM_FLOW_AUTH_ISSUER": issuer.issuer,
           "WORKSTREAM_FLOW_AUTH_AUDIENCE": issuer.audience,
           "WORKSTREAM_FLOW_AUTH_LOCAL_HMAC_SECRET": issuer.secret,
           "WORKSTREAM_API_RATE_LIMIT_KEY_SECRET": base64.b64encode(os.urandom(32)).decode(),
           "WORKSTREAM_PAGINATION_CURSOR_HMAC_SECRET": base64.b64encode(os.urandom(32)).decode(),
           "WORKSTREAM_ARTIFACT_STORE_BACKEND": "disabled",
           "WORKSTREAM_PROJECT_SETUP_PIPELINE_AUTOSTART": "false", "PYTHONPATH": str(ROOT)}
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT))
    report.update(commit=sha, worktree_dirty=dirty,
        drill_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        limitations=["local synthetic Flow issuer, not deployed Flow",
        "artifact storage disabled; no provider/model calls", "no product fixtures or trigger suppression",
        "partial scenarios; no operation certified fully field-complete"], setup=[])
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory",
        "--host", "127.0.0.1", "--port", str(port), "--no-access-log"], cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", trust_env=False,
                                     follow_redirects=False, timeout=20) as client:
            for _ in range(100):
                if process.poll() is not None:
                    raise ProbeFailure("server_startup_failed")
                try:
                    response = await client.get("/api/v1/health")
                    if response.status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                await asyncio.sleep(0.2)
            else:
                raise ProbeFailure("server_startup_timeout")
            document = (await client.get("/openapi.json")).json()
            drill = Drill(client, document, report)
            await drill.call("health", "GET", "/api/v1/health")
            admin, manager, outsider = (issuer.issue(name) for name in ("admin", "manager", "outsider"))
            admin_id = await profile_cases(drill, issuer, admin)
            bootstrap = subprocess.run([sys.executable, "scripts/bootstrap_access_administrator.py",
                "--actor-profile-id", admin_id, "--execute"], env=env, cwd=ROOT,
                capture_output=True, timeout=30)
            if bootstrap.returncode != 0:
                raise ProbeFailure("bootstrap_failed")
            report["setup"].append("documented initial Access Administrator bootstrap CLI")
            manager_body = await drill.call("manager_profile", "GET", "/api/v1/actors/me", token=manager)
            await drill.call("outsider_profile", "GET", "/api/v1/actors/me", token=outsider)
            await project_cases(drill, admin, manager, outsider, manager_body["actor_profile_id"])
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isolation-metadata", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = {"result": "failed", "operations": {}, "cases": []}
    if args.report.resolve().is_relative_to(ROOT.parent):
        raise SystemExit("report must be outside repository")
    descriptor = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as output:
        try:
            asyncio.run(run(args, report))
            report["result"] = "completed_partial_coverage"
        except Exception as exc:
            report["failure_kind"] = type(exc).__name__
            if isinstance(exc, ProbeFailure):
                report["failure_code"] = str(exc)
        finally:
            json.dump(report, output, indent=2)
            output.write("\n")
    print(report["result"])
    return 0 if report["result"] == "completed_partial_coverage" else 1


if __name__ == "__main__":
    raise SystemExit(main())
