"""Exercise the public first journey after a scripted, approved guide precondition.

Run only through the isolated database/MinIO runner with a disposable Redis broker.
The source compilation is a canonical owner fixture, not a model-provider run.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import nullcontext
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import hmac
from io import BytesIO
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from uuid import UUID, uuid4
from zipfile import ZipFile, ZipInfo

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.artifacts import (
    create_artifact_store_bootstrap,
)
from app.core.config import get_settings
from app.core.identifiers import new_record_id
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.actors.api.service_identities import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.checkers.models import CheckerRun, SelectedPreSubmitRun
from app.modules.checkers.execution_repository import stored_result
from app.modules.outbox.models import OutboxDeliveryAttempt, OutboxEvent
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
from tests.tasks.post_submit_routing.support import revision_archive
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


def _settings_digests(settings, nonce: bytes) -> dict[str, str]:
    """Compare every resolved setting across processes without exposing values."""
    values = settings.model_dump(mode="json")
    for name in (
        "api_rate_limit_key_secret", "pagination_cursor_hmac_secret",
        "artifact_s3_access_key_id", "artifact_s3_secret_access_key",
        "artifact_s3_session_token",
    ):
        secret = getattr(settings, name)
        values[name] = None if secret is None else secret.get_secret_value()
    return {
        name: hmac.new(
            nonce, json.dumps(value, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        for name, value in values.items()
    }


def _celery_config_mismatches(settings) -> list[str]:
    from app.workers.celery_app import celery_app

    expected = {
        "celery_broker_url": settings.celery_broker_url,
        "celery_result_backend_url": settings.celery_result_backend_url,
        "celery_task_always_eager": settings.celery_task_always_eager,
    }
    actual = {
        "celery_broker_url": celery_app.conf.broker_url,
        "celery_result_backend_url": celery_app.conf.result_backend,
        "celery_task_always_eager": celery_app.conf.task_always_eager,
    }
    return [name for name in expected if expected[name] != actual[name]]


def _verify_child_configuration(role: str) -> int:
    """Import the same API or worker entry point and report only mismatched keys."""
    request = json.load(sys.stdin)
    nonce = bytes.fromhex(request["nonce"])
    if role == "api":
        from app.main import app

        actual = app.state.settings
    else:
        from app.workers.celery_app import celery_app  # noqa: F401

        actual = get_settings()
    observed = _settings_digests(actual, nonce)
    expected = request["expected"]
    mismatches = sorted(
        name for name in expected.keys() | observed.keys()
        if expected.get(name) != observed.get(name)
    )
    if role == "worker":
        mismatches.extend(_celery_config_mismatches(actual))
    print(json.dumps(sorted(set(mismatches)), separators=(",", ":")))
    return 0


def _preflight_children(settings, env: dict[str, str], root: Path) -> None:
    """Reject API/worker drift before starting real services or public requests."""
    nonce = os.urandom(32)
    request = json.dumps({
        "nonce": nonce.hex(), "expected": _settings_digests(settings, nonce),
    })
    for role in ("api", "worker"):
        with (root / f"preflight-{role}.log").open("wb") as errors:
            result = subprocess.run(
                [
                    sys.executable, "-c",
                    "import sys; sys.path.extend(sys.argv[1:3]); "
                    "from experiments.pilot04_external_checker_runtime."
                    "run_public_journey_probe import _verify_child_configuration; "
                    "raise SystemExit(_verify_child_configuration(sys.argv[3]))",
                    str(BACKEND.parent), str(BACKEND / "tests"), role,
                ],
                cwd=BACKEND, env=env, input=request, text=True,
                stdout=subprocess.PIPE, stderr=errors, timeout=300, check=False,
            )
        _require(result.returncode == 0,
                 f"{role} configuration preflight failed; see private diagnostics")
        try:
            mismatches = json.loads(result.stdout)
        except ValueError as exc:
            raise RuntimeError(f"{role} configuration preflight returned invalid evidence") from exc
        _require(not mismatches,
                 f"{role} configuration differs from parent: {', '.join(mismatches)}")


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
    deadline = time.monotonic() + 120
    async with httpx.AsyncClient(timeout=2) as client:
        while time.monotonic() < deadline:
            _require(process.poll() is None, "public API exited before readiness")
            try:
                if (await client.get(origin + "/api/v1/health")).status_code == 200:
                    return
            except httpx.TransportError:
                pass
            await asyncio.sleep(0.25)
    raise RuntimeError("public API did not become ready")


async def _wait_worker(process: subprocess.Popen, hostname: str) -> None:
    from app.workers.celery_app import celery_app

    deadline = time.monotonic() + 120
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


def _with_fixture_file(archive: bytes, name: str) -> bytes:
    """Add a deterministic project-rule marker without changing valid packet members."""
    output = BytesIO(archive)
    with ZipFile(output, "a") as target:
        target.writestr(
            ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)),
            b"sample project rule marker\n",
        )
    return output.getvalue()


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


async def _seed_contributor(factory) -> ActorIdentityFacts:
    """Create a Flow-linked human without an administrator role grant."""
    actor = ActorIdentityFacts(new_record_id(), new_record_id(), ActorKind.HUMAN)
    async with factory() as session, session.begin():
        session.add(ActorProfile(
            id=str(actor.actor_profile_id), actor_kind="human", status="active",
            provisioning_method="automatic_first_access", created_by="public-probe-fixture",
        ))
        await session.flush()
        session.add(ActorIdentityLink(
            id=str(actor.identity_link_id), actor_profile_id=str(actor.actor_profile_id),
            issuer="https://identity.flowresearch.tech",
            subject=str(actor.actor_profile_id), subject_kind="human",
            status="active", linked_by="public-probe-fixture",
            last_verified_at=datetime.now(UTC),
        ))
    return actor


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


async def _deliver_known_retry(factory, event_id: UUID, project_id: UUID,
                               task_id: str, submission_id: str) -> None:
    from app.workers.outbox import deliver_event

    await asyncio.to_thread(
        deliver_event.apply_async, args=(str(event_id), str(project_id)),
    )
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        async with factory() as session:
            event = await session.get(OutboxEvent, event_id)
            if event.delivery_state == "retryable":
                attempt = await session.get(
                    OutboxDeliveryAttempt, (event_id, event.attempt_count)
                )
                receipt = json.loads(attempt.outcome_json)
                _require(event.attempt_count == 1
                         and event.last_error_code == "RETRY_REQUESTED"
                         and receipt["delivery_state"] == "retryable"
                         and receipt["error_code"] == "RETRY_REQUESTED"
                         and receipt["invocation_unknown"] is False
                         and event.next_attempt_at is not None,
                         "non-live completion did not record one known safe retry")
                task = await session.get(WorkstreamTask, task_id)
                submission = await session.get(Submission, submission_id)
                _require(task.status == "evaluation_pending"
                         and submission.status == "submitted",
                         "non-live completion changed Task or Submission")
                for table in ("task_post_submit_routing_requests",
                              "task_post_submit_routing_manifests", "final_acceptances",
                              "contribution_records", "compensation_awards", "reviews"):
                    count = await session.scalar(text(
                        f"SELECT count(*) FROM public.{table} WHERE project_id=:project"
                    ), {"project": str(project_id)})
                    _require(count == 0, "non-live retry committed governed effects")
                _require(await session.scalar(text(
                    "SELECT count(*) FROM public.audit_events "
                    "WHERE project_id=:project AND action_id='task.post_submit.route'"
                ), {"project": str(project_id)}) == 0,
                         "non-live retry retained routing authorization")
                return
            if event.delivery_state in {"acknowledged", "dead_letter", "cancelled"}:
                raise RuntimeError("non-live completion escaped the safe retry path")
        await asyncio.sleep(0.3)
    raise RuntimeError("non-live completion did not settle into retryable")


async def _wait_outbox_due(factory, event_id: UUID) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        async with factory() as session:
            due = await session.scalar(text(
                "SELECT clock_timestamp() >= next_attempt_at "
                "FROM public.outbox_events WHERE event_id=:event"
            ), {"event": str(event_id)})
        if due:
            return
        await asyncio.sleep(0.2)
    raise RuntimeError("known safe outbox retry did not become due")


async def _ready_admission(client, factory, task_id: str, assignment_id: str,
                           contributor_token: str, archive: bytes, summary: str,
                           attestation: str, predecessor_id: str | None = None) -> str:
    from app.workers.artifacts import scan_pending_work

    key = str(uuid4())
    headers = {
        "Content-Type": "application/zip",
        "X-Task-Assignment-Id": assignment_id,
        "Idempotency-Key": key,
        "X-Submission-Summary": summary,
        "X-Contributor-Attestation": attestation,
    }
    if predecessor_id is not None:
        headers["X-Predecessor-Submission-Id"] = predecessor_id
    route = f"/api/v1/tasks/{task_id}/submission-bundle-preparations"
    deadline = time.monotonic() + 180
    current_status = None
    status_since = time.monotonic()
    last_scan_status = None
    last_scan_at = 0.0
    while time.monotonic() < deadline:
        result = await _json(
            client, "POST", route, contributor_token, 202,
            headers=headers, content=archive,
        )
        status = result["submission_bundle_preparation_status"]
        if status == "ready":
            _require(result["admission_id"] is not None, "ready intake omitted admission")
            return result["admission_id"]
        _require(result["admission_id"] is None, "unverified admission was public")
        _require(status not in {
            "conflict", "integrity_mismatch", "missing", "absent_replay_required", "stale",
        }, f"artifact preparation ended {status}")
        if status != current_status:
            current_status = status
            status_since = time.monotonic()
        now = time.monotonic()
        # A PUT can spawn verification work without changing the public PUT
        # status. Observe one scan for ten seconds before a bounded rescan.
        if status != "put_in_flight" and (
            status != last_scan_status or now - last_scan_at >= 10
        ):
            await asyncio.to_thread(scan_pending_work.delay)
            last_scan_status = status
            last_scan_at = now
        _require(now - status_since < 60,
                 f"artifact preparation remained {status} after bounded worker scans")
        await asyncio.sleep(1)
    raise RuntimeError(f"artifact verification did not become ready from {current_status}")


async def _submit(client, factory, *, task_id: str, assignment_id: str,
                  contributor_token: str, archive: bytes, summary: str,
                  attestation: str, predecessor_id: str | None) -> dict:
    admission_id = await _ready_admission(
        client, factory, task_id, assignment_id, contributor_token,
        archive, summary, attestation, predecessor_id,
    )
    route = f"/api/v1/tasks/{task_id}/submissions"
    packet = {
        "assignment_id": assignment_id,
        "admission_id": admission_id,
        "predecessor_submission_id": predecessor_id,
        "summary": summary,
        "contributor_attestation": attestation,
    }
    saved = await _json(client, "POST", route, contributor_token, 201, json=packet)
    repeated = await _json(client, "POST", route, contributor_token, 201, json=packet)
    _require(saved == repeated, "public Submission replay changed receipt")
    _require(saved["admission_id"] == admission_id,
             "Submission consumed another admission")
    return saved


async def _complete_post(factory, *, submission_id: str,
                         project_id: UUID, recommendation: str,
                         finding_code: str | None = None,
                         deliver_completion: bool = True) -> tuple[str, UUID]:
    async with factory() as session:
        dispatch = await session.get(SubmissionDispatch, submission_id)
        _require(dispatch is not None, "atomic Submission dispatch is absent")
        request_event_id = dispatch.evaluation_event_id
        attempt_id = dispatch.evaluation_attempt_id
    await _deliver(factory, request_event_id, project_id)
    async with factory() as session:
        run = await session.get(CheckerRun, attempt_id)
        _require(run.status == "completed" and run.completion_event_id is not None,
                 "selected POST did not retain completion")
        _require(run.routing_recommendation == recommendation,
                 "selected POST recommendation differs from fixture finding")
        result = stored_result(run)
        _require(result.execution is not None,
                 "selected POST lacks completed external evidence")
        members = result.execution.external_members
        _require(len(members) == 1, "selected POST did not execute one project image")
        findings = [finding.code for finding in members[0].result.findings]
        _require(findings == ([finding_code] if finding_code else []),
                 "selected POST finding differs from fixture rule")
        completion_id = run.completion_event_id
    if deliver_completion:
        await _deliver(factory, completion_id, project_id)
    return str(attempt_id), completion_id


async def _assert_revision(factory, *, project_id: UUID, task_id: str,
                           submission_id: str, attempt_id: str) -> None:
    async with factory() as session:
        task = await session.get(WorkstreamTask, task_id)
        _require(task.status == "needs_revision",
                 "failed selected POST did not route the Task to needs_revision")
        source = await session.get(Submission, submission_id)
        _require(source is not None and source.status == "submitted",
                 "failed selected POST changed the immutable submitted source")
        manifest = (await session.execute(text(
            "SELECT submission_id,checker_run_id,routing_recommendation "
            "FROM public.task_post_submit_routing_manifests "
            "WHERE project_id=:project"
        ), {"project": str(project_id)})).one()
        _require(str(manifest.submission_id) == submission_id
                 and str(manifest.checker_run_id) == attempt_id
                 and manifest.routing_recommendation == "needs_revision",
                 "revision route lost exact failed checker lineage")
        for table in ("final_acceptances", "contribution_records",
                      "compensation_awards", "reviews"):
            count = await session.scalar(text(
                f"SELECT count(*) FROM public.{table} WHERE project_id=:project"
            ), {"project": str(project_id)})
            _require(count == 0, "revision minted final or economic evidence")


async def _assert_outcome(factory, *, project_id: UUID, task_id: str,
                          submission_id: str, initial_submission_id: str,
                          contributor_id: UUID,
                          human_review_required: bool, expected_awards: int,
                          expected_submissions: int) -> dict:
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
        dispatch = await session.get(SubmissionDispatch, submission_id)
        _require(dispatch is not None, "governed Submission lost its atomic dispatch")
        if human_review_required:
            source = await session.get(Submission, initial_submission_id)
            _require(source is not None and source.version == 1
                     and submission.version == 2
                     and submission.supersedes_submission_id == initial_submission_id
                     and submission.package_hash != source.package_hash
                     and dispatch.creation_kind == "checker_remediation"
                     and dispatch.checker_remediation_manifest_id is not None,
                     "replacement lost exact failed predecessor custody")
        counts = {}
        for name in ("submissions", "final_acceptances", "contribution_records",
                     "compensation_awards", "reviews"):
            counts[name] = await session.scalar(text(
                f"SELECT count(*) FROM public.{name} WHERE project_id=:project"
                if name != "reviews" else
                "SELECT count(*) FROM public.reviews WHERE project_id=:project"
            ), {"project": str(project_id)})
        _require(counts == {
            "submissions": expected_submissions,
            "final_acceptances": int(not human_review_required),
            "contribution_records": int(not human_review_required),
            "compensation_awards": expected_awards,
            "reviews": 0,
        }, "governed record counts differ")
        if not human_review_required:
            row = (await session.execute(text(
                "SELECT c.id,c.contributor_id,c.submission_id,c.source_review_id,"
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
            award = (await session.execute(text(
                "SELECT contribution_record_id,contributor_id,contribution_policy_version_id,"
                "instrument_type,unit_code,quantity FROM public.compensation_awards "
                "WHERE project_id=:project"
            ), {"project": str(project_id)})).one()
            _require(
                str(award.contribution_record_id) == str(row.id)
                and str(award.contributor_id) == str(contributor_id)
                and str(award.contribution_policy_version_id)
                == str(submission.contribution_policy_version_id)
                and award.instrument_type == "project_points"
                and award.unit_code == "PTS"
                and award.quantity == Decimal("7"),
                "conditional award differs from the locked contribution policy",
            )
        return counts | {"task_status": task.status}


async def _one_mode(client, factory, database_url, namespace, image, env, *,
                    human_review_required: bool, operator_id: UUID | None,
                    bootstrap_only: bool = False) -> dict:
    awards = () if human_review_required else ("project_points",)
    proposal = SubmissionArtifactPolicyProposal(
        maximum_file_size_bytes=1_000_000,
        maximum_package_size_bytes=5_000_000,
        required_artifacts=("task.toml",),
        required_evidence=("results",),
        attestation_terms=("rights_confirmed",),
    )
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
        contributor = await _seed_contributor(factory)
        if bootstrap_only:
            return {
                "review_mode": "human" if human_review_required else "automatic",
                "approved_draft": True,
                "ordinary_contributor": contributor.actor_profile_id != manager.actor_profile_id,
            }
        from app.workers.outbox import deliver_event

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

        admitted = await _json(client, "GET", "/api/v1/actors/me", contributor_token, 200)
        _require(admitted["actor_profile_id"] == str(contributor.actor_profile_id),
                 "Flow-linked contributor did not resolve to the stored human")
        role_grant = await _json(
            client, "POST", f"/api/v1/projects/{project_id}/role-grants",
            manager_token, 201,
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "target_actor_profile_id": str(contributor.actor_profile_id),
                "role": "submitter",
                "qualification": {
                    "skills_snapshot": {
                        "availability": "unavailable", "reference_ids": [],
                        "unavailable_reason": "no_record",
                    },
                    "reputation_snapshot": {
                        "availability": "unavailable", "reference_ids": [],
                        "unavailable_reason": "no_record",
                    },
                    "prior_project_work_refs": [], "external_expertise_refs": [],
                },
                "reason": "Assign this contributor to the public first-journey task",
            },
        )
        _require(role_grant["role"] == "submitter"
                 and role_grant["actor_profile_id"] == str(contributor.actor_profile_id),
                 "public project submitter grant names another actor or role")

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
        external_bad = await _json(
            client, "POST", f"/api/v1/tasks/{task_id}/submission-bundle-preparations",
            contributor_token, 422,
            headers={
                "Content-Type": "application/zip",
                "X-Task-Assignment-Id": assignment_id,
                "Idempotency-Key": str(uuid4()),
                "X-Submission-Summary": summary,
                "X-Contributor-Attestation": attestation,
            },
            content=_with_fixture_file(archive, "project-rejected.txt"),
        )
        results = external_bad["error"]["details"]["results"]
        external = [item for item in results
                    if item["source"] == "project_external_checker"]
        _require(external_bad["error"]["code"] == "pre_submission_checker_failed"
                 and len(external) == 1 and external[0]["status"] == "failed"
                 and [finding["code"] for finding in external[0]["findings"]]
                 == ["probe.project_rule_failed"]
                 and all(item.get("failure_code") is None for item in results
                         if item["source"] == "workstream_default"),
                 "public external PRE rejection did not preserve passing defaults")
        async with factory() as session:
            _require(await session.scalar(select(func.count()).select_from(Submission).where(
                Submission.task_id == task_id
            )) == 0, "failed intake created a Submission")

        first_archive = (_with_fixture_file(archive, "post-rejected.txt")
                         if human_review_required else archive)
        saved = await _submit(
            client, factory, task_id=task_id, assignment_id=assignment_id,
            contributor_token=contributor_token, archive=first_archive,
            summary=summary, attestation=attestation, predecessor_id=None,
        )
        submission_path = f"/api/v1/tasks/{task_id}/submissions"
        history = await _json(client, "GET", submission_path, contributor_token, 200)
        _require([item["id"] for item in history["items"]] == [saved["submission_id"]],
                 "public submission history differs")
        first_submission_id = saved["submission_id"]
        first_attempt_id, completion_id = await _complete_post(
            factory, submission_id=first_submission_id,
            project_id=compilation.project_id,
            recommendation="needs_revision" if human_review_required else "allow_review",
            finding_code="probe.post_rule_failed" if human_review_required else None,
            deliver_completion=human_review_required,
        )
        attempt_id = first_attempt_id
        if human_review_required:
            await _assert_revision(
                factory, project_id=compilation.project_id,
                task_id=task_id, submission_id=first_submission_id,
                attempt_id=first_attempt_id,
            )
            saved = await _submit(
                client, factory, task_id=task_id, assignment_id=assignment_id,
                contributor_token=contributor_token,
                archive=revision_archive(archive), summary=summary,
                attestation=attestation, predecessor_id=first_submission_id,
            )
            _require(saved["submission_version"] == 2,
                     "public checker remediation did not create version 2")
            history = await _json(client, "GET", submission_path, contributor_token, 200)
            _require([item["id"] for item in history["items"]]
                     == [first_submission_id, saved["submission_id"]],
                     "public revision history lost exact predecessor order")
            attempt_id, completion_id = await _complete_post(
                factory, submission_id=saved["submission_id"],
                project_id=compilation.project_id, recommendation="allow_review",
            )
        else:
            await _deliver_known_retry(
                factory, completion_id, compilation.project_id,
                task_id, first_submission_id,
            )
            from tests.reviews.lifecycle.transition_support import command_for, transition
            await transition(await command_for(operator_id, "live"))
            await _wait_outbox_due(factory, completion_id)
            await _deliver(factory, completion_id, compilation.project_id)
            async with factory() as session:
                event = await session.get(OutboxEvent, completion_id)
                _require(event.delivery_state == "acknowledged"
                         and event.attempt_count == 2,
                         "known safe retry did not commit once after authorized live transition")
        outcome = await _assert_outcome(
            factory, project_id=compilation.project_id, task_id=task_id,
            submission_id=saved["submission_id"], initial_submission_id=first_submission_id,
            contributor_id=contributor.actor_profile_id,
            human_review_required=human_review_required,
            expected_awards=len(awards),
            expected_submissions=2 if human_review_required else 1,
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
                     and [(award["instrument"], award["unit"], Decimal(award["quantity"]))
                     for award in item["awards"]] == [("project_points", "PTS", Decimal("7"))],
                     "public contribution source or award set differs")
        # Retained outbox outcome must be stable after a duplicate real broker delivery.
        await asyncio.to_thread(deliver_event.apply_async,
                                args=(str(completion_id), project_id))
        await asyncio.sleep(0.5)
        again = await _assert_outcome(
            factory, project_id=compilation.project_id, task_id=task_id,
            submission_id=saved["submission_id"], initial_submission_id=first_submission_id,
            contributor_id=contributor.actor_profile_id,
            human_review_required=human_review_required,
            expected_awards=len(awards),
            expected_submissions=2 if human_review_required else 1,
        )
        _require(again == outcome, "duplicate completion changed governed outcome")
        return {
            "project_id": project_id,
            "task_id": task_id,
            "submission_id": saved["submission_id"],
            "initial_submission_id": first_submission_id,
            "review_mode": "human" if human_review_required else "automatic",
            "intake_failure_code": bad["error"]["code"],
            "external_pre_failure_code": "probe.project_rule_failed",
            "selected_pre_runs": await _pre_runs(factory, task_id),
            "selected_post_attempt_ids": (
                [first_attempt_id, attempt_id] if human_review_required else [attempt_id]
            ),
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
    issuer, audience, flow_secret = flow_settings(env)
    _require(runtime_settings.database_url == database_url,
             "API/worker database differs from isolated fixture")
    _require(runtime_settings.flow_auth_issuer == issuer
             and runtime_settings.flow_auth_audience == audience
             and runtime_settings.flow_auth_local_hmac_secret == flow_secret,
             "API Flow verifier differs from local test signer")
    _require(runtime_settings.api_rate_limit_key_secret is not None
             and runtime_settings.pagination_cursor_hmac_secret is not None,
             "API rate/cursor signing configuration is absent")
    _require(runtime_settings.celery_broker_url == broker_url
             and runtime_settings.celery_task_always_eager is False,
             "worker broker configuration is not durable")
    _require(runtime_settings.artifact_scratch_root == scratch
             and runtime_settings.artifact_scratch_minimum_free_bytes == 0
             and runtime_settings.external_checker_service_socket == socket_path
             and runtime_settings.external_checker_material_root == scratch,
             "API/worker scratch or checker service configuration differs from fixture")
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
    parent_celery_mismatches = _celery_config_mismatches(runtime_settings)
    _require(not parent_celery_mismatches,
             "parent broker configuration differs from resolved Settings: "
             + ", ".join(parent_celery_mismatches))
    _preflight_children(runtime_settings, env, root)

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
            true = await _one_mode(client, factory, database_url, namespace, image, env,
                                   human_review_required=True,
                                   operator_id=operator.actor_profile_id)
            false = await _one_mode(client, factory, database_url, namespace, image, env,
                                    human_review_required=False,
                                    operator_id=operator.actor_profile_id)
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


async def _fixture_bootstrap_only(database_url: str) -> dict:
    """Check both actual guide setup fixtures before the costly runtime launch."""
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        # Registry custody validates the digest shape; no image is executed here.
        image = {"platform_manifest_digest": "sha256:" + "0" * 64}
        true = await _one_mode(
            None, factory, database_url, None, image, None,
            human_review_required=True, operator_id=None, bootstrap_only=True,
        )
        false = await _one_mode(
            None, factory, database_url, None, image, None,
            human_review_required=False, operator_id=None, bootstrap_only=True,
        )
        _require(true["ordinary_contributor"] and false["ordinary_contributor"],
                 "fixture contributor has manager identity")
        return {"fixture_bootstrap_only": True, "human": true, "automatic": false}
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.environ.get("WORKSTREAM_TEST_DATABASE_URL"))
    parser.add_argument("--image-reference")
    parser.add_argument("--service-binary", type=Path)
    parser.add_argument("--broker-url")
    parser.add_argument("--fixture-bootstrap-only", action="store_true")
    parser.add_argument("--work-dir", type=Path,
                        help="Unique private directory retaining API and worker diagnostics")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("isolated --database-url or WORKSTREAM_TEST_DATABASE_URL is required")
    if args.fixture_bootstrap_only:
        print(json.dumps(asyncio.run(_fixture_bootstrap_only(args.database_url)),
                         sort_keys=True, separators=(",", ":")))
        return 0
    if not args.image_reference or not args.service_binary or not args.broker_url:
        parser.error("full drill requires image, service binary, and broker URL")
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
