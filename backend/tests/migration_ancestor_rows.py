"""Literal Review ancestors for predecessor-storage migration proofs only.

This seeder calls no current review, routing, checker or authorization service.
Installed SQL guards validate every archived relationship and digest.
"""

from contextlib import asynccontextmanager
from datetime import timedelta
import json
from uuid import UUID

from sqlalchemy import insert, text

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.reviews.models import ReviewQueueEntry, ReviewLease
from app.modules.reviews.packet.models import ReviewPacketManifest, ReviewPacketGuideItem
from app.modules.reviews.decision.models import Review, ReviewFinding, ReviewDecisionRequest
from tests.checkers.execution.historical_execution import archived_completed_checker_source


def _uuid_json(value):
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"Non-JSON archived fact: {type(value).__name__}")


def _json(value):
    return json.loads(json.dumps(value, default=_uuid_json, allow_nan=False))


@asynccontextmanager
async def archived_packet_ancestors(tmp_path, database_url, **options):
    async with archived_completed_checker_source(tmp_path, database_url, **options) as h:
        await seed_packet_ancestors(h)
        yield h


async def seed_packet_ancestors(h):
    async with h.factory() as session, session.begin():
        revision = await session.scalar(text("SELECT version_num FROM public.alembic_version"))
        assert 11 <= int(revision[:4]) <= 28
        submission = (await session.execute(text(
            "SELECT * FROM public.submissions WHERE id=:id"
        ), {"id": UUID(h.request["submission_id"])})).mappings().one()
        guide = (await session.execute(text(
            "SELECT * FROM public.project_guides WHERE project_id=:project AND version=:version"
        ), {"project": submission["project_id"], "version": submission["locked_guide_version"]})).mappings().one()
        activation = await session.scalar(text(
            "SELECT response_json FROM public.guide_mutation_idempotency_records WHERE operation_id=:id"
        ), {"id": guide["activation_operation_id"]})
        proposal = activation["command"]["target"]["proposal"]
        documents = (await session.execute(text("""SELECT i.id AS ingest_id,
            s.id AS source_item_id, s.item_order, s.media_type
            FROM public.guide_source_snapshot_items s
            JOIN public.guide_source_artifact_ingests i ON i.source_item_id=s.id
            WHERE s.source_snapshot_id=:id ORDER BY s.item_order"""),
            {"id": submission["locked_guide_source_snapshot_id"]})).mappings().all()
        reviewer = await session.scalar(text("""SELECT id FROM public.actor_profiles
            WHERE service_identity IS NULL AND id<>:contributor AND status='active'
            ORDER BY id LIMIT 1"""), {"contributor": submission["contributor_id"]})
        assert reviewer is not None, "archived base must include a distinct human reviewer"
        now = await session.scalar(text("SELECT clock_timestamp()"))
        h.queue_id, h.lease_id = new_record_id(), new_record_id()
        await session.execute(insert(ReviewQueueEntry).values(
            id=h.queue_id, project_id=str(submission["project_id"]), task_id=str(submission["task_id"]),
            submission_id=str(submission["id"]), submission_version=submission["version"],
            admitting_checker_run_id=h.result["attempt_id"], routing_mode="open",
            routing_reason="first_submission", queue_state="pending", active_lease_id=None,
            routing_generation=1, lifecycle_generation=1, first_queued_at=now, available_since=now,
        ))
        await session.execute(insert(ReviewLease).values(
            id=h.lease_id, review_queue_entry_id=h.queue_id,
            project_id=str(submission["project_id"]), task_id=str(submission["task_id"]),
            submission_id=str(submission["id"]), submission_version=submission["version"],
            reviewer_id=str(reviewer), reviewer_contribution_policy_version_id=h.source["contribution_policy_version_id"],
            attempt_generation=1, expires_at=now+timedelta(days=1), status="active", claimed_at=now,
        ))
        await session.execute(text("""UPDATE public.review_queue_entries
            SET queue_state='leased',active_lease_id=:lease WHERE id=:id"""),
            {"id": h.queue_id, "lease": h.lease_id})
        request = {
            "project_id": str(submission["project_id"]), "task_id": str(submission["task_id"]),
            "submission_id": str(submission["id"]), "submission_version": submission["version"],
            "checker_run_id": h.result["attempt_id"], "result_id": h.result["result_id"],
            "guide_id": str(guide["id"]), "guide_version": guide["version"],
            "source_snapshot_id": str(submission["locked_guide_source_snapshot_id"]),
            "project_setup_run_id": proposal["setup_run_id"], "setup_generation": proposal["setup_generation"],
        }
        h.packet_body = {"request": request, "submission": {
            "binding_id": str(submission["artifact_binding_id"]),
            "logical_role": "submission_bundle_original", "media_type": "application/zip",
        }, "guide_documents": [{
            "ingest_id": str(d["ingest_id"]), "source_item_id": str(d["source_item_id"]),
            "item_order": d["item_order"], "logical_role": "guide_source_original", "media_type": d["media_type"],
        } for d in documents]}
        h.archived_submission = dict(submission)
        h.archived_reviewer_id = reviewer


@asynccontextmanager
async def archived_review_ancestors(tmp_path, database_url, *, decision="accept", **options):
    async with archived_packet_ancestors(tmp_path, database_url, **options) as h:
        await seed_review_ancestors(h, decision=decision)
        yield h


async def seed_review_ancestors(h, *, decision):
    async with h.factory() as session, session.begin():
        revision = await session.scalar(text("SELECT version_num FROM public.alembic_version"))
        assert 12 <= int(revision[:4]) <= 28
        h.packet_id = new_record_id()
        digest = canonical_json_hash(h.packet_body)
        request = h.packet_body["request"]
        await session.execute(insert(ReviewPacketManifest).values(
            id=h.packet_id, review_lease_id=h.lease_id, review_queue_entry_id=h.queue_id,
            packet_manifest_generation=1, packet_manifest_digest=digest,
            **request, submission_binding_id=h.packet_body["submission"]["binding_id"],
            submission_logical_role="submission_bundle_original", submission_media_type="application/zip",
        ))
        for member in h.packet_body["guide_documents"]:
            await session.execute(insert(ReviewPacketGuideItem).values(
                packet_id=h.packet_id, **member,
            ))
        s = h.archived_submission
        artifact_hash = await session.scalar(text(
            "SELECT sha256 FROM public.artifact_contents WHERE id=:id"
        ), {"id": s["artifact_content_id"]})
        h.review = {
            "id": new_record_id(), "project_id": s["project_id"], "task_id": s["task_id"],
            "task_assignment_id": s["task_assignment_id"], "submission_id": s["id"],
            "submission_version": s["version"], "review_queue_entry_id": h.queue_id,
            "review_lease_id": h.lease_id, "packet_manifest_id": h.packet_id,
            "packet_manifest_digest": digest, "artifact_hash": artifact_hash,
            "reviewer_id": h.archived_reviewer_id,
            "reviewer_contribution_policy_version_id": h.source["contribution_policy_version_id"],
            "locked_guide_version": s["locked_guide_version"],
            "locked_review_policy_id": s["locked_review_policy_id"],
            "locked_review_policy_generation": s["locked_review_policy_generation"],
            "locked_review_policy_hash": s["locked_review_policy_hash"], "predecessor_review_id": None,
            "decision": decision, "summary": "Verified the exact submitted work.",
            "findings": ([{"id": new_record_id(), "finding_kind": "blocking", "area": "Deliverable",
                          "issue": "Required result", "required_fix": "Correct the documented result."}]
                         if decision == "needs_revision" else []), "resolutions": [],
        }


async def seed_review_row(session, review):
    source = _json(review)
    findings = source["findings"]
    counts = {"finding_count": len(findings),
              "blocking_finding_count": sum(f["finding_kind"] == "blocking" for f in findings),
              "resolution_count": 0}
    digest = canonical_json_hash(source | counts | {"domain": "workstream.review_source.v0.1"})
    values = {k: v for k, v in review.items() if k not in {"findings", "resolutions"}}
    await session.execute(insert(Review).values(**values, **counts, aggregate_digest=digest))
    for order, member in enumerate(review["findings"]):
        await session.execute(insert(ReviewFinding).values(**member, review_id=review["id"], item_order=order))
    request_body = source | counts | {"action": "review.decision", "domain": "workstream.review_decision_request.v0.1"}
    request_body.pop("id")
    for member in request_body["findings"]:
        member.pop("id")
    await session.execute(insert(ReviewDecisionRequest).values(
        id=new_record_id(), operation_id=new_record_id(), project_id=review["project_id"],
        reviewer_id=review["reviewer_id"], idempotency_key=new_record_id(), review_id=review["id"],
        request_digest=canonical_json_hash(request_body),
    ))
    await session.execute(text("""UPDATE public.review_leases SET status='consumed',
        close_reason='review_recorded',closed_at=clock_timestamp() WHERE id=:id"""), {"id": review["review_lease_id"]})
    await session.execute(text("""UPDATE public.review_queue_entries SET queue_state='closed',
        closed_reason='review_recorded',active_lease_id=NULL,closed_at=clock_timestamp() WHERE id=:id"""),
        {"id": review["review_queue_entry_id"]})
