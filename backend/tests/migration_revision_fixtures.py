"""Historical 0047 window inputs, inserted with its original guards enabled."""

from datetime import timedelta
import json
from types import SimpleNamespace

from sqlalchemy import func, select, text

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.tasks.api.transition_audit import TaskPolicyLineage
from app.modules.tasks.models import Submission, WorkstreamTask


async def insert_0047_preparation(session, *, manifest, candidate, audit_event_id):
    """Seed the old INSERT shape; current runtime never calls this test-only writer."""
    task = await session.get(WorkstreamTask, manifest.task_id)
    source_round = await session.scalar(select(func.count(Submission.id)).where(
        Submission.task_assignment_id == manifest.assignment_id,
        Submission.version <= manifest.submission_version,
    ))
    preparation_id = new_record_id()
    deadline = manifest.created_at + timedelta(hours=candidate.revision_deadline_hours)
    now = await session.scalar(select(func.clock_timestamp()))
    reason = (
        "revision_limit_reached" if source_round > candidate.max_revision_rounds or (
            candidate.target_max_revision_rounds is not None
            and source_round > candidate.target_max_revision_rounds
        ) else "revision_deadline_expired" if now >= deadline else
        "context_blocked" if candidate.target is None else None
    )
    outcome = "blocked" if reason else "kept"
    assert outcome == "blocked" or candidate.prior == candidate.target
    packet = {
        "domain": "workstream.task_revision_preparation.v1",
        "id": str(preparation_id), "routing_manifest_id": str(manifest.id),
        "predecessor_id": None, "sequence": 1,
        "requested_at": manifest.created_at.isoformat(), "deadline_at": deadline.isoformat(),
        "source_submission_version": manifest.submission_version,
        "next_revision_round": source_round, "max_revision_rounds": candidate.max_revision_rounds,
        "outcome": outcome, "blocked_reason": reason,
        "candidate": candidate.model_dump(mode="json"),
        "previous_task_lineage": {
            name: str(getattr(task, name)) if name.endswith("_id") else getattr(task, name)
            for name in TaskPolicyLineage.model_fields
        },
    }
    row = {
        "id": str(preparation_id), "project_id": manifest.project_id, "task_id": manifest.task_id,
        "assignment_id": manifest.assignment_id, "contributor_id": manifest.contributor_id,
        "submission_id": manifest.submission_id, "routing_manifest_id": str(manifest.id),
        "predecessor_id": None, "sequence": 1, "source_submission_version": manifest.submission_version,
        "next_revision_round": source_round, "max_revision_rounds": candidate.max_revision_rounds,
        "requested_at": manifest.created_at.isoformat(), "deadline_at": deadline.isoformat(),
        "outcome": outcome, "blocked_reason": reason, "packet": packet,
        "preparation_sha256": canonical_json_hash(packet),
        "authorization_decision_id": manifest.authorization_decision_id,
        "audit_event_id": str(audit_event_id),
    }
    columns = ",".join(row)
    result = (await session.execute(text(
        f"INSERT INTO public.task_revision_preparations ({columns}) "
        f"SELECT {columns} FROM jsonb_populate_record("
        "NULL::public.task_revision_preparations,CAST(:row AS jsonb)) RETURNING *"
    ), {"row": json.dumps(row)})).mappings().one()
    return SimpleNamespace(**result, remaining_microseconds=None, clock_observed_at=None)


async def retained_revision_rows(session, manifest_id, *, root_only=False):
    """Compare retained bytes plus table and physical row identities across ADD COLUMN."""
    selectors = {
        "revision_policies": "id=(SELECT s.locked_revision_policy_id FROM public.submissions s "
        "JOIN public.task_post_submit_routing_manifests m ON m.submission_id=s.id WHERE m.id=:id)",
        "workstream_tasks": "id=(SELECT task_id FROM public.task_post_submit_routing_manifests WHERE id=:id)",
        "task_assignments": "id=(SELECT assignment_id FROM public.task_post_submit_routing_manifests WHERE id=:id)",
        "submissions": "id=(SELECT submission_id FROM public.task_post_submit_routing_manifests WHERE id=:id)",
        "task_revision_preparations": "routing_manifest_id=:id",
        "task_post_submit_routing_manifests": "id=:id",
        "outbox_events": "idempotency_key='task.revision.expire:'||CAST(CAST(:id AS uuid) AS text)",
    }
    if root_only:
        selectors["task_revision_preparations"] += " AND predecessor_id IS NULL"
    result = {}
    for table, where in selectors.items():
        values = await session.execute(text(
            "SELECT (to_jsonb(row)-'remaining_microseconds'-'clock_observed_at')::text,"
            f"tableoid::bigint,xmin::text FROM public.{table} row WHERE {where}"
        ), {"id": manifest_id})
        result[table] = [tuple(row) for row in values]
        assert len(result[table]) == 1, table
    return result
