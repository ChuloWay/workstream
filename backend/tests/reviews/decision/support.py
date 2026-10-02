"""Isolated storage fixtures; these are not authorized product decisions."""

import hashlib
import zipfile
from contextlib import asynccontextmanager
from dataclasses import asdict
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import insert, select, text

from app.adapters.tasks import submitted_bundle_port
from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.core.identifiers import new_record_id
from app.modules.actors.models import ActorIdentityLink
from app.modules.artifacts.api import SubmissionBundlePreparationRequest
from app.modules.artifacts.submission_manifest import build_submission_manifest
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.checkers.api import (
    ExpectedPostSubmitContext,
    ObservedPostSubmitContext,
    PostSubmitManifestEntry,
)
from app.modules.checkers.models import CheckerRun
from app.modules.reviews.decision.models import (
    FindingResolution,
    Review,
    ReviewDecisionRequest,
    ReviewFinding,
)
from app.modules.reviews.decision.schemas import ReviewFindingInput, ReviewSourceInput
from app.modules.reviews.packet.repository import ReviewPacketRepository
from app.modules.tasks.api import SubmissionCreationRequest
from app.modules.tasks.api.submitted_bundle import SubmittedBundleRequest
from app.modules.tasks.models import Submission
from tests.checkers.execution.support import live_executor, reserve
from tests.checkers.post_submit.support import change_request
from tests.reviews.packet.support import packet_source, prepare_packet
from tests.tasks.post_submit_routing.support import source_values
from tests.tasks.submission_lineage_support import _verified_admission
from tests.test_artifact_admission import _context
from tests.test_default_pre_submit_execution import _bytes


@asynccontextmanager
async def review_source(tmp_path, database_url, **options):
    async with packet_source(tmp_path, database_url, **options) as h:
        await attach_review_source(h)
        yield h


async def attach_review_source(h):
    async with h.factory() as session:
        packet = await ReviewPacketRepository(session).store(h.lease_id, h.membership)
        await session.commit()
        row = (
            (
                await session.execute(
                    text("""
            SELECT s.*, l.reviewer_id, l.reviewer_contribution_policy_version_id,
                   c.sha256 FROM public.submissions s
            JOIN public.review_leases l ON l.id=:lease
            JOIN public.artifact_contents c ON c.id=s.artifact_content_id
            WHERE s.id=:submission
        """),
                    {"lease": h.lease_id, "submission": h.request.submission_id},
                )
            )
            .mappings()
            .one()
        )
        h.review = ReviewSourceInput(
            id=new_record_id(),
            project_id=h.membership.request.project_id,
            task_id=UUID(str(row["task_id"])),
            task_assignment_id=UUID(str(row["task_assignment_id"])),
            submission_id=UUID(str(row["id"])),
            submission_version=row["version"],
            review_queue_entry_id=h.queue_id,
            review_lease_id=h.lease_id,
            packet_manifest_id=packet.packet_manifest_id,
            packet_manifest_digest=packet.packet_manifest_digest,
            artifact_hash=row["sha256"],
            reviewer_id=UUID(str(row["reviewer_id"])),
            reviewer_contribution_policy_version_id=row["reviewer_contribution_policy_version_id"],
            locked_guide_version=row["locked_guide_version"],
            locked_review_policy_id=UUID(str(row["locked_review_policy_id"])),
            locked_review_policy_generation=row["locked_review_policy_generation"],
            locked_review_policy_hash=row["locked_review_policy_hash"],
            predecessor_review_id=None,
            decision="accept",
            summary="Verified the exact submitted work.",
            findings=(),
            resolutions=(),
        )


def finding(*, kind="blocking", label="Required result"):
    return ReviewFindingInput(
        id=new_record_id(),
        finding_kind=kind,
        area="Deliverable",
        issue=label,
        required_fix="Correct the documented result.",
    )


async def insert_review(
    session,
    source,
    *,
    header=None,
    request=None,
    close=True,
    include_request=True,
    include_children=True,
):
    """Stage raw owner rows in the caller transaction; SQL performs validation."""
    values = source.model_dump(exclude={"findings", "resolutions"})
    values.update(
        finding_count=len(source.findings),
        blocking_finding_count=sum(f.finding_kind == "blocking" for f in source.findings),
        resolution_count=len(source.resolutions),
        aggregate_digest=source.aggregate_digest,
    )
    values.update(header or {})
    for field in (
        "project_id",
        "task_id",
        "task_assignment_id",
        "submission_id",
        "reviewer_id",
        "locked_review_policy_id",
    ):
        values[field] = str(values[field])
    await session.execute(insert(Review).values(**values))
    if include_children:
        for order, member in enumerate(source.findings):
            await session.execute(
                insert(ReviewFinding).values(
                    **member.model_dump(), review_id=source.id, item_order=order
                )
            )
        for order, member in enumerate(source.resolutions):
            await session.execute(
                insert(FindingResolution).values(
                    **member.model_dump(), review_id=source.id, item_order=order
                )
            )
    if include_request:
        request_values = dict(
            id=new_record_id(),
            operation_id=new_record_id(),
            project_id=source.project_id,
            reviewer_id=source.reviewer_id,
            idempotency_key=new_record_id(),
            review_id=source.id,
            request_digest=source.request_digest,
        )
        request_values.update(request or {})
        for field in ("project_id", "reviewer_id"):
            request_values[field] = str(request_values[field])
        await session.execute(insert(ReviewDecisionRequest).values(**request_values))
    if close:
        await close_review_lease(session, source)


async def close_review_lease(session, source):
    await session.execute(
        text("""
        UPDATE public.review_leases SET status='consumed', close_reason='review_recorded',
          closed_at=clock_timestamp() WHERE id=:lease;
    """),
        {"lease": source.review_lease_id},
    )
    await session.execute(
        text("""
        UPDATE public.review_queue_entries SET queue_state='closed',closed_reason='review_recorded',
          active_lease_id=NULL,closed_at=clock_timestamp() WHERE id=:queue
    """),
        {"queue": source.review_queue_entry_id},
    )


async def _admit_successor(h):
    """Create real admitted successor bytes; only task routing is fixture-arranged."""

    async with h.factory() as session:
        prior = await session.get(Submission, str(h.request.submission_id))
        link = await session.scalar(
            select(ActorIdentityLink.id).where(
                ActorIdentityLink.actor_profile_id == prior.contributor_id,
                ActorIdentityLink.status == "active",
            )
        )
        context = _context(
            actor_profile_id=UUID(prior.contributor_id), identity_link_id=UUID(str(link))
        )
        await session.execute(
            text("UPDATE public.workstream_tasks SET status='needs_revision' WHERE id=:id"),
            {"id": h.request.task_id},
        )
        await session.commit()

    revised_bytes = BytesIO()
    with (
        zipfile.ZipFile(BytesIO(h.data)) as original,
        zipfile.ZipFile(revised_bytes, "w") as revised,
    ):
        for member in original.infolist():
            revised.writestr(member, original.read(member))
        revised.writestr(
            f"revision-{h.request.submission_version + 1}.txt", "The requested result is corrected."
        )
    revised_data = revised_bytes.getvalue()
    preparation = SubmissionBundlePreparationRequest(
        actor=ActorIdentityFacts(
            context.actor_profile_id, context.identity_link_id, ActorKind.HUMAN
        ),
        request_id=context.request_id,
        correlation_id=context.correlation_id,
        task_id=h.request.task_id,
        assignment_id=h.request.assignment_id,
        predecessor_submission_id=h.request.submission_id,
        idempotency_key=new_record_id(),
        summary=h.request.structural_input.summary,
        contributor_attestation=h.request.structural_input.worker_attestation,
        media_type="application/zip",
        byte_source=_bytes(revised_data),
    )
    admission_id = await _verified_admission(
        h.factory, h.store, h.namespace, h.settings, context, preparation
    )
    async with h.factory() as session:
        created = await compose_hidden_submission_creation_command(
            session, context, request_id=new_record_id(), correlation_id=new_record_id()
        ).create(
            SubmissionCreationRequest(
                task_id=h.request.task_id,
                assignment_id=h.request.assignment_id,
                contributor_id=context.actor_profile_id,
                predecessor_submission_id=h.request.submission_id,
                admission_id=admission_id,
                summary=preparation.summary,
                contributor_attestation=preparation.contributor_attestation,
            )
        )
    async with h.factory() as session:
        facts = await submitted_bundle_port(session).read(
            SubmittedBundleRequest(h.request.project_id, h.request.task_id, created.submission_id)
        )

    return facts, revised_data


async def _evaluate_successor(h, facts, revised_data):
    """Run real post-submit evaluation using the new admitted content identity."""
    digest = "sha256:" + hashlib.sha256(revised_data).hexdigest()
    manifest = build_submission_manifest(h.inspector.inspect(BytesIO(revised_data)))
    request = change_request(
        h.request,
        content_sha256=digest,
        byte_count=len(revised_data),
        evaluation_request_id=new_record_id(),
        evaluation_generation=1,
        submission_id=facts.submission_id,
        submission_version=facts.submission_version,
        content_id=facts.content_id,
        binding_id=facts.binding_id,
        expected_context=ExpectedPostSubmitContext(**asdict(facts.context)),
        structural_input=h.request.structural_input.model_copy(
            update={
                "observed_context": ObservedPostSubmitContext(**asdict(facts.context)),
                "package_hash": digest,
                "manifest": tuple(
                    PostSubmitManifestEntry(
                        artifact=e.normalized_path, hash=e.sha256, size_bytes=e.byte_count
                    )
                    for e in manifest.entries
                    if e.sha256 is not None
                ),
            }
        ),
    )
    successor = SimpleNamespace(
        **{**vars(h), "request": request, "source": {}, "data": revised_data, "manifest": manifest}
    )
    await reserve(successor)
    successor.result = await live_executor(successor).evaluate_post_submission(request)
    async with h.factory() as session:
        run = await session.get(CheckerRun, str(successor.result.attempt_id))
        assert run.status == "completed" and run.routing_recommendation == "allow_review"
        successor.material = dict(run.material_custody)
    successor.source = await source_values(successor)
    return successor


async def successor_source(h, *, with_packet=True):
    """Build an admitted and evaluated successor, optionally with a retained packet."""
    facts, revised_data = await _admit_successor(h)
    successor = await _evaluate_successor(h, facts, revised_data)
    if with_packet:
        await prepare_packet(successor)
        await attach_review_source(successor)
    return successor
