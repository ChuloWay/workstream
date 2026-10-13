"""Exercise the public first journey after a scripted, approved guide precondition.

Run only through the isolated database/MinIO runner with a disposable Redis broker.
The source compilation is a canonical owner fixture, not a model-provider run.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import nullcontext
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from uuid import UUID, uuid4

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts import (
    create_artifact_scratch_manager,
    create_artifact_store_bootstrap,
)
from app.core.config import get_settings
from app.core.identifiers import new_record_id
from app.modules.actors.api.service_identities import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.checkers.models import CheckerRun, SelectedPreSubmitRun
from app.modules.outbox.models import OutboxEvent
from app.modules.artifacts.service import artifact_storage_namespace_spec
from app.modules.projects.models import ProjectGuide
from app.modules.tasks.models import Submission, SubmissionDispatch, WorkstreamTask
from experiments.pilot04_external_checker_runtime.run_probe import _image_identity
from experiments.pilot04_external_checker_runtime.run_selected_end_to_end_probe import (
    _locked_spec,
    _secret_archive,
    _start_service,
    _stop_service,
    _wait_service,
)
from tests.authorization.post_submit_routing.support import provision_router
from tests.post_submit_materialization_helpers import (
    archive_with_modes,
    provision_material_services,
)
from tests.projects.guide_activation.pg_support import (
    activation_command,
    publish_policy,
)
from tests.projects.guide_activation.source_fixtures import source_case
from tests.projects.guide_compilation.helpers import service_actor
from tests.projects.guide_compilation.proposals.pg_support import (
    seed_review_actor,
    seed_selected_review_revision_inputs,
)
from tests.projects.post_policy.pg_support import operate, prepare_post_policy
from tests.tasks.invalidation_support import provision_reconciler
from tests.test_s3_artifact_store import minio_settings
from app.interfaces.project_agents import SubmissionArtifactPolicyProposal
from app.modules.projects.api.post_policy import PostPolicyApproval

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND / "scripts"))
from api_contract_e2e import (  # noqa: E402
    api_environment, find_free_port, flow_settings, issue_flow_token,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _process(command: list[str], *, env: dict[str, str], log: Path) -> subprocess.Popen:
    with log.open("wb") as output:
        return subprocess.Popen(
            command, cwd=BACKEND, env=env, stdout=output,
            stderr=subprocess.STDOUT, start_new_session=True,
        )


def _stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


async def _wait_api(origin: str, process: subprocess.Popen) -> None:
    async with httpx.AsyncClient(timeout=2) as client:
        for _ in range(100):
            _require(process.poll() is None, "public API exited before readiness")
            try:
                if (await client.get(origin + "/api/v1/health")).status_code == 200:
                    return
            except httpx.TransportError:
                pass
            await asyncio.sleep(0.1)
    raise RuntimeError("public API did not become ready")


async def _wait_worker(process: subprocess.Popen, hostname: str) -> None:
    from app.workers.celery_app import celery_app

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        _require(process.poll() is None, "prefork worker exited before readiness")
        pong = await asyncio.to_thread(
            celery_app.control.ping, destination=[hostname], timeout=0.5
        )
        if pong:
            return
        await asyncio.sleep(0.2)
    raise RuntimeError("prefork worker did not become ready")


def _token(env: dict[str, str], actor) -> str:
    issuer, audience, secret = flow_settings(env)
    return issue_flow_token(
        str(actor.actor_profile_id), [], issuer=issuer, audience=audience, secret=secret
    )


async def _json(client: httpx.AsyncClient, method: str, path: str, token: str,
                expected: int, **options) -> dict:
    headers = {"Authorization": "Bearer " + token, **options.pop("headers", {})}
    response = await client.request(method, path, headers=headers, **options)
    if response.status_code != expected:
        # Public error codes are enough to diagnose without printing guide bytes or tokens.
        try:
            error = response.json().get("error", {}).get("code")
        except ValueError:
            error = None
        raise RuntimeError(f"{method} {path} returned {response.status_code}/{error}; expected {expected}")
    return response.json()


async def _provision_runtime_services(factory) -> None:
    async with factory() as session, session.begin():
        for identity in (ServiceIdentity.OUTBOX_DISPATCHER,
                         ServiceIdentity.ARTIFACT_SCHEDULER):
            existing = await session.scalar(select(ActorProfile.id).where(
                ActorProfile.service_identity == identity.value
            ))
            if existing is not None:
                continue
            actor_id = str(new_record_id())
            session.add(ActorProfile(
                id=actor_id, actor_kind="service", status="active",
                provisioning_method="manual_service_provisioning",
                service_identity=identity.value,
                created_by=actor_id,
            ))
            session.add(ActorIdentityLink(
                id=str(new_record_id()), actor_profile_id=actor_id,
                issuer="workstream.internal", subject=identity.value,
                subject_kind="service", status="active", linked_by="workstream:system:bootstrap",
            ))


async def _deliver(factory, event_id: UUID, project_id: UUID) -> None:
    from app.workers.outbox import deliver_event

    async with factory() as session:
        current = await session.get(OutboxEvent, event_id)
        _require(current is not None, "expected outbox event is missing")
        if current.delivery_state == "acknowledged":
            return
    # Production task publication and real prefork child handle the event.
    await asyncio.to_thread(
        deliver_event.apply_async,
        args=(str(event_id), str(project_id)),
    )
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        async with factory() as session:
            event = await session.get(OutboxEvent, event_id)
            if event.delivery_state == "acknowledged":
                return
            if event.delivery_state in {"dead_letter", "cancelled"}:
                raise RuntimeError(f"outbox event ended {event.delivery_state}")
        await asyncio.sleep(0.3)
    raise RuntimeError("outbox event was not acknowledged by prefork worker")


async def _ready_admission(client, factory, task_id: str, assignment_id: str,
                           contributor_token: str, archive: bytes, summary: str,
                           attestation: str) -> str:
    from app.workers.artifacts import scan_pending_work

    key = str(uuid4())
    headers = {
        "Content-Type": "application/zip",
        "X-Task-Assignment-Id": assignment_id,
        "Idempotency-Key": key,
        "X-Submission-Summary": summary,
        "X-Contributor-Attestation": attestation,
    }
    route = f"/api/v1/tasks/{task_id}/submission-bundle-preparations"
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        result = await _json(
            client, "POST", route, contributor_token, 202,
            headers=headers, content=archive,
        )
        if result["submission_bundle_preparation_status"] == "ready":
            _require(result["admission_id"] is not None, "ready intake omitted admission")
            return result["admission_id"]
        _require(result["admission_id"] is None, "unverified admission was public")
        await asyncio.to_thread(scan_pending_work.delay)
        await asyncio.sleep(0.5)
    raise RuntimeError("artifact verification did not produce a ready admission")


async def _assert_outcome(factory, *, project_id: UUID, task_id: str,
                          submission_id: str, contributor_id: UUID,
                          human_review_required: bool, expected_awards: int) -> dict:
    async with factory() as session:
        task = await session.get(WorkstreamTask, task_id)
        submission = await session.get(Submission, submission_id)
        _require(task.status == ("review_pending" if human_review_required else "accepted"),
                 "governed Task outcome differs")
        _require(submission is not None and submission.submission_bundle_admission_id is not None,
                 "Submission lacks consumed immutable admission")
        _require(submission.locked_post_submit_checker_policy_hash == task.locked_post_submit_checker_policy_hash,
                 "Submission POST policy differs from locked Task")
        _require(submission.contribution_policy_version_id == task.locked_contribution_policy_version_id,
                 "Submission contribution policy differs from locked Task")
        counts = {}
        for name in ("submissions", "final_acceptances", "contribution_records",
                     "compensation_awards", "reviews"):
            counts[name] = await session.scalar(text(
                f"SELECT count(*) FROM public.{name} WHERE project_id=:project"
                if name != "reviews" else
                "SELECT count(*) FROM public.reviews WHERE project_id=:project"
            ), {"project": str(project_id)})
        _require(counts == {
            "submissions": 1,
            "final_acceptances": int(not human_review_required),
            "contribution_records": int(not human_review_required),
            "compensation_awards": expected_awards,
            "reviews": 0,
        }, "governed record counts differ")
        if not human_review_required:
            row = (await session.execute(text(
                "SELECT c.contributor_id,c.submission_id,c.source_review_id,"
                "c.source_final_acceptance_id,c.source_task_assignment_id,c.artifact_hash,"
                "c.contribution_policy_version_id,f.acceptance_source "
                "FROM public.contribution_records c JOIN public.final_acceptances f "
                "ON f.id=c.source_final_acceptance_id WHERE c.project_id=:project"
            ), {"project": str(project_id)})).one()
            _require(
                str(row.contributor_id) == str(contributor_id)
                and str(row.submission_id) == submission_id
                and row.source_review_id is None
                and row.source_final_acceptance_id is not None
                and row.source_task_assignment_id is not None
                and row.artifact_hash == submission.package_hash
                and str(row.contribution_policy_version_id) == str(submission.contribution_policy_version_id)
                and row.acceptance_source == "task_post_submit_route",
                "submitter ContributionRecord lost its exact source or artifact lineage",
            )
        return counts | {"task_status": task.status}


async def _one_mode(client, factory, namespace, image, env, *, human_review_required: bool) -> dict:
    from app.workers.outbox import deliver_event

    awards = () if human_review_required else ("project_points",)
    proposal = SubmissionArtifactPolicyProposal(
        maximum_file_size_bytes=1_000_000,
        maximum_package_size_bytes=5_000_000,
        required_artifacts=("task.toml",),
        required_evidence=("results",),
        attestation_terms=("rights_confirmed",),
    )
    database_url = os.environ["WORKSTREAM_TEST_DATABASE_URL"]
    async with source_case(
        database_url, namespace=namespace, artifact_proposal=proposal,
        pre_submit_registry_spec=_locked_spec("pre_submit", image),
        post_submit_registry_spec=_locked_spec("post_submit", image),
    ) as (values, _, compilation, manager, grant):
        await seed_selected_review_revision_inputs(
            factory, compilation, manager,
            human_review_required=human_review_required,
        )
        _, derived = await prepare_post_policy(
            factory, compilation, manager, grant, service_actor(values)
        )
        approved = await operate(
            factory, manager, compilation.project_id, grant, "approve",
            PostPolicyApproval(target=derived.target, idempotency_key=uuid4()),
        )
        _, policy = await publish_policy(
            factory, compilation.project_id, contribution_awards=awards
        )
        activation = await activation_command(factory, approved, policy)
        async with factory() as session:
            draft = await session.get(ProjectGuide, guide_id := str(compilation.guide_id))
            _require(draft is not None and draft.status == "draft"
                     and draft.activation_operation_id is None,
                     "guide setup did not leave a draft for public activation")
        contributor, _ = await seed_review_actor(
            factory, compilation.project_id, role="submitter"
        )
        manager_token, contributor_token = _token(env, manager), _token(env, contributor)
        project_id = str(compilation.project_id)
        activation_path = f"/api/v1/projects/{project_id}/guides/{guide_id}/activate"
        body = activation.model_dump(mode="json", exclude={"idempotency_key"})
        activation_headers = {"Idempotency-Key": str(activation.idempotency_key)}
        activated = await _json(
            client, "POST", activation_path, manager_token, 200,
            headers=activation_headers, json=body,
        )
        _require(activated["prior_project_status"] == "draft"
                 and activated["command"]["target"]["proposal"]["guide_id"] == guide_id,
                 "public activation receipt lacks the draft guide lineage")
        async with factory() as session:
            bound = await session.get(ProjectGuide, guide_id)
            _require(bound is not None and bound.status == "active"
                     and str(bound.activation_operation_id) == activated["operation_id"],
                     "public activation did not bind the guide")
        replay = await _json(
            client, "POST", activation_path, manager_token, 200,
            headers=activation_headers, json=body,
        )
        _require(replay == activated, "public activation replay changed receipt")

        from tests.test_tasks import complete_task_payload

        created = await _json(
            client, "POST", f"/api/v1/projects/{project_id}/tasks", manager_token, 201,
            headers={"Idempotency-Key": str(uuid4())}, json=complete_task_payload(),
        )
        task_id = created["id"]
        for operation in ("screen", "release"):
            await _json(
                client, "POST", f"/api/v1/tasks/{task_id}/{operation}",
                manager_token, 200, headers={"Idempotency-Key": str(uuid4())},
                json={"reason": "Public first journey"},
            )
        claimed = await _json(
            client, "POST", f"/api/v1/tasks/{task_id}/claim", contributor_token,
            200, headers={"Idempotency-Key": str(uuid4())},
        )
        assignment_id = claimed["assignment"]["id"]
        await _json(
            client, "POST", f"/api/v1/tasks/{task_id}/start", contributor_token,
            200, headers={"Idempotency-Key": str(uuid4())},
        )
        await _json(
            client, "GET", f"/api/v1/tasks/{task_id}/submission-requirements",
            contributor_token, 200,
        )

        archive = archive_with_modes("evidence/results", compilation.project_id)
        summary = "Completed the governed task with required evidence."
        attestation = (
            "I confirm no confidential client data, credentials, or copied source "
            "material is included in this submission; rights_confirmed."
        )
        bad = await _json(
            client, "POST", f"/api/v1/tasks/{task_id}/submission-bundle-preparations",
            contributor_token, 422,
            headers={
                "Content-Type": "application/zip",
                "X-Task-Assignment-Id": assignment_id,
                "Idempotency-Key": str(uuid4()),
                "X-Submission-Summary": summary,
                "X-Contributor-Attestation": attestation,
            },
            content=_secret_archive(archive),
        )
        _require(bad["error"]["code"] == "pre_submission_checker_failed",
                 "public intake did not return checker feedback")
        async with factory() as session:
            _require(await session.scalar(select(func.count()).select_from(Submission).where(
                Submission.task_id == task_id
            )) == 0, "failed intake created a Submission")

        admission_id = await _ready_admission(
            client, factory, task_id, assignment_id, contributor_token,
            archive, summary, attestation,
        )
        submission_path = f"/api/v1/tasks/{task_id}/submissions"
        packet = {
            "assignment_id": assignment_id,
            "admission_id": admission_id,
            "predecessor_submission_id": None,
            "summary": summary,
            "contributor_attestation": attestation,
        }
        saved = await _json(
            client, "POST", submission_path, contributor_token, 201, json=packet
        )
        repeated = await _json(
            client, "POST", submission_path, contributor_token, 201, json=packet
        )
        _require(saved == repeated, "public Submission replay changed receipt")
        _require(saved["admission_id"] == admission_id, "Submission consumed another admission")
        history = await _json(client, "GET", submission_path, contributor_token, 200)
        _require([item["id"] for item in history["items"]] == [saved["submission_id"]],
                 "public submission history differs")

        async with factory() as session:
            dispatch = await session.get(SubmissionDispatch, saved["submission_id"])
            _require(dispatch is not None, "atomic Submission dispatch is absent")
            request_event_id = dispatch.evaluation_event_id
            attempt_id = dispatch.evaluation_attempt_id
        await _deliver(factory, request_event_id, compilation.project_id)
        async with factory() as session:
            run = await session.get(CheckerRun, attempt_id)
            _require(run.status == "completed" and run.completion_event_id is not None,
                     "selected POST did not retain completion")
            completion_id = run.completion_event_id
        await _deliver(factory, completion_id, compilation.project_id)
        outcome = await _assert_outcome(
            factory, project_id=compilation.project_id, task_id=task_id,
            submission_id=saved["submission_id"],
            contributor_id=contributor.actor_profile_id,
            human_review_required=human_review_required,
            expected_awards=len(awards),
        )
        if not human_review_required:
            exported = await _json(
                client, "GET", "/api/v1/actors/me/contributions",
                contributor_token, 200,
                params={"project_id": project_id},
            )
            _require(len(exported["items"]) == 1, "public self contribution is absent")
            item = exported["items"][0]
            _require(item["submission_id"] == saved["submission_id"]
                     and item["acceptance_source"] == "task_post_submit_route"
                     and len(item["awards"]) == len(awards),
                     "public contribution source or award set differs")
        # Retained outbox outcome must be stable after a duplicate real broker delivery.
        await asyncio.to_thread(deliver_event.apply_async,
                                args=(str(completion_id), project_id))
        await asyncio.sleep(0.5)
        again = await _assert_outcome(
            factory, project_id=compilation.project_id, task_id=task_id,
            submission_id=saved["submission_id"],
            contributor_id=contributor.actor_profile_id,
            human_review_required=human_review_required,
            expected_awards=len(awards),
        )
        _require(again == outcome, "duplicate completion changed governed outcome")
        return {
            "project_id": project_id,
            "task_id": task_id,
            "submission_id": saved["submission_id"],
            "review_mode": "human" if human_review_required else "automatic",
            "intake_failure_code": bad["error"]["code"],
            "selected_pre_runs": await _pre_runs(factory, task_id),
            "selected_post_attempt_id": str(attempt_id),
            "outcome": outcome,
        }


async def _pre_runs(factory, task_id: str) -> list[str]:
    async with factory() as session:
        return list(await session.scalars(select(SelectedPreSubmitRun.status).where(
            SelectedPreSubmitRun.task_id == task_id
        ).order_by(SelectedPreSubmitRun.queued_at)))


async def run(database_url: str, image_reference: str, service_binary: Path,
              broker_url: str, root: Path) -> dict:
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    image = _image_identity(image_reference)
    bucket = os.environ["WORKSTREAM_TEST_MINIO_BUCKET"]
    prefix = os.environ["WORKSTREAM_TEST_MINIO_PREFIX"]
    scratch = root / "scratch"
    socket_root = root / "service"
    scratch.mkdir(mode=0o700)
    socket_root.mkdir(mode=0o700)
    socket_path = socket_root / "checker.sock"
    settings = minio_settings(private_prefix=prefix).model_copy(update={
        "artifact_s3_bucket": bucket,
        "artifact_scratch_root": scratch,
        "artifact_scratch_minimum_free_bytes": 0,
        "external_checker_service_socket": socket_path,
        "external_checker_material_root": scratch,
        "external_checker_service_timeout_seconds": 90.0,
    })
    create_artifact_scratch_manager(settings).close()
    bootstrap = create_artifact_store_bootstrap(settings)
    namespace = artifact_storage_namespace_spec(settings, bootstrap)
    bootstrap.close()
    service_config = {
        "socket_path": str(socket_path), "material_root": str(scratch),
        "docker_binary": "/usr/bin/docker", "runtime": "runc",
        "isolation_mode": "docker-dev", "operating_system": image["operating_system"],
        "architecture": image["architecture"], "sandbox_uid": os.getuid(),
        "sandbox_gid": os.getgid(), "cache": [image],
    }
    config_path = socket_root / "service.json"
    config_path.write_text(json.dumps(service_config, separators=(",", ":")))

    os.environ["WORKSTREAM_E2E_FLOW_ISSUER"] = "https://identity.flowresearch.tech"
    env = api_environment()
    env.update({
        "WORKSTREAM_DATABASE_URL": database_url,
        "WORKSTREAM_E2E_FLOW_ISSUER": "https://identity.flowresearch.tech",
        "WORKSTREAM_FLOW_AUTH_ISSUER": "https://identity.flowresearch.tech",
        "WORKSTREAM_CELERY_BROKER_URL": broker_url,
        "WORKSTREAM_CELERY_RESULT_BACKEND_URL": broker_url,
        "WORKSTREAM_CELERY_TASK_ALWAYS_EAGER": "false",
        "WORKSTREAM_ARTIFACT_SCRATCH_ROOT": str(scratch),
        "WORKSTREAM_ARTIFACT_SCRATCH_MINIMUM_FREE_BYTES": "0",
        "WORKSTREAM_EXTERNAL_CHECKER_SERVICE_SOCKET": str(socket_path),
        "WORKSTREAM_EXTERNAL_CHECKER_MATERIAL_ROOT": str(scratch),
        "WORKSTREAM_EXTERNAL_CHECKER_SERVICE_TIMEOUT_SECONDS": "90",
        "PYTHONPATH": str(BACKEND),
    })
    env.pop("OPENAI_API_KEY", None)
    # Owner fixture calls and broker publication in this process use the same
    # isolated database and provider settings as the API and worker children.
    for key, value in env.items():
        if key.startswith("WORKSTREAM_"):
            os.environ[key] = value
    os.environ.pop("OPENAI_API_KEY", None)
    get_settings.cache_clear()
    runtime_settings = get_settings()
    for field in (
        "artifact_store_backend", "artifact_s3_provider_profile", "artifact_s3_region",
        "artifact_s3_endpoint_url", "artifact_s3_bucket", "artifact_s3_private_prefix",
        "artifact_s3_addressing_style", "artifact_s3_credential_mode",
        "artifact_s3_access_key_id", "artifact_s3_secret_access_key",
    ):
        _require(getattr(runtime_settings, field) == getattr(settings, field),
                 "API/worker artifact provider configuration differs from fixture")
    runtime_bootstrap = create_artifact_store_bootstrap(runtime_settings)
    try:
        runtime_namespace = artifact_storage_namespace_spec(
            runtime_settings, runtime_bootstrap
        )
    finally:
        runtime_bootstrap.close()
    _require(runtime_namespace.namespace_fingerprint == namespace.namespace_fingerprint,
             "API/worker artifact namespace differs from approved fixture")

    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    rust = api = worker = None
    try:
        await provision_material_services(factory, artifacts=True, checker=True)
        await provision_router(factory)
        await provision_reconciler(factory)
        await _provision_runtime_services(factory)
        operator, _ = await seed_review_actor(factory, None, role="operator", scope="system")
        from tests.reviews.lifecycle.transition_support import command_for, transition
        await transition(await command_for(operator.actor_profile_id, "shadow"))
        await transition(await command_for(operator.actor_profile_id, "live"))

        rust = _start_service(service_binary, config_path, socket_path)
        await _wait_service(rust, socket_path)
        port = find_free_port()
        origin = f"http://127.0.0.1:{port}"
        api = _process([
            sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1", "--port", str(port),
            "--log-level", "error", "--no-access-log",
        ], env=env, log=root / "api.log")
        await _wait_api(origin, api)
        hostname = f"first-journey-{uuid4().hex}@localhost"
        worker = _process([
            sys.executable, "-m", "celery", "-A", "app.workers.celery_app",
            "worker", "--pool=prefork", "--concurrency=1",
            "--queues=celery,workstream.outbox", "--hostname", hostname,
            "--without-gossip", "--without-mingle", "--without-heartbeat",
            "--loglevel=ERROR",
        ], env=env, log=root / "worker.log")
        await _wait_worker(worker, hostname)
        async with httpx.AsyncClient(base_url=origin, timeout=90) as client:
            true = await _one_mode(client, factory, namespace, image, env,
                                   human_review_required=True)
            false = await _one_mode(client, factory, namespace, image, env,
                                    human_review_required=False)
        _require(api.poll() is None and worker.poll() is None,
                 "API or prefork worker exited during public journey")
        return {"tree_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=BACKEND
        ).strip(), "runtime": "runc/docker-dev", "image_digest": image["platform_manifest_digest"],
                "public_api": True, "prefork_worker": True,
                "scripted_approved_guide_precondition": True,
                "human": true, "automatic": false}
    finally:
        _stop_process(worker)
        _stop_process(api)
        if rust is not None:
            _stop_service(rust)
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.environ.get("WORKSTREAM_TEST_DATABASE_URL"))
    parser.add_argument("--image-reference", required=True)
    parser.add_argument("--service-binary", required=True, type=Path)
    parser.add_argument("--broker-url", required=True)
    parser.add_argument("--work-dir", type=Path,
                        help="Unique private directory retaining API and worker diagnostics")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("isolated --database-url or WORKSTREAM_TEST_DATABASE_URL is required")
    workspace = (nullcontext(args.work_dir) if args.work_dir else
                 tempfile.TemporaryDirectory(prefix="ws-pilot04-public-"))
    with workspace as directory:
        value = asyncio.run(run(
            args.database_url, args.image_reference, args.service_binary,
            args.broker_url, Path(directory),
        ))
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
