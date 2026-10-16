"""Prepare and consume complete revision contexts inside the existing TASK root."""

import json
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select, text, tuple_

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.projects.api.locked_policy import ProjectLockedPolicyContextUnavailable
from app.modules.projects.api.policy_lineage import RevisionPolicySemantics
from app.modules.tasks.submission_attempts import COVERAGE_RETURN_REASON
from app.modules.tasks.api.revision import (
    ContributorRevisionContext, RevisionCandidate, RevisionContextChange, RevisionContextSnapshot,
)
from app.modules.tasks.api.authorization import TaskAuthorityDecision
from app.modules.tasks.api.submission_context import TaskSubmissionContextUnavailable
from app.modules.tasks.api.transition_audit import TaskPolicyLineage
from app.modules.tasks.models import Submission, TaskAssignment, WorkstreamTask
from app.modules.tasks.post_submit_routing.models import TaskPostSubmitRoutingManifest
from app.modules.tasks.revision.models import TaskRevisionPreparation
from app.modules.tasks.service import TaskService


_COMPONENTS = {
    "source": ("locked_guide_source_snapshot_id", "locked_guide_source_snapshot_hash"),
    "artifact": ("locked_effective_project_submission_artifact_policy_id", "locked_effective_project_submission_artifact_policy_hash"),
    "pre_submit": ("locked_pre_submit_checker_policy_id", "locked_pre_submit_checker_bundle_hash"),
    "post_submit": ("locked_post_submit_checker_policy_id", "locked_post_submit_checker_policy_hash"),
    "review": ("locked_review_policy_id", "locked_review_policy_hash"),
    "revision": ("locked_revision_policy_id", "locked_revision_policy_hash"),
    "contribution": ("locked_contribution_policy_version_id",),
}


@dataclass(frozen=True, slots=True)
class RevisionRepairReceipt:
    """One PM request and exact consumed AUTH evidence for a child preparation."""

    actor_id: UUID
    idempotency_key: UUID
    request_digest: str
    reason: str
    authority: TaskAuthorityDecision


def snapshot(facts) -> RevisionContextSnapshot:
    """Project already-verified PROJECTS facts to the TASK-owned frozen contract."""
    stamps = TaskService._policy_stamps(facts)
    lineage = TaskPolicyLineage.model_validate_json(json.dumps({
        key: str(stamps[key]) if key.endswith("_id") else stamps[key]
        for key in TaskPolicyLineage.model_fields
    }))
    receipt = facts.activation_receipt
    return RevisionContextSnapshot(
        guide_id=facts.guide_id, activation_operation_id=receipt.operation_id,
        activation_generation=receipt.activation_generation, activated_at=receipt.effective_at,
        lineage=lineage,
    )


def candidate_from_packet(packet: dict) -> RevisionCandidate:
    """Decode stored JSON through JSON mode for strict nested UUID lineage."""
    return RevisionCandidate.model_validate_json(json.dumps(packet["candidate"]))


async def select_candidate(projects, prior) -> RevisionCandidate:
    """Lock PROJECT before CHECKERS; missing current context is an explicit block."""
    policy = RevisionPolicySemantics.model_validate_json(prior.revision_policy.value)
    try:
        target = await projects.lock_active_policy_context(prior.project_id)
    except ProjectLockedPolicyContextUnavailable:
        target = None
    return RevisionCandidate(
        prior=snapshot(prior), target=snapshot(target) if target else None,
        target_post_policy_json=target.compiled_post_submit_policy.value if target else None,
        max_revision_rounds=policy.max_revision_rounds,
        revision_deadline_hours=policy.revision_deadline_hours,
        target_max_revision_rounds=(
            RevisionPolicySemantics.model_validate_json(target.revision_policy.value).max_revision_rounds
            if target else None
        ),
    )


async def head_for_source(session, routing_manifest_id):
    """Select the unique chain head without falling back to an earlier preparation."""
    child = TaskRevisionPreparation.__table__.alias("child")
    return await session.scalar(select(TaskRevisionPreparation).where(
        TaskRevisionPreparation.routing_manifest_id == routing_manifest_id,
        ~select(child.c.id).where(child.c.predecessor_id == TaskRevisionPreparation.id).exists(),
    ))


async def _inherited_coverage_window(session, manifest):
    """Consecutive coverage returns keep the first return's revision window.

    A coverage return spends no revision round, so without this a checker that
    keeps reporting the same gap could return the work forever. PostgreSQL
    applies the same rule when it validates the preparation.
    """
    # Read columns, not ORM objects: the outcome reason was just written in SQL.
    source = (await session.execute(select(
        Submission.status_reason, Submission.supersedes_submission_id,
    ).where(Submission.id == str(manifest.submission_id)))).one_or_none()
    if source is None or source.status_reason != COVERAGE_RETURN_REASON:
        return None
    if source.supersedes_submission_id is None or await session.scalar(select(
        Submission.status_reason,
    ).where(Submission.id == source.supersedes_submission_id)) != COVERAGE_RETURN_REASON:
        return None
    return (await session.execute(select(
        TaskRevisionPreparation.requested_at, TaskRevisionPreparation.deadline_at,
    ).where(
        TaskRevisionPreparation.submission_id == source.supersedes_submission_id,
    ).order_by(TaskRevisionPreparation.sequence).limit(1))).one_or_none()


async def prepare_revision(session, *, manifest, candidate, audit_event_id, predecessor=None,
                           authorization_decision_id=None, repair_receipt: RevisionRepairReceipt | None = None):
    """Freeze an authorized source once; caller retains all locks and owns commit."""
    if not session.in_transaction() or session.in_nested_transaction():
        raise TaskSubmissionContextUnavailable("task_submission_context_invalid")
    existing = await head_for_source(session, manifest.id)
    if predecessor is None and existing is not None:
        return existing
    if predecessor is not None and (existing is None or existing.id != predecessor.id):
        raise TaskSubmissionContextUnavailable("revision_context_changed")
    if predecessor is not None and repair_receipt is None:
        raise TaskSubmissionContextUnavailable("task_submission_context_invalid")
    now = await session.scalar(select(func.clock_timestamp()))
    window = predecessor or await _inherited_coverage_window(session, manifest)
    requested_at = window.requested_at if window else manifest.created_at
    deadline_at = (window.deadline_at if window else
                   requested_at + timedelta(hours=candidate.revision_deadline_hours))
    limit = predecessor.max_revision_rounds if predecessor else candidate.max_revision_rounds
    # A checker coverage return is not a revision round (PostgreSQL counts alike).
    source_round = await session.scalar(select(func.count(Submission.id)).where(
        Submission.task_assignment_id == manifest.assignment_id,
        Submission.version <= manifest.submission_version,
        Submission.status_reason.is_distinct_from(COVERAGE_RETURN_REASON),
    ))
    if source_round is None or source_round < 0 or (
        predecessor is not None and source_round != predecessor.next_revision_round
    ):
        raise TaskSubmissionContextUnavailable("revision_context_changed")
    reason = None
    if source_round > limit or (
        candidate.target_max_revision_rounds is not None
        and source_round > candidate.target_max_revision_rounds
    ):
        reason = "revision_limit_reached"
    elif now >= deadline_at:
        reason = "revision_deadline_expired"
    elif candidate.target is None:
        reason = "context_blocked"
    outcome = "blocked" if reason else (
        "kept" if candidate.prior == candidate.target else "rebased"
    )
    task = await session.get(WorkstreamTask, manifest.task_id)
    preparation_id = new_record_id()
    packet = {
        "domain": "workstream.task_revision_preparation.v1",
        "id": str(preparation_id), "routing_manifest_id": str(manifest.id),
        "predecessor_id": str(predecessor.id) if predecessor else None,
        "sequence": predecessor.sequence + 1 if predecessor else 1,
        "requested_at": requested_at.isoformat(), "deadline_at": deadline_at.isoformat(),
        "source_submission_version": manifest.submission_version,
        "next_revision_round": source_round, "max_revision_rounds": limit,
        "outcome": outcome, "blocked_reason": reason,
        "candidate": candidate.model_dump(mode="json"),
        "previous_task_lineage": {
            name: str(getattr(task, name)) if name.endswith("_id") else getattr(task, name)
            for name in TaskPolicyLineage.model_fields
        },
    }
    row = TaskRevisionPreparation(
        id=preparation_id, project_id=manifest.project_id, task_id=manifest.task_id,
        assignment_id=manifest.assignment_id, contributor_id=manifest.contributor_id,
        submission_id=manifest.submission_id, routing_manifest_id=manifest.id,
        predecessor_id=predecessor.id if predecessor else None,
        sequence=packet["sequence"], source_submission_version=manifest.submission_version,
        next_revision_round=source_round,
        max_revision_rounds=limit, requested_at=requested_at, deadline_at=deadline_at,
        outcome=outcome, blocked_reason=reason, packet=packet,
        preparation_sha256=canonical_json_hash(packet),
        authorization_decision_id=str(authorization_decision_id or manifest.authorization_decision_id),
        audit_event_id=str(audit_event_id),
        repair_actor_id=repair_receipt.actor_id if repair_receipt else None,
        repair_idempotency_key=repair_receipt.idempotency_key if repair_receipt else None,
        repair_request_digest=repair_receipt.request_digest if repair_receipt else None,
        repair_reason=repair_receipt.reason if repair_receipt else None,
        repair_authority_context=json.loads(repair_receipt.authority.resource_context_json)
        if repair_receipt else None,
    )
    session.add(row)
    # The immutable receipt precedes its guarded Task/Assignment changes.
    await session.flush()
    if outcome != "blocked":
        task = await session.get(WorkstreamTask, manifest.task_id)
        assignment = await session.get(TaskAssignment, manifest.assignment_id)
        for name, value in candidate.target.lineage.model_dump(mode="json").items():
            setattr(task, name, UUID(value) if name == "locked_contribution_policy_version_id" else value)
        task.locked_post_submit_checker_policy_body = json.loads(candidate.target_post_policy_json)
        assignment.submitter_contribution_policy_version_id = candidate.target.lineage.locked_contribution_policy_version_id
        await session.flush()
    return row


def project_revision(row, now) -> ContributorRevisionContext:
    """Expose identities and bounded differences, never checker bodies or authority."""
    candidate = RevisionCandidate.model_validate_json(json.dumps(row.packet["candidate"]))
    target, prior = candidate.target, candidate.prior
    changes = []
    if target is not None:
        before = f"{prior.guide_id}@{prior.activation_generation}:{prior.lineage.locked_guide_version}"
        after = f"{target.guide_id}@{target.activation_generation}:{target.lineage.locked_guide_version}"
        if before != after:
            changes.append(RevisionContextChange(component="guide", before=before, after=after))
        for component, fields in _COMPONENTS.items():
            before = ":".join(str(getattr(prior.lineage, name)) for name in fields)
            after = ":".join(str(getattr(target.lineage, name)) for name in fields)
            if before != after:
                changes.append(RevisionContextChange(component=component, before=before, after=after))
    disposition = row.blocked_reason or "ready"
    if disposition != "revision_limit_reached" and now >= row.deadline_at:
        disposition = "revision_deadline_expired"
    direction = None if target is None else (
        "kept" if prior == target else
        "forward" if target.activated_at >= prior.activated_at else "backward"
    )
    return ContributorRevisionContext(
        preparation_id=UUID(str(row.id)), preparation_sha256=row.preparation_sha256,
        predecessor_preparation_id=(UUID(str(row.predecessor_id)) if row.predecessor_id is not None else None),
        source_submission_id=UUID(str(row.submission_id)),
        source_routing_manifest_id=UUID(str(row.routing_manifest_id)), sequence=row.sequence,
        next_revision_round=row.next_revision_round, max_revision_rounds=row.max_revision_rounds,
        requested_at=row.requested_at, deadline_at=row.deadline_at, outcome=row.outcome,
        disposition=disposition, direction=direction, prior=prior, target=target, changes=tuple(changes),
    )


async def project_current_revisions(session, rows) -> dict[UUID, ContributorRevisionContext]:
    """Keep frozen receipt facts while projecting current source and window eligibility.

    One statement checks every source and one database clock reading serves the batch.
    """
    if not rows:
        return {}
    current = {UUID(str(key)): value for key, value in (await session.execute(text(
        "SELECT p.id, public.revision_preparation_source_current(p) "
        "FROM public.task_revision_preparations p WHERE p.id = ANY(CAST(:ids AS uuid[]))"
    ), {"ids": [str(row.id) for row in rows]})).all()}
    now = await session.scalar(select(func.clock_timestamp()))
    views = {}
    for row in rows:
        view = project_revision(row, now)
        if current.get(UUID(str(row.id))) is not True and view.disposition not in {
            "revision_limit_reached", "revision_deadline_expired",
        }:
            view = view.model_copy(update={"disposition": "context_blocked"})
        views[UUID(str(row.id))] = view
    return views


async def project_current_revision(session, row) -> ContributorRevisionContext:
    """Project one preparation through the shared batch rule."""
    return (await project_current_revisions(session, (row,)))[UUID(str(row.id))]


@dataclass(frozen=True, slots=True)
class ContributorRevisionSource:
    """One continuing contributor's active assignment on a task awaiting revision."""

    project_id: str
    task_id: str
    assignment_id: str
    contributor_id: str


async def read_contributor_revisions(
    session, sources: tuple[ContributorRevisionSource, ...],
) -> dict[str, ContributorRevisionContext]:
    """Read each source's latest revision head, keyed by assignment, in bounded queries."""
    if not sources:
        return {}
    latest = select(
        Submission.task_id, func.max(Submission.version).label("version"),
    ).where(Submission.task_id.in_([source.task_id for source in sources])).group_by(Submission.task_id).subquery()
    manifest = TaskPostSubmitRoutingManifest
    manifest_ids = (await session.scalars(select(manifest.id).distinct(manifest.task_id).join(
        latest, (latest.c.task_id == manifest.task_id),
    ).join(
        Submission, (Submission.id == manifest.submission_id) & (Submission.version == latest.c.version),
    ).where(
        tuple_(manifest.project_id, manifest.task_id, manifest.assignment_id, manifest.contributor_id).in_([
            (source.project_id, source.task_id, source.assignment_id, source.contributor_id)
            for source in sources
        ]),
        manifest.routing_recommendation == "needs_revision",
    ).order_by(manifest.task_id, manifest.evaluation_generation.desc()))).all()
    if not manifest_ids:
        return {}
    child = TaskRevisionPreparation.__table__.alias("child")
    heads = (await session.scalars(select(TaskRevisionPreparation).where(
        TaskRevisionPreparation.routing_manifest_id.in_(list(manifest_ids)),
        ~select(child.c.id).where(child.c.predecessor_id == TaskRevisionPreparation.id).exists(),
    ))).all()
    views = await project_current_revisions(session, tuple(heads))
    return {str(head.assignment_id): views[UUID(str(head.id))] for head in heads}


async def read_contributor_revision(session, task, assignment):
    """Read only the authorized continuing contributor's latest revision source."""
    if task.status != "needs_revision" or assignment is None:
        return None
    source = ContributorRevisionSource(
        str(task.project_id), str(task.id), str(assignment.id), str(assignment.contributor_id),
    )
    return (await read_contributor_revisions(session, (source,))).get(source.assignment_id)
