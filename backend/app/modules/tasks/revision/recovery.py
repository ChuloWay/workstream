"""Bounded service recovery of retained routed failures without resetting their window."""

import json
from uuid import UUID

from sqlalchemy import func, select

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.outbox.api import OutboxIdempotencyConflict
from app.modules.projects.api import ProjectLockedPolicyContextRequest, ProjectLockedPolicyContextUnavailable
from app.modules.tasks.api.transition_audit import TaskPolicyLineage
from app.modules.tasks.api.revision_recovery import RECOVERY_REASON, TaskRevisionRecoveryFacts
from app.modules.tasks.api.transition_audit import TaskRevisionRepairAuditFacts
from app.modules.tasks.post_submit_routing.models import TaskPostSubmitRoutingManifest
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.revision.expiry_event import revision_expiry_event
from app.modules.tasks.revision.models import TaskRevisionPreparation
from app.modules.tasks.revision.service import RevisionRepairReceipt, prepare_revision, select_candidate
from app.modules.tasks.service import LOCKED_CONTEXT_REQUIRED_FIELDS


class TaskRevisionRecovery:
    """Caller owns the root transaction; this operation locks TASK before dependents."""

    def __init__(self, session, *, projects, authorization, audit, outbox):
        """Share the root transaction across source recovery and all owner ports."""
        self._session = session
        self._repo = TaskRepository(session)
        self._projects, self._authorization = projects, authorization
        self._audit, self._outbox = audit, outbox

    async def _missing_root_candidate(self, manifest, latest, task):
        """Freeze only the unchanged historical target or a blocked receipt."""
        try:
            historical = await self._projects.lock_locked_policy_context(
                ProjectLockedPolicyContextRequest(
                    project_id=UUID(manifest.project_id),
                    guide_version=latest.locked_guide_version,
                    source_snapshot_id=UUID(latest.locked_guide_source_snapshot_id),
                    source_snapshot_hash=latest.locked_guide_source_snapshot_hash,
                    effective_policy_id=UUID(
                        latest.locked_effective_project_submission_artifact_policy_id),
                    effective_policy_hash=latest.locked_effective_project_submission_artifact_policy_hash,
                    pre_submit_policy_id=UUID(latest.locked_pre_submit_checker_policy_id),
                    pre_submit_policy_bundle_hash=latest.locked_pre_submit_checker_bundle_hash,
                )
            )
        except (ProjectLockedPolicyContextUnavailable, TypeError, ValueError):
            return None
        candidate = await select_candidate(self._projects, historical)
        # System discovery may freeze an unchanged active context or a
        # blocked receipt. Only a PM can authorize a changed target.
        task_lineage = TaskPolicyLineage.model_validate_json(json.dumps({
            field: str(getattr(task, field)) if isinstance(getattr(task, field), UUID)
            else getattr(task, field)
            for field in TaskPolicyLineage.model_fields
        }))
        same_post_policy = (
            candidate.target_post_policy_json is not None
            and task.locked_post_submit_checker_policy_body
            == json.loads(candidate.target_post_policy_json)
        )
        if (candidate.target != candidate.prior
                or task_lineage != candidate.prior.lineage
                or not same_post_policy):
            candidate = candidate.model_copy(update={
                "target": None, "target_post_policy_json": None,
                "target_max_revision_rounds": None,
            })
        return candidate

    async def recover(self, manifest_id: UUID) -> bool:
        """Return whether one current source gained its missing root or event."""
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise RuntimeError("revision recovery requires one root transaction")
        # The first read is only a selector. Revalidate it after TASK custody.
        manifest = await self._session.get(TaskPostSubmitRoutingManifest, manifest_id)
        if manifest is None or manifest.routing_recommendation != "needs_revision":
            return False
        task = await self._repo.lock_project_task(UUID(manifest.project_id), UUID(manifest.task_id))
        if task is None or task.status != "needs_revision":
            return False
        assignment = await self._repo.lock_accepted_assignment(
            project_id=UUID(manifest.project_id), task_id=UUID(manifest.task_id),
            assignment_id=UUID(manifest.assignment_id),
        )
        if (assignment is None or assignment.status != "active"
                or assignment.accepted_at is None or assignment.released_at is not None
                or task.assigned_to != assignment.contributor_id
                or assignment.contributor_id != manifest.contributor_id):
            return False
        latest = await self._repo.get_latest_submission_for_task(
            task.id, for_update=True, populate_existing=True,
        )
        if (latest is None or latest.id != manifest.submission_id
                or latest.task_assignment_id != assignment.id
                or latest.version != manifest.submission_version
                or not await self._session.scalar(select(
                    func.revision_routing_source_current(manifest_id)))):
            return False
        root = await self._session.scalar(select(TaskRevisionPreparation).where(
            TaskRevisionPreparation.routing_manifest_id == manifest_id,
            TaskRevisionPreparation.sequence == 1,
        ))
        expected_event = revision_expiry_event(manifest, root) if root else None
        if expected_event is not None:
            try:
                await self._outbox.require_existing(None, expected_event)
                return False
            except OutboxIdempotencyConflict:
                # Missing or conflicting logical keys are resolved by OUTBOX's
                # atomic append after fresh service authority below.
                pass
        candidate = None
        if root is None:
            candidate = await self._missing_root_candidate(manifest, latest, task)
            if candidate is None:
                return False
        context_hash = canonical_json_hash({
            field: str(getattr(task, field)) if isinstance(getattr(task, field), UUID)
            else getattr(task, field) for field in LOCKED_CONTEXT_REQUIRED_FIELDS
        })
        request_digest = canonical_json_hash({
            "routing_manifest_id": str(manifest_id),
            "preparation_id": str(root.id) if root else None,
            "preparation_sha256": root.preparation_sha256 if root else None,
            "candidate": candidate.model_dump(mode="json") if candidate else None,
        })
        actor_id, decision = await self._authorization.authorize(
            TaskRevisionRecoveryFacts(
                project_id=UUID(task.project_id), task_id=UUID(task.id),
                assignment_id=UUID(assignment.id),
                contributor_id=UUID(assignment.contributor_id),
                routing_manifest_id=manifest_id,
                locked_context_hash=context_hash, request_digest=request_digest,
                preparation_id=UUID(str(root.id)) if root else None,
                preparation_sha256=root.preparation_sha256 if root else None,
            )
        )
        audit_event_id = new_record_id()
        if root is None:
            root = await prepare_revision(
                self._session, manifest=manifest, candidate=candidate,
                audit_event_id=audit_event_id,
                authorization_decision_id=decision.decision_id,
                repair_receipt=RevisionRepairReceipt(
                    actor_id=actor_id, idempotency_key=manifest_id,
                    request_digest=request_digest, reason=RECOVERY_REASON,
                    authority=decision,
                ),
            )
            if root.outcome == "rebased":
                raise RuntimeError("service recovery cannot rebase a task")
        event = await self._outbox.append(revision_expiry_event(manifest, root))
        await self._audit.record_revision_repair(TaskRevisionRepairAuditFacts(
            event_id=audit_event_id, project_id=UUID(task.project_id), task_id=UUID(task.id),
            assignment_id=UUID(assignment.id), submission_id=UUID(latest.id),
            routing_manifest_id=manifest_id, preparation_id=UUID(str(root.id)),
            actor_profile_id=actor_id, authorization_decision_id=decision.decision_id,
            reason=RECOVERY_REASON, outbox_event_id=event.event_id,
            authorization_resource_digest=decision.resource_context_digest,
        ))
        await self._session.flush()
        return True
