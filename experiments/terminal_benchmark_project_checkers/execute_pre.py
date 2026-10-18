#!/usr/bin/env python3
"""Create and verify one exact PRE request for a WS493 proof package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.artifacts.submission_manifest import SUBMISSION_MANIFEST_SCHEMA_VERSION
from app.modules.checkers.api.external import (
    ExternalCheckerExecutionRequest,
    ExternalCheckerExecutionResult,
    ExternalCheckerRegistryEntry,
    ExternalCheckerSchema,
    ExternalCheckerRegistrySpec,
    PRE_SUBMIT_INPUT_SCHEMA_ID,
    PreSubmitExternalCheckerIdentity,
    PreSubmitExternalCheckerMaterial,
    external_checker_json_hash,
    make_external_checker_execution_request,
)

from execute_post import _inventory, _registry_entry_from_json


def _write(path: Path, value: object) -> None:
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(
        path,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("PRE evidence write made no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def request(contract_path: Path, package: Path, output: Path) -> None:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    post_registry = _registry_entry_from_json(contract["registry"])
    pre_input_schema = ExternalCheckerSchema(
        schema_id=PRE_SUBMIT_INPUT_SCHEMA_ID,
        schema_version=post_registry.input_schema.schema_version,
        document=post_registry.input_schema.document,
        schema_sha256=external_checker_json_hash(post_registry.input_schema.document),
    )
    pre_spec = ExternalCheckerRegistrySpec(
        capability_id=post_registry.capability_id,
        capability_version=post_registry.capability_version,
        phase="pre_submit",
        image_digest=post_registry.image_digest,
        configuration_schema=post_registry.configuration_schema,
        input_schema=pre_input_schema,
        output_schema=post_registry.output_schema,
        resources=post_registry.resources,
    )
    registry = ExternalCheckerRegistryEntry(
        **pre_spec.model_dump(),
        registry_entry_id=new_record_id(),
        entry_digest=pre_spec.spec_digest,
        registration_operation_id=new_record_id(),
        registered_by_actor_profile_id=post_registry.registered_by_actor_profile_id,
        authorization_decision_event_id=new_record_id(),
        created_at=post_registry.created_at,
    )
    _, files, manifest_entries = _inventory(package)
    semantic_body = {
        "schema_version": SUBMISSION_MANIFEST_SCHEMA_VERSION,
        "entries": manifest_entries,
    }
    semantic_digest = canonical_json_hash(semantic_body)
    identity = PreSubmitExternalCheckerIdentity(
        project_id=new_record_id(),
        task_id=new_record_id(),
        assignment_id=new_record_id(),
        prepared_generation_id=new_record_id(),
        attempt_id=new_record_id(),
        attempt_request_digest="sha256:" + "4" * 64,
        effective_plan_sha256="sha256:" + "5" * 64,
    )
    archive_body = [
        {"path": item.normalized_path, "sha256": item.sha256} for item in files
    ]
    material = PreSubmitExternalCheckerMaterial(
        role="submission_archive",
        prepared_generation_id=identity.prepared_generation_id,
        attempt_id=identity.attempt_id,
        attempt_request_digest=identity.attempt_request_digest,
        archive_sha256=external_checker_json_hash(archive_body),
        archive_byte_count=sum(item.byte_count for item in files),
        semantic_manifest_sha256=semantic_digest,
        media_type="application/zip",
    )
    configuration = contract["configuration"]
    execution = make_external_checker_execution_request(
        registry=registry,
        identity=identity,
        configuration=configuration,
        configuration_sha256=external_checker_json_hash(configuration),
        input={"manifest": manifest_entries},
        input_sha256=external_checker_json_hash({"manifest": manifest_entries}),
        materials=(material,),
    )
    _write(output, execution.model_dump(mode="json"))


def verify(request_path: Path, result_path: Path, output: Path) -> None:
    execution = ExternalCheckerExecutionRequest.model_validate_json(
        request_path.read_text(encoding="utf-8")
    )
    result_bytes = result_path.read_bytes()
    if len(result_bytes) > 65_536:
        raise ValueError("PRE result is unbounded")
    result = ExternalCheckerExecutionResult.model_validate_json(result_bytes)
    result.validate_request(execution)
    if (
        result.outcome != "completed"
        or result.verdict != "passed"
        or result.findings
        or result.infrastructure_failure_code is not None
    ):
        raise ValueError("PRE result differs")
    _write(
        output,
        {
            "request_digest": execution.request_digest,
            "result_digest": result.result_digest,
            "result_sha256": hashlib.sha256(result_bytes).hexdigest(),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="operation", required=True)
    request_parser = subparsers.add_parser("request")
    request_parser.add_argument("--contract", type=Path, required=True)
    request_parser.add_argument("--package", type=Path, required=True)
    request_parser.add_argument("--output", type=Path, required=True)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--request", type=Path, required=True)
    verify_parser.add_argument("--result", type=Path, required=True)
    verify_parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.operation == "request":
        request(arguments.contract, arguments.package, arguments.output)
    else:
        verify(arguments.request, arguments.result, arguments.output)


if __name__ == "__main__":
    main()
