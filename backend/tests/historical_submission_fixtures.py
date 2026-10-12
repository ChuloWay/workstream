"""Explicit predecessor storage for migration proofs, never a current intake writer.

Only migration tests call this seeder. It writes the pre-0025 row shape with all
then-installed constraints enabled; it does not invent current AUTH or dispatch
receipts. Preparation and verification still use real ART owners and ZIP bytes.
"""

import json
from contextlib import AsyncExitStack, asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select, func

from app.core.identifiers import new_record_id
from app.core.hashing import canonical_json_hash
from app.modules.artifacts.api import SubmissionBundleFile
from app.modules.artifacts.models import ArtifactBinding, SubmissionBundleAdmission
from app.modules.checkers.api.artifact_paths import required_evidence_path
from app.modules.projects.api import ProjectLockedPolicyContextFacts
from app.modules.tasks.api import TaskSubmissionContextRequest
from app.modules.tasks.api import TaskSubmissionContextFacts
from app.modules.tasks.models import Submission
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.submission_composition import build_submission
from tests.migration_fixtures import current_art_attempt_seed_schema
from tests.post_submit_materialization_helpers import _archive_facts, _material_fixture


class HistoricalRawValue(SimpleNamespace):
    """Attribute access over literal predecessor JSON, never a product contract."""

    def model_dump(self, *, exclude=frozenset(), **_options):
        def dump(value):
            if isinstance(value, HistoricalRawValue):
                return {key: dump(item) for key, item in vars(value).items()}
            if isinstance(value, tuple):
                return [dump(item) for item in value]
            if isinstance(value, UUID):
                return str(value)
            return deepcopy(value)

        return {
            key: dump(value)
            for key, value in vars(self).items()
            if key not in exclude
        }

    def model_copy(self, *, update):
        values = vars(self) | update
        return HistoricalRawValue(**values)


def _raw(value):
    if isinstance(value, dict):
        return HistoricalRawValue(**{key: _raw(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_raw(item) for item in value)
    return value


_HISTORICAL_DEFINITIONS = (
    ("check_submission_packet", "packet_presence", "packet_fields_missing", "submission_structure", "failed", "high", True),
    ("check_policy_context_present", "policy_context_consistency", "policy_context_invalid", "task_configuration", "failed", "high", True),
    ("check_evidence_present", "evidence_presence", "evidence_missing", "submission_structure", "failed", "high", True),
    ("check_evidence_integrity", "evidence_structure", "evidence_structure_invalid", "submission_structure", "failed", "high", True),
    ("check_required_files", "required_path_presence", "required_files_missing", "submission_structure", "failed", "high", True),
    ("check_forbidden_files", "forbidden_path_detection", "forbidden_path_present", "submission_structure", "failed", "high", True),
    ("check_confidentiality_attestation", "attestation_presence", "attestation_missing", "submission_structure", "failed", "high", True),
    ("check_low_quality_generated_artifacts", "placeholder_signal_detection", "placeholder_signal", "submission_structure", "warning", "medium", True),
    ("check_acceptance_criteria_present", "criteria_presence", "acceptance_criteria_missing", "task_configuration", "failed", "high", False),
)


def _historical_catalogue() -> dict[str, object]:
    resources = {
        "deadline_ms": 5000,
        "maximum_evidence_items": 1024,
        "maximum_generated_output_bytes": 0,
        "maximum_input_bytes": 1_048_576,
        "maximum_manifest_items": 1024,
        "maximum_policy_items": 256,
        "maximum_result_bytes": 4096,
        "maximum_results": 1,
        "maximum_text_characters": 65_536,
        "phase_deadline_ms": 45_000,
    }
    definitions = []
    for order, values in enumerate(_HISTORICAL_DEFINITIONS, 1):
        capability, claim, code, category, status, severity, platform_default = values
        definitions.append(
            {
                "capability_id": capability,
                "capability_version": "v0.1",
                "configuration_schema": "post_submit_empty_configuration",
                "dependencies": [],
                "disabled_behavior": "unavailable",
                "execution_method": "deterministic",
                "failure_category": category,
                "failure_code": code,
                "failure_severity": severity,
                "failure_status": status,
                "implementation_version": "workstream-structural",
                "input_schema": "post_submit_structural_input",
                "order": order,
                "platform_default": platform_default,
                "provider_recovery": "none",
                "required_output_roles": [],
                "resources": resources,
                "result_schema": "post_submit_structural_result",
                "selectable": not platform_default,
                "stage": "post_submit",
                "state": "enabled",
                "supported_claim": claim,
            }
        )
    return {
        "catalogue_id": "workstream.post_submission_checkers",
        "definitions": definitions,
        "manifest_sha256": "sha256:87b454499eca2dbf10e86495e4f9b2a4440977a51d5ae5c4d3f6405672fa89a5",
        "schema_version": "post_submission_checker_capability_projection",
        "source_version": "v0.1",
    }


async def write_historical_submission(factory, context, request):
    """Seed only an actual predecessor schema; never bypass current constraints."""
    from sqlalchemy import text
    async with factory() as session, session.begin():
        revision = await session.scalar(text("SELECT version_num FROM public.alembic_version"))
        assert revision in {
            "0007_checker_output_custody", "0008_checker_execution", "0009_checker_material_lineage",
            "0010_post_submit_authority", "0011_task_routing_source", "0012_review_packet",
            "0013_review_source", "0014_final_acceptance", "0015_contribution_awards",
            "0017_acceptance_source_contracts", "0018_task_routing_request",
            "0020_review_admission_lock_order", "0021_submission_manifest",
            "0022_submission_packet_custody", "0023_remove_task_payment_policy",
            "0024_require_second_review_false",
        }, "historical seeder cannot write the current schema"
        repository = TaskRepository(session)
        facts, source = await repository.select_submission_context(TaskSubmissionContextRequest(
            request.task_id, request.assignment_id, request.contributor_id, request.predecessor_submission_id,
        ))
        assert source is None
        task = await repository.get_task(str(request.task_id))
        admission = await session.get(SubmissionBundleAdmission, str(request.admission_id))
        assert admission.status == "ready" and admission.actor_profile_id == str(context.actor_profile_id)
        version = 1 if facts.predecessor is None else facts.predecessor.version + 1
        submission_id, binding_id = new_record_id(), new_record_id()
        submission = build_submission(
            submission_id=str(submission_id), task=task, contributor_id=str(request.contributor_id),
            version=version, summary=request.summary, worker_attestation=request.contributor_attestation,
            supersedes_submission_id=str(request.predecessor_submission_id) if request.predecessor_submission_id else None,
            contribution_policy_version_id=facts.submitter_contribution_policy_version_id,
            task_assignment_id=str(request.assignment_id),
        )
        session.add(submission)
        await session.flush()
        session.add(ArtifactBinding(
            id=str(binding_id), content_id=admission.artifact_content_id, project_id=admission.project_id,
            resource_type="submission", resource_id=str(submission_id), logical_role="submission_bundle_original",
            scope_version=1, actor_id=admission.actor_profile_id, attribution_type="contributor",
        ))
        consumed_at = await session.scalar(select(func.now()))
        admission.status = "consumed"
        admission.consumed_at = consumed_at
        admission.consumed_by_submission_id = str(submission_id)
        admission.consumed_by_submission_version = version
        submission.submission_bundle_admission_id = admission.id
        submission.artifact_binding_id = str(binding_id)
        submission.artifact_content_id = admission.artifact_content_id
        task.status = "submitted"
        await session.flush()
        return SimpleNamespace(submission_id=submission_id, submission_version=version,
            admission_id=request.admission_id, artifact_binding_id=binding_id,
            artifact_content_id=UUID(admission.artifact_content_id), task_context=facts)


def submission_evaluation_content(
    task_context: TaskSubmissionContextFacts,
    project_context: ProjectLockedPolicyContextFacts,
    packet,
    files: tuple[SubmissionBundleFile, ...],
    archive_sha256: str,
) -> HistoricalRawValue:
    """Build the literal predecessor JSON retained by migration fixtures."""
    from app.adapters.tasks import validate_submission_policy_context

    validate_submission_policy_context(task_context, project_context)
    stamps = task_context.locked_policy
    expected = {
        "guide_version": stamps.locked_guide_version,
        "source_id": stamps.locked_guide_source_snapshot_id,
        "source_hash": stamps.locked_guide_source_snapshot_hash,
        "effective_policy_id": stamps.locked_effective_project_submission_artifact_policy_id,
        "effective_policy_hash": stamps.locked_effective_project_submission_artifact_policy_hash,
        "pre_policy_id": stamps.locked_pre_submit_checker_policy_id,
        "pre_policy_hash": stamps.locked_pre_submit_checker_bundle_hash,
        "post_policy_id": stamps.locked_post_submit_checker_policy_id,
        "post_policy_version": stamps.locked_post_submit_checker_policy_version,
        "post_policy_hash": stamps.locked_post_submit_checker_policy_hash,
        "review_policy_id": stamps.locked_review_policy_id,
        "review_generation": stamps.locked_review_policy_generation,
        "review_hash": stamps.locked_review_policy_hash,
        "revision_policy_id": stamps.locked_revision_policy_id,
        "revision_generation": stamps.locked_revision_policy_generation,
        "revision_hash": stamps.locked_revision_policy_hash,
    }
    effective = json.loads(project_context.effective_policy.value)
    policy_inputs = {
        "required_evidence_keys": [
            item["key"] for item in effective.get("required_evidence", [])
            if item.get("required", True)
        ],
        "required_artifact_paths": [
            item["path"] for item in effective.get("required_artifacts", [])
            if item.get("required", True)
        ],
        "forbidden_artifact_patterns": [
            item["pattern"] for item in effective.get("forbidden_artifacts", [])
            if item.get("pattern")
        ],
        "required_attestation_terms": [
            term for term in effective.get("attestation_terms", []) if term
        ],
    }
    by_path = {item.normalized_path: item for item in files}
    body = {
        "project_id": project_context.project_id,
        "expected_context": expected,
        "catalogue": _historical_catalogue(),
        "policy": json.loads(project_context.compiled_post_submit_policy.value),
        "structural_input": {
            "schema_version": "post_submit_structural_input",
            "summary": packet.summary,
            "worker_attestation": packet.contributor_attestation,
            "package_hash": archive_sha256,
            "criteria": task_context.acceptance_criteria or "",
            "manifest": [
                {
                    "artifact": item.normalized_path,
                    "hash": item.sha256,
                    "notes": None,
                    "size_bytes": item.byte_count,
                }
                for item in files
            ],
            "evidence": [
                {
                    "label": key,
                    "uri": item.normalized_path,
                    "hash": item.sha256,
                    "type": "file",
                    "key": key,
                    "policy_key": None,
                    "evidence_key": None,
                    "required_evidence_key": None,
                }
                for key in policy_inputs["required_evidence_keys"]
                for item in (by_path.get(required_evidence_path(key)),)
                if item is not None
            ],
            "policy_inputs": policy_inputs,
            "observed_context": expected,
        },
    }
    return _raw(body)


async def _historical_request(session, facts, created, data):
    """Project genuine historical inputs without creating a future reservation."""
    from app.adapters.tasks import task_service
    from app.core.config import get_settings
    from app.modules.tasks.models import WorkstreamTask

    submission = await session.get(Submission, str(created.submission_id))
    task = await session.get(WorkstreamTask, submission.task_id)
    project = await task_service(session, settings=get_settings())._load_locked_task_context(task)
    _, manifest, _, digest = _archive_facts(data)
    content = submission_evaluation_content(
        created.task_context,
        project.facts,
        SimpleNamespace(
            summary=submission.summary,
            contributor_attestation=submission.worker_attestation,
        ),
        manifest.file_facts(),
        digest,
    )
    body = content.model_dump() | {
        "schema_version": "post_submit_evaluation_request",
        "evaluation_request_id": new_record_id(),
        "evaluation_generation": 1,
        "task_id": facts.task_id,
        "assignment_id": facts.assignment_id,
        "submission_id": created.submission_id,
        "submission_version": created.submission_version,
        "content_id": created.artifact_content_id,
        "binding_id": created.artifact_binding_id,
        "content_sha256": digest,
        "byte_count": len(data),
    }
    body["request_sha256"] = canonical_json_hash(
        _raw(body).model_dump()
    )
    return _raw(body)


@asynccontextmanager
async def historical_material_fixture(tmp_path, database_url, **options):
    async with AsyncExitStack() as stack:
        async with current_art_attempt_seed_schema(database_url):
            material = await stack.enter_async_context(_material_fixture(
                tmp_path, database_url, write_submission=write_historical_submission,
                read_request=_historical_request, **options,
            ))
        yield material
