"""Real inspected ZIP capacity and exact locked input projection before durable admission."""

from dataclasses import replace
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

import json
import pytest
from sqlalchemy import func, select

from app.adapters.artifacts.local import LocalStorageAdapter
from app.adapters.checkers import submission_evaluation_content
from app.core.identifiers import new_record_id
from app.modules.artifacts.api import SubmissionBundleFile, SubmissionBundlePreparationRejected
from app.modules.artifacts.models import (
    ArtifactPutAttempt, PreSubmitEvidenceSet, PreSubmitExecutionAttempt,
    SubmissionBundleAdmission, SubmissionBundleDurableIntent,
)
from app.modules.artifacts.submission_materialization import PreparedBundlePreSubmitEvidenceService
from app.modules.checkers.api import SubmissionPacketView
from app.modules.checkers.api.post_submit import make_post_submit_request
from app.modules.checkers.runner import check_acceptance_criteria_present, check_evidence_present
from app.modules.checkers.post_submit_implementations import detached_checker_context
from app.modules.projects.api import ProjectLockedPolicyContextRequest
from app.modules.projects.api.locked_policy import CanonicalJsonObject
from app.modules.projects.api.policy_lineage import ReviewPolicySemantics, policy_digest
from app.modules.projects.locked_policy_repository import ProjectLockedPolicyRepository
from app.modules.tasks.api import TaskSubmissionContextRequest
from app.modules.tasks.repository import TaskRepository
from tests.submission_capacity_fixtures import capacity_fixture
from tests.pre_submit_test_helpers import approved_pre_submit_fixture
from tests.tasks.submission_lineage_support import _verified_admission
from tests.test_default_pre_submit_execution import _archive, _bytes
from tests.checkers.post_submit.support import request as evaluation_request


async def test_real_zip_capacity_rejects_before_effects_and_valid_control_passes(
    isolated_database_env, tmp_path,
):
    async with capacity_fixture(isolated_database_env, tmp_path) as h:
        base = _archive(evidence_path=h.policy["evidence_path"])
        many = BytesIO(base)
        with ZipFile(many, "a") as archive:
            for index in range(1023):
                archive.writestr(f"f{index:04d}", b"x")
        # Exactly 1001 characters, each component portable and within ART limits.
        path = "/".join(["a" * 200] * 4 + ["b" * 197])
        assert len(path) == 1001
        long_path = _archive(evidence_path=h.policy["evidence_path"], extra_path=path)
        models = (ArtifactPutAttempt, PreSubmitExecutionAttempt, PreSubmitEvidenceSet,
                  SubmissionBundleDurableIntent, SubmissionBundleAdmission)
        async with h.factory() as session:
            # Guide setup already uploaded its own documents; retain that custody.
            before = {model: await session.scalar(select(func.count()).select_from(model)) for model in models}
            assert await session.scalar(select(func.count()).select_from(ArtifactPutAttempt).where(
                ArtifactPutAttempt.task_id == str(h.request.task_id))) == 0
        for payload in (many.getvalue(), long_path):
            key = new_record_id()
            for _ in range(2):
                with patch.object(PreparedBundlePreSubmitEvidenceService, "reserve", autospec=True,
                                  side_effect=PreparedBundlePreSubmitEvidenceService.reserve) as reserve, \
                     patch.object(LocalStorageAdapter, "put", autospec=True, side_effect=LocalStorageAdapter.put) as put:
                    with pytest.raises(SubmissionBundlePreparationRejected, match="^submission_evaluation_content_invalid$"):
                        await _verified_admission(h.factory, h.store, h.namespace, h.settings, h.context,
                                                  replace(h.request, idempotency_key=key, byte_source=_bytes(payload)))
                    reserve.assert_not_called()
                    put.assert_not_called()
                async with h.factory() as session:
                    for model in models:
                        assert await session.scalar(select(func.count()).select_from(model)) == before[model], model.__tablename__
                for folder in ("files", "workspaces"):
                    assert list((h.settings.artifact_scratch_root / folder).iterdir()) == []
        admission = await _verified_admission(h.factory, h.store, h.namespace, h.settings, h.context,
                                             replace(h.request, byte_source=_bytes(base)))
        async with h.factory() as session:
            row = await session.get(SubmissionBundleAdmission, str(admission))
            assert row.status == "ready"


async def _locked_facts(h):
    async with h.factory.begin() as session:
        task = await TaskRepository(session).lock_submission_context(TaskSubmissionContextRequest(
            task_id=h.request.task_id, assignment_id=h.request.assignment_id,
            contributor_id=h.context.actor_profile_id, predecessor_submission_id=None,
        ))
        refs = task.locked_project_context
        project = await ProjectLockedPolicyRepository(session).lock_locked_policy_context(ProjectLockedPolicyContextRequest(
            project_id=refs.project_id, guide_version=refs.guide_version,
            source_snapshot_id=refs.source_snapshot_id, source_snapshot_hash=refs.source_snapshot_hash,
            effective_policy_id=refs.effective_policy_id, effective_policy_hash=refs.effective_policy_hash,
            pre_submit_policy_id=refs.pre_submit_policy_id, pre_submit_policy_bundle_hash=refs.pre_submit_policy_bundle_hash,
        ))
        return task, project


async def test_projection_exact_files_criteria_and_all_locked_stamps(isolated_database_env, tmp_path):
    async with capacity_fixture(isolated_database_env, tmp_path) as h:
        task, project = await _locked_facts(h)
        packet = SubmissionPacketView(summary=h.request.summary, contributor_attestation=h.request.contributor_attestation)
        evidence_file = SubmissionBundleFile(normalized_path=h.policy["evidence_path"], sha256="sha256:" + "1" * 64, byte_count=19)
        other_file = SubmissionBundleFile(normalized_path="evidence/other", sha256="sha256:" + "2" * 64, byte_count=23)
        project_hash = "sha256:" + "3" * 64
        def project_content(task_facts=task, files=(evidence_file, other_file)):
            return submission_evaluation_content(task_facts, project, packet, files, project_hash)
        content = project_content()
        assert content.structural_input.criteria == task.acceptance_criteria
        assert content.structural_input.package_hash == project_hash
        assert [(m.artifact, m.hash, m.size_bytes) for m in content.structural_input.manifest] == [
            (f.normalized_path, f.sha256, f.byte_count) for f in (evidence_file, other_file)]
        assert [(e.key, e.uri, e.hash) for e in content.structural_input.evidence] == [
            (json.loads(project.effective_policy.value)["required_evidence"][0]["key"],
             evidence_file.normalized_path, evidence_file.sha256)]
        # Detached false-policy facts prove the same capacity rules, not live activation.
        for required in (True, False):
            semantics = ReviewPolicySemantics(**{**json.loads(project.review_policy.value), "human_review_required": required})
            digest = policy_digest("review", semantics)
            receipt = project.activation_receipt
            selection = type(receipt.command.review)(**{**receipt.command.review.model_dump(), "policy_hash": digest})
            command = type(receipt.command)(**{**receipt.command.model_dump(), "review": selection})
            updated_receipt = type(receipt)(**{**receipt.model_dump(), "command": command})
            updated_project = replace(project, activation_receipt=updated_receipt, review_semantics_format="v2",
                                      review_policy=CanonicalJsonObject.from_mapping(semantics.model_dump(mode="json")))
            updated_policy = type(task.locked_policy)(**{**task.locked_policy.model_dump(), "locked_review_policy_hash": digest})
            updated_task = replace(task, locked_policy=updated_policy)
            projected = submission_evaluation_content(updated_task, updated_project, packet, (evidence_file,), project_hash)
            assert projected.expected_context.review_hash == digest
            with pytest.raises(ValueError, match="1024"):
                submission_evaluation_content(updated_task, updated_project, packet, (evidence_file,) * 1025, project_hash)
        base = evaluation_request()
        envelope = base.model_dump(exclude=set(type(content).model_fields) | {"request_sha256"})
        for files in ((), (other_file,)):
            missing = project_content(files=files)
            assert missing.structural_input.evidence == ()
            outcome = await check_evidence_present(detached_checker_context(make_post_submit_request(**envelope, **missing.model_dump())))
            assert outcome.status == "failed"
        for criteria in (None, ""):
            empty = project_content(replace(task, acceptance_criteria=criteria))
            assert empty.structural_input.criteria == ""
            outcome = await check_acceptance_criteria_present(detached_checker_context(make_post_submit_request(**envelope, **empty.model_dump())))
            assert outcome.status == "failed"
        with pytest.raises(ValueError, match="65536"):
            project_content(replace(task, acceptance_criteria="x" * 65537))
        # Every selected downstream identity/generation/hash is varied independently.
        for field in type(task.locked_policy).model_fields:
            if not field.startswith(("locked_post_", "locked_review_", "locked_revision_")):
                continue
            value = getattr(task.locked_policy, field)
            changed = new_record_id() if field.endswith("_id") else value + 1 if type(value) is int else "sha256:" + "f" * 64 if field.endswith("hash") else "different"
            altered = type(task.locked_policy)(**{**task.locked_policy.model_dump(), field: changed})
            with pytest.raises(ValueError, match="task submission policy differs"):
                project_content(replace(task, locked_policy=altered))
        foreign_plan, _ = await approved_pre_submit_fixture(h.factory, h.namespace, guide_version="v1")
        async with h.factory.begin() as session:
            foreign_project = await ProjectLockedPolicyRepository(session).lock_active_policy_context(foreign_plan.lineage.project_id)
        with pytest.raises(ValueError, match="task submission project differs"):
            submission_evaluation_content(task, foreign_project, packet, (evidence_file,), project_hash)
