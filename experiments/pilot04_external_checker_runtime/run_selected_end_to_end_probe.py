"""Run selected PRE, atomic Submission and selected POST through one Rust service."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import tempfile
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from aiobotocore.config import AioConfig
from aiobotocore.session import AioSession
from sqlalchemy import func, select, text
from starlette.requests import Request

from app.adapters.artifacts import (
    artifact_preparation_limits,
    create_artifact_scratch_manager,
    get_submission_bundle_preparation_command,
)
from app.adapters.checkers import external_checker_execution_factory
from app.adapters.outbox import production_outbox_delivery
from app.adapters.artifacts.internal_workers import shutdown_artifact_internal_runtime
from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.core.identifiers import new_record_id
from app.modules.actors.api.service_identities import ServiceIdentity
from app.modules.artifacts.api import (
    SubmissionBundlePreparationCheckFailed,
    SubmissionBundlePreparationInfrastructureUnavailable,
    SubmissionBundlePreparationRequest,
    SubmissionBundlePreparationStatus,
)
from app.modules.artifacts.models import (
    ArtifactVerificationJob,
    SubmissionBundleAdmission,
)
from app.modules.artifacts.service import ArtifactStorageOrchestrator
from app.modules.artifacts.authorization import (
    PreparedArtifactInternalAuthority,
    PreparedSubmissionBundlePreparationAuthorization,
)
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.checkers.api.external import ExternalCheckerRegistrySpec
from app.modules.checkers.models import CheckerRun, SelectedPreSubmitRun
from app.modules.tasks.api import SubmissionCreationRequest
from app.modules.tasks.models import Submission, SubmissionDispatch, WorkstreamTask
from experiments.pilot04_external_checker_runtime.run_probe import _image_identity
from tests.artifact_store_helpers import artifact_admission_limit_settings
from app.modules.checkers.execution_repository import stored_result
from tests.authorization.post_submit_routing.support import provision_router
from tests.tasks.evaluation_delivery.support import delivery_fixture, outcome
from tests.tasks.post_submit_routing.outcome_support import outcome_snapshot
from tests.checkers.external.test_selected_post_submit import _post_spec
from tests.checkers.external.test_selected_pre_submit import _policy
from tests.archive_fixtures import byte_source
from tests.post_submit_materialization_helpers import material_fixture
from tests.tasks.lineage_fixtures import seed_started_task_for_artifact_test
from tests.test_s3_artifact_store import (
    MINIO_ACCESS_KEY,
    MINIO_ENDPOINT,
    MINIO_REGION,
    MINIO_SECRET_KEY,
    minio_settings,
)


def _locked_spec(phase: str, image: dict[str, str]) -> ExternalCheckerRegistrySpec:
    source = _policy().entries[0].registry if phase == "pre_submit" else _post_spec()
    values = source.model_dump(
        mode="json",
        exclude={
            "registry_entry_id",
            "entry_digest",
            "registration_operation_id",
            "registered_by_actor_profile_id",
            "authorization_decision_event_id",
            "created_at",
        },
    )
    values["image_digest"] = image["platform_manifest_digest"]
    values["resources"] |= {"deadline_ms": 30_000, "maximum_output_bytes": 8_192}
    return ExternalCheckerRegistrySpec.model_validate(values)


async def _bucket_client():
    session = AioSession()
    session.set_credentials(MINIO_ACCESS_KEY, MINIO_SECRET_KEY)
    return session.create_client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        region_name=MINIO_REGION,
        config=AioConfig(s3={"addressing_style": "path"}),
    )


async def _delete_bucket(bucket: str) -> None:
    async with await _bucket_client() as client:
        values = await client.list_objects_v2(Bucket=bucket)
        objects = [{"Key": item["Key"]} for item in values.get("Contents", ())]
        if objects:
            await client.delete_objects(Bucket=bucket, Delete={"Objects": objects})
        await client.delete_bucket(Bucket=bucket)


def _secret_archive(source: bytes) -> bytes:
    """Preserve the valid packet while introducing one known private key."""
    output = BytesIO()
    with ZipFile(BytesIO(source)) as existing, ZipFile(output, "w") as target:
        for item in existing.infolist():
            value = existing.read(item)
            if item.filename == "task.toml":
                value += b"\n-----BEGIN OPENSSH PRIVATE KEY-----\nencoded\n"
            copy = ZipInfo(item.filename, date_time=(1980, 1, 1, 0, 0, 0))
            copy.create_system, copy.external_attr = (
                item.create_system,
                item.external_attr,
            )
            target.writestr(copy, value)
    return output.getvalue()


async def _prepare(fixture, settings, request):
    """Enter the actual hidden PRE composition with no owner bypass."""
    http = Request(
        {
            "type": "http",
            "headers": [],
            "app": SimpleNamespace(state=SimpleNamespace(settings=settings)),
        }
    )
    async with fixture.factory() as session:
        authority = PreparedArtifactInternalAuthority(
            session,
            service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            request_id=new_record_id(),
            correlation_id=new_record_id(),
        )
        return await get_submission_bundle_preparation_command(
            http,
            session,
            authority,
            PreparedSubmissionBundlePreparationAuthorization(
                session, fixture.actor_context
            ),
        ).prepare(request)


async def _prove_work_failure(fixture, settings) -> dict[str, object]:
    """A default-check failure leaves a separate Task in progress."""
    task_id, assignment_id = new_record_id(), new_record_id()
    params = {
        "task": str(task_id),
        "assignment": str(assignment_id),
        "project": str(fixture.facts.project_id),
        "actor": str(fixture.actor_context.actor_profile_id),
    }
    async with fixture.engine.begin() as connection:
        await seed_started_task_for_artifact_test(connection, params)
    request = SubmissionBundlePreparationRequest(
        actor=ActorIdentityFacts(
            fixture.actor_context.actor_profile_id,
            fixture.actor_context.identity_link_id,
            ActorKind.HUMAN,
        ),
        request_id=new_record_id(),
        correlation_id=new_record_id(),
        task_id=task_id,
        assignment_id=assignment_id,
        predecessor_submission_id=None,
        idempotency_key=new_record_id(),
        summary=fixture.creation_request.summary,
        contributor_attestation=fixture.creation_request.contributor_attestation,
        media_type="application/zip",
        byte_source=byte_source(_secret_archive(fixture.data)),
    )
    try:
        await _prepare(fixture, settings, request)
    except SubmissionBundlePreparationCheckFailed as error:
        codes = tuple(
            check.failure_code
            for check in error.facts.workstream_default.checks
            if check.failure_code is not None
        )
    else:
        raise RuntimeError("secret-bearing input unexpectedly passed selected PRE")
    async with fixture.factory() as session:
        task = await session.get(WorkstreamTask, str(task_id))
        submissions = await session.scalar(select(func.count()).select_from(Submission))
    if task.status != "in_progress" or submissions != 1:
        raise RuntimeError("work finding created a Submission or advanced its Task")
    return {
        "task_id": str(task_id),
        "failure_codes": codes,
        "submission_count": submissions,
    }


def _start_service(binary: Path, config_path: Path, socket_path: Path):
    """Start only the private checker service and wait for its UDS endpoint."""
    socket_path.unlink(missing_ok=True)
    return subprocess.Popen(
        [str(binary), str(config_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


async def _wait_service(service, socket_path: Path) -> None:
    for _ in range(500):
        if socket_path.exists():
            return
        if service.poll() is not None:
            detail = service.stderr.read().strip() if service.stderr is not None else ""
            raise RuntimeError(
                f"checker service exited before readiness: {detail or 'no stderr'}"
            )
        await asyncio.sleep(0.02)
    raise RuntimeError("checker service socket did not become ready")


def _stop_service(service) -> None:
    if service.poll() is not None:
        return
    service.terminate()
    try:
        service.wait(timeout=5)
    except subprocess.TimeoutExpired:
        service.kill()
        service.wait(timeout=5)


def _request(fixture, task_id, assignment_id, data: bytes):
    return SubmissionBundlePreparationRequest(
        actor=ActorIdentityFacts(
            fixture.actor_context.actor_profile_id,
            fixture.actor_context.identity_link_id,
            ActorKind.HUMAN,
        ),
        request_id=new_record_id(),
        correlation_id=new_record_id(),
        task_id=task_id,
        assignment_id=assignment_id,
        predecessor_submission_id=None,
        idempotency_key=new_record_id(),
        summary=fixture.creation_request.summary,
        contributor_attestation=fixture.creation_request.contributor_attestation,
        media_type="application/zip",
        byte_source=byte_source(data),
    )


async def _verify_prepared(fixture, settings, prepared):
    """Run the independent ART verifier for one freshly uploaded preparation."""
    async with fixture.factory() as session:
        job_id = await session.scalar(
            select(ArtifactVerificationJob.id).where(
                ArtifactVerificationJob.originating_put_attempt_id
                == str(prepared.put_attempt_id)
            )
        )
        if job_id is None:
            raise RuntimeError("fresh preparation did not enqueue verification")
        await session.rollback()
        verifier = PreparedArtifactInternalAuthority(
            session,
            service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
            request_id=new_record_id(),
            correlation_id=new_record_id(),
        )
        outcome = await ArtifactStorageOrchestrator(
            session, fixture.store, fixture.namespace, settings, verifier
        ).verify_object(UUID(job_id))
        if outcome != "verified":
            raise RuntimeError("fresh preparation verification did not complete")
    async with fixture.factory() as session:
        admission = (
            await session.scalars(
                select(SubmissionBundleAdmission).where(
                    SubmissionBundleAdmission.put_attempt_id
                    == str(prepared.put_attempt_id)
                )
            )
        ).one()
        if admission.status != "ready":
            raise RuntimeError("fresh preparation admission is not ready")
        return UUID(admission.id)


async def _prove_infrastructure_recovery(
    fixture, settings, service_holder, service_binary, config_path, socket_path
):
    """Retain infrastructure failure, then require a fresh successful upload."""
    task_id, assignment_id = new_record_id(), new_record_id()
    params = {
        "task": str(task_id),
        "assignment": str(assignment_id),
        "project": str(fixture.facts.project_id),
        "actor": str(fixture.actor_context.actor_profile_id),
    }
    async with fixture.engine.begin() as connection:
        await seed_started_task_for_artifact_test(connection, params)
    _stop_service(service_holder[0])
    try:
        await _prepare(
            fixture, settings, _request(fixture, task_id, assignment_id, fixture.data)
        )
    except SubmissionBundlePreparationInfrastructureUnavailable as error:
        failure_code = str(error)
    else:
        raise RuntimeError("unavailable checker service did not fail preparation")
    async with fixture.factory() as session:
        task = await session.get(WorkstreamTask, str(task_id))
        before_submissions = await session.scalar(
            select(func.count()).select_from(Submission)
        )
        failed = (
            (
                await session.execute(
                    select(SelectedPreSubmitRun)
                    .where(SelectedPreSubmitRun.task_id == str(task_id))
                    .order_by(SelectedPreSubmitRun.queued_at)
                )
            )
            .scalars()
            .all()
        )
    if (
        task.status != "in_progress"
        or before_submissions != 1
        or len(failed) != 1
        or failed[0].status != "infrastructure_failed"
    ):
        raise RuntimeError("infrastructure failure changed TASK or was not retained")
    service = _start_service(service_binary, config_path, socket_path)
    service_holder[0] = service
    await _wait_service(service, socket_path)
    recovered = await _prepare(
        fixture,
        settings,
        _request(fixture, task_id, assignment_id, fixture.data),
    )
    if recovered.replayed:
        raise RuntimeError(
            "fresh preparation did not recover infrastructure failure: "
            f"status={recovered.submission_bundle_preparation_status}, "
            f"admission={recovered.admission_id}, replayed={recovered.replayed}"
        )
    if (
        recovered.submission_bundle_preparation_status
        == SubmissionBundlePreparationStatus.STORED_PENDING_VERIFICATION
        and recovered.admission_id is None
    ):
        admission_id = await _verify_prepared(fixture, settings, recovered)
    elif (
        recovered.submission_bundle_preparation_status
        == SubmissionBundlePreparationStatus.READY
        and recovered.admission_id is not None
    ):
        admission_id = recovered.admission_id
    else:
        raise RuntimeError(
            "fresh preparation returned an invalid durable state: "
            f"status={recovered.submission_bundle_preparation_status}, "
            f"admission={recovered.admission_id}"
        )
    async with fixture.factory() as session:
        created = await compose_hidden_submission_creation_command(
            session,
            fixture.actor_context,
            request_id=new_record_id(),
            correlation_id=new_record_id(),
        ).create(
            SubmissionCreationRequest(
                task_id=task_id,
                assignment_id=assignment_id,
                contributor_id=fixture.actor_context.actor_profile_id,
                predecessor_submission_id=None,
                admission_id=admission_id,
                summary=fixture.creation_request.summary,
                contributor_attestation=fixture.creation_request.contributor_attestation,
            )
        )
    async with fixture.factory() as session:
        task = await session.get(WorkstreamTask, str(task_id))
        submission_count = await session.scalar(
            select(func.count()).select_from(Submission)
        )
        dispatch_count = await session.scalar(
            select(func.count()).select_from(SubmissionDispatch)
        )
        runs = (
            (
                await session.execute(
                    select(SelectedPreSubmitRun.status)
                    .where(SelectedPreSubmitRun.task_id == str(task_id))
                    .order_by(SelectedPreSubmitRun.queued_at)
                )
            )
            .scalars()
            .all()
        )
    if (
        task.status != "evaluation_pending"
        or submission_count != 2
        or dispatch_count != 2
        or tuple(runs) != ("infrastructure_failed", "completed")
    ):
        raise RuntimeError("fresh recovery did not commit one atomic dispatch")
    return {
        "failure_code": failure_code,
        "retained_run_statuses": runs,
        "submission_id": str(created.submission_id),
        "evaluation_request_id": str(created.evaluation_request_id),
        "submission_count": submission_count,
        "dispatch_count": dispatch_count,
    }


async def _production_post_delivery(fixture, settings):
    """Use production handlers and a fresh worker runtime, then replay delivery."""
    # The ART arrangement is not a contributor-start authority proof. Supply
    # its exact accepted-assignment prerequisite before testing routing owners.
    async with fixture.factory() as session, session.begin():
        accepted = await session.execute(text(
            "UPDATE public.task_assignments SET accepted_at=clock_timestamp() "
            "WHERE id=:id AND accepted_at IS NULL"
        ), {"id": str(fixture.request.assignment_id)})
        if accepted.rowcount != 1:
            raise RuntimeError("fixture assignment acceptance was not established")
    await provision_router(fixture.factory)
    await delivery_fixture(fixture)
    # Supply only this isolated run's configuration. Every provider, grant,
    # authority, execution and routing operation remains the production owner.
    with patch("app.core.config.get_settings", return_value=settings), patch(
        "app.adapters.artifacts.internal_workers.get_settings", return_value=settings
    ):
        shutdown_artifact_internal_runtime()
        try:
            delivery = production_outbox_delivery(fixture.factory)
            requested = await delivery.deliver(
                fixture.created.evaluation_event_id, fixture.facts.project_id,
                "selected-production-request",
            )
            if requested is None or outcome(requested)["delivery_state"] != "acknowledged":
                raise RuntimeError("production evaluation request was not acknowledged")
            async with fixture.factory() as session:
                run = await session.get(CheckerRun, str(fixture.created.evaluation_attempt_id))
                if run.status != "completed" or run.completion_event_id is None:
                    raise RuntimeError("production selected execution did not emit completion")
                result = stored_result(run)
                completion_id = run.completion_event_id
            # Reconstruct the worker between the two durable events. No callback
            # grant, lease capability or in-memory result crosses this boundary.
            shutdown_artifact_internal_runtime()
            delivery = production_outbox_delivery(fixture.factory)
            completed = await delivery.deliver(
                completion_id, fixture.facts.project_id, "selected-production-completion",
            )
            if completed is None or outcome(completed)["delivery_state"] != "acknowledged":
                raise RuntimeError("production completion was not acknowledged")
            async with fixture.factory() as session:
                before = await outcome_snapshot(session)
            if await delivery.deliver(
                completion_id, fixture.facts.project_id, "selected-production-replay",
            ) is not None:
                raise RuntimeError("production completion was delivered twice")
            async with fixture.factory() as session:
                if await outcome_snapshot(session) != before:
                    raise RuntimeError("duplicate completion changed retained owner facts")
            return result
        finally:
            shutdown_artifact_internal_runtime()


async def run(
    *, database_url: str, image_reference: str, service_binary: Path, root: Path
) -> dict[str, object]:
    """Prove actual image execution on both sides of atomic Submission creation."""
    image = _image_identity(image_reference)
    bucket = "ws-p04-e2e-" + os.urandom(8).hex()
    socket_root, scratch = root / "service", root / "scratch"
    socket_root.mkdir(mode=0o700)
    scratch.mkdir(mode=0o700)
    socket_path = socket_root / "checker.sock"
    settings = minio_settings(
        private_prefix="selected-flow",
    ).model_copy(
        update={
            **artifact_admission_limit_settings(1024 * 1024),
            "artifact_s3_bucket": bucket,
            "artifact_scratch_root": scratch,
            "artifact_scratch_minimum_free_bytes": 0,
            "external_checker_service_socket": socket_path,
            "external_checker_material_root": scratch,
            "external_checker_service_timeout_seconds": 90.0,
        }
    )
    config = {
        "socket_path": str(socket_path),
        "material_root": str(scratch),
        "docker_binary": "/usr/bin/docker",
        "runtime": "runc",
        "isolation_mode": "docker-dev",
        "operating_system": image["operating_system"],
        "architecture": image["architecture"],
        "sandbox_uid": os.getuid(),
        "sandbox_gid": os.getgid(),
        "cache": [image],
    }
    config_path = socket_root / "service.json"
    config_path.write_text(json.dumps(config, separators=(",", ":")))
    scratch_owner = create_artifact_scratch_manager(settings)
    scratch_owner.close()
    async with await _bucket_client() as client:
        await client.create_bucket(Bucket=bucket)
    service = _start_service(service_binary, config_path, socket_path)
    service_holder = [service]
    try:
        await _wait_service(service, socket_path)
        adapter = external_checker_execution_factory(
            socket_path=socket_path, timeout_seconds=90.0
        ).create("unix_socket")
        health = await adapter.health()
        async with material_fixture(
            root,
            database_url,
            storage_settings=settings,
            pre_submit_registry_spec=_locked_spec("pre_submit", image),
            post_submit_registry_spec=_locked_spec("post_submit", image),
            post_scratch_root=scratch,
            scratch_limits=artifact_preparation_limits(settings),
        ) as fixture:
            result = await _production_post_delivery(fixture, settings)
            async with fixture.factory() as session:
                task = await session.get(WorkstreamTask, str(fixture.facts.task_id))
                submission_count = await session.scalar(
                    select(func.count()).select_from(Submission)
                )
                run_row = await session.get(CheckerRun, str(result.attempt_id))
            if (
                submission_count != 1
                or task.status != "review_pending"
                or result.outcome != "completed"
                or result.execution is None
                or len(result.execution.external_members) != 1
                or run_row.status != "completed"
            ):
                raise RuntimeError("selected flow did not retain its atomic boundaries")
            member = result.execution.external_members[0]
            if (
                member.result.verdict != "passed"
                or member.isolation.platform_manifest_digest
                != image["platform_manifest_digest"]
            ):
                raise RuntimeError("selected POST result or isolation differs")
            workspaces = scratch / "workspaces"
            workspace_cleanup = not workspaces.exists() or not any(workspaces.iterdir())
            if not workspace_cleanup:
                raise RuntimeError("selected checker workspace cleanup is incomplete")
            work_failure = await _prove_work_failure(fixture, settings)
            infrastructure_recovery = await _prove_infrastructure_recovery(
                fixture,
                settings,
                service_holder,
                service_binary,
                config_path,
                socket_path,
            )
            return {
                "image": image,
                "health": {
                    "runtime": health.runtime,
                    "isolation_mode": health.isolation_mode,
                },
                "submission_id": str(fixture.created.submission_id),
                "evaluation_request_id": str(fixture.created.evaluation_request_id),
                "attempt_id": str(result.attempt_id),
                "post_result_digest": result.result_digest,
                "post_member_result_digest": member.result.result_digest,
                "task_status": task.status,
                "submission_count": submission_count,
                "workspace_cleanup": workspace_cleanup,
                "work_failure": work_failure,
                "infrastructure_recovery": infrastructure_recovery,
                "minio_bucket": bucket,
            }
    finally:
        _stop_service(service_holder[0])
        await _delete_bucket(bucket)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database-url", default=os.environ.get("WORKSTREAM_TEST_DATABASE_URL")
    )
    parser.add_argument("--image-reference", required=True)
    parser.add_argument("--service-binary", required=True, type=Path)
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or WORKSTREAM_TEST_DATABASE_URL is required")
    with tempfile.TemporaryDirectory(prefix="ws-pilot04-selected-e2e-") as directory:
        value = asyncio.run(
            run(
                database_url=args.database_url,
                image_reference=args.image_reference,
                service_binary=args.service_binary,
                root=Path(directory),
            )
        )
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
