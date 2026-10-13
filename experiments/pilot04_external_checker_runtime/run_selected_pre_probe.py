"""Run selected PRE over genuine prepared ART bytes and the Rust service."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

from app.adapters.checkers import (
    SelectedPreSubmitCheckerExecutionAdapter,
    external_checker_execution_factory,
)
from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.artifacts.submission_materialization import (
    PreparedBundleMaterializationService,
)
from app.modules.checkers.api.default_checker import (
    WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
    WorkstreamDefaultCheckerInput,
    workstream_default_input_sha256,
)
from app.modules.checkers.api.external import (
    ExternalCheckerRegistryEntry,
    ExternalCheckerRegistrySpec,
)
from app.modules.checkers.api.external_policy import (
    LockedExternalCheckerBinding,
    LockedExternalPreSubmitPolicy,
)
from app.modules.checkers.api.materialization import SubmissionMaterialEntry
from app.modules.checkers.api.pre_submit import SubmissionPacketView
from app.modules.checkers.api.selected_pre_submit import (
    SelectedPreSubmitLeaseFacts,
    SelectedPreSubmitReservationFacts,
)
from experiments.pilot04_external_checker_runtime.run_probe import (
    _image_identity,
)
from tests.checkers.external.test_selected_pre_submit import _policy, _request


def _locked_policy(image: dict[str, str]) -> LockedExternalPreSubmitPolicy:
    """Replace only the fixture image and resource limits, then rebind hashes."""
    fixture = _policy()
    source = fixture.entries[0]
    body = source.registry.model_dump(
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
    body["image_digest"] = image["platform_manifest_digest"]
    body["resources"] |= {"deadline_ms": 8_000, "maximum_output_bytes": 8_192}
    spec = ExternalCheckerRegistrySpec.model_validate(body)
    registry = ExternalCheckerRegistryEntry(
        **spec.model_dump(),
        registry_entry_id=source.registry.registry_entry_id,
        entry_digest=spec.spec_digest,
        registration_operation_id=source.registry.registration_operation_id,
        registered_by_actor_profile_id=source.registry.registered_by_actor_profile_id,
        authorization_decision_event_id=(
            source.registry.authorization_decision_event_id
        ),
        created_at=source.registry.created_at,
    )
    binding = LockedExternalCheckerBinding(
        requirement_id=source.requirement_id,
        stage="pre_submit",
        registry=registry,
        configuration=source.configuration,
        configuration_sha256=source.configuration_sha256,
    )
    policy_body = {
        "schema_version": "external_pre_submit_policy.v1",
        "workstream_default": fixture.workstream_default.model_dump(mode="json"),
        "entries": [binding.model_dump(mode="json")],
    }
    return LockedExternalPreSubmitPolicy(
        workstream_default=fixture.workstream_default,
        entries=(binding,),
        policy_sha256=canonical_json_hash(policy_body),
    )


async def run(
    *, image_reference: str, service_binary: Path, root: Path
) -> dict[str, object]:
    """Execute one selected PRE image with no Submission or durable ART binding."""
    image = _image_identity(image_reference)
    request, inspector, manager, preparation, _ = await _request(root)
    socket_root = root / "service"
    socket_root.mkdir(mode=0o700)
    socket_path = socket_root / "checker.sock"
    config = {
        "socket_path": str(socket_path),
        "material_root": str(root / "scratch"),
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
    service = subprocess.Popen(
        [str(service_binary), str(config_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        for _ in range(500):
            if socket_path.exists():
                break
            if service.poll() is not None:
                raise RuntimeError("checker service exited before readiness")
            await asyncio.sleep(0.02)
        else:
            raise RuntimeError("checker service socket did not become ready")
        policy = _locked_policy(image)
        entries = tuple(
            SubmissionMaterialEntry(
                item.normalized_path,
                item.entry_type.value,
                item.byte_count,
                item.sha256,
                item.executable,
            )
            for item in request.manifest.entries
        )
        default_input = WorkstreamDefaultCheckerInput(
            archive_sha256=request.prepared_artifact.commitment.sha256,
            archive_byte_count=request.prepared_artifact.commitment.byte_count,
            archive_media_type="application/zip",
            semantic_manifest_sha256=request.manifest.sha256,
            entries=entries,
            predecessor=None,
            predecessor_exists=False,
            current_predecessor=None,
            current_rules_sha256=policy.policy_sha256,
            predecessor_rules_sha256=None,
            packet=SubmissionPacketView("", ""),
        )
        attempt_id = new_record_id()
        reservation = SelectedPreSubmitReservationFacts(
            actor_profile_id=new_record_id(),
            identity_link_id=new_record_id(),
            project_id=request.effective_plan.lineage.project_id,
            task_id=request.task_id,
            assignment_id=request.assignment_id,
            attempt_id=attempt_id,
            idempotency_key=new_record_id(),
            attempt_request_digest="sha256:" + "2" * 64,
            prepared_generation_id=request.prepared_artifact.generation_id,
            policy_sha256=policy.policy_sha256,
            default_behavior_sha256=WORKSTREAM_DEFAULT_BEHAVIOR_SHA256,
            default_input_sha256=workstream_default_input_sha256(default_input),
            archive_sha256=request.prepared_artifact.commitment.sha256,
            archive_byte_count=request.prepared_artifact.commitment.byte_count,
            semantic_manifest_sha256=request.manifest.sha256,
            execution_budget_ms=120_000,
        )
        request = replace(
            request,
            external_policy=policy,
            default_checker_input=default_input,
            selected_reservation=reservation,
        )
        lease = SelectedPreSubmitLeaseFacts(
            reservation=reservation,
            lease_id=new_record_id(),
            lease_generation=1,
            lease_expires_at=datetime.now(UTC) + timedelta(minutes=2),
        )
        adapter = external_checker_execution_factory(
            socket_path=socket_path, timeout_seconds=90.0
        ).create("unix_socket")
        health = await adapter.health()
        materialization = PreparedBundleMaterializationService(
            session=SimpleNamespace(in_transaction=lambda: False),
            authorization=object(),
            preparation=preparation,
            checker_execution=SelectedPreSubmitCheckerExecutionAdapter(
                archive_inspector=inspector,
                external_execution=adapter,
            ),
            storage_scheme="s3",
        )
        result = await materialization.materialize_selected_pre_submit(
            request,
            run_id=attempt_id,
            lease=lease,
            execution_authority=SimpleNamespace(
                consume=lambda *, run_id, lease: lease
            ),
        )
        member = result.external_members[0]
        workspaces = root / "scratch" / "workspaces"
        workspace_cleanup = not workspaces.exists() or list(workspaces.iterdir()) == []
        if (
            not result.eligible
            or len(result.external_members) != 1
            or member.result.verdict != "passed"
            or member.isolation.platform_manifest_digest
            != image["platform_manifest_digest"]
            or not workspace_cleanup
        ):
            raise RuntimeError("selected PRE result or cleanup differs")
        return {
            "health": {
                "runtime": health.runtime,
                "isolation_mode": health.isolation_mode,
            },
            "image": image,
            "attempt_id": str(attempt_id),
            "request_digest": reservation.request_digest,
            "result_digest": result.result_digest,
            "member_result_digest": member.result.result_digest,
            "workspace_cleanup": workspace_cleanup,
            "submission_created": False,
        }
    finally:
        await request.prepared_artifact.close()
        manager.close()
        service.terminate()
        try:
            service.wait(timeout=5)
        except subprocess.TimeoutExpired:
            service.kill()
            service.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-reference", required=True)
    parser.add_argument("--service-binary", required=True, type=Path)
    args = parser.parse_args()
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ws-pilot04-selected-pre-") as directory:
        result = asyncio.run(
            run(
                image_reference=args.image_reference,
                service_binary=args.service_binary,
                root=Path(directory),
            )
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
