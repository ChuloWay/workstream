"""Stored upstream prerequisites for checker/review-owner tests.

These fixtures use ART preparation, verification and consumption owners with
a scripted provider, then seed retained Submission projections with locked
lineage. CHECKERS reads these bytes with real phase authority and controlled
external-image outcomes; this is not a deployment/provider conformance proof.
"""

from uuid import UUID
from tests.retained_material_fixtures import retained_admission


from sqlalchemy import select

from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink
from app.modules.tasks.models import EvidenceItem, Submission, TaskAssignment, WorkstreamTask
from app.modules.tasks.schemas import SubmissionCreate
from app.modules.tasks.submission_composition import build_submission
from datetime import UTC, datetime


async def seed_retained_submission(
    task_id: str, payload: dict, *, predecessor_id: str | None = None,
) -> str:
    """Seed a retained locked packet with guards enabled; not an intake proof."""
    packet = SubmissionCreate.model_validate(payload)
    async with db_session.get_session_factory()() as session:
        task = await session.get(WorkstreamTask, task_id)
        assert task is not None
        assert task.status == ("needs_revision" if predecessor_id else "in_progress")
        predecessor = await session.get(Submission, predecessor_id) if predecessor_id else None
        if predecessor_id:
            assert predecessor is not None and predecessor.task_id == task_id
            assert predecessor.contributor_id == task.assigned_to
        assignment = await session.scalar(select(TaskAssignment).where(
            TaskAssignment.task_id == task_id, TaskAssignment.status == "active",
        ))
        assert assignment is not None and assignment.contributor_id == task.assigned_to
        link = await session.scalar(select(ActorIdentityLink).where(
            ActorIdentityLink.actor_profile_id == task.assigned_to,
        ))
        assert link is not None and link.status == "active"
        session.expunge_all()
        await session.rollback()
        # Detached selectors remain fixture inputs; real preparation rechecks them.
        admission_id = await retained_admission(
            db_session.get_session_factory(), task, assignment, link, packet, predecessor_id,
        )
        # Retained history includes private packet fields absent from the hidden
        # input DTO. Seed those fixture-only values before the real atomic writer
        # seals the row; all ownership, authority and dispatch guards stay enabled.
        from unittest.mock import patch
        from app.api.deps.authorization import compose_hidden_submission_creation_command
        from app.modules.tasks.api import SubmissionCreationRequest
        from app.modules.actors.api.service_identities import ServiceIdentity
        from app.modules.actors.models import ActorProfile
        from tests.test_artifact_admission import _context
        service = await session.scalar(select(ActorProfile).where(
            ActorProfile.service_identity == ServiceIdentity.ARTIFACT_BINDING.value,
        ))
        if service is None:
            service_id = str(new_record_id())
            session.add(ActorProfile(
                id=service_id, actor_kind="service", status="active",
                provisioning_method="manual_service_provisioning",
                service_identity=ServiceIdentity.ARTIFACT_BINDING.value,
                created_by="retained-history-fixture",
            ))
            session.add(ActorIdentityLink(
                id=str(new_record_id()), actor_profile_id=service_id,
                issuer="flow-test", subject=service_id, subject_kind="service",
                status="active", linked_by="retained-history-fixture",
            ))
        await session.commit()

        def retained_packet(**values):
            identifier = values["submission_id"]
            return build_submission(
                **values, package_uri=packet.package_uri, package_hash=packet.package_hash,
                artifact_hash_manifest=[entry.model_dump() for entry in packet.artifact_hash_manifest],
                evidence_items=[EvidenceItem(
                    id=str(new_record_id()), submission_id=identifier, type=item.type,
                    label=item.label, uri=item.uri, hash=item.hash,
                    size_bytes=item.size_bytes, metadata_json=item.metadata,
                    locked_at=datetime.now(UTC),
                ) for item in packet.evidence_items],
            )

        with patch("app.modules.tasks.submission_composition.build_submission", retained_packet):
            created = await compose_hidden_submission_creation_command(
                session, _context(actor_profile_id=UUID(task.assigned_to), identity_link_id=UUID(link.id)),
                request_id=new_record_id(), correlation_id=new_record_id(),
            ).create(SubmissionCreationRequest(
                admission_id=UUID(admission_id), task_id=UUID(task_id),
                assignment_id=UUID(assignment.id), contributor_id=UUID(task.assigned_to),
                predecessor_submission_id=UUID(predecessor_id) if predecessor_id else None,
                summary=packet.summary, contributor_attestation=packet.worker_attestation,
            ))
        submission_id = str(created.submission_id)
    return submission_id


async def seed_retained_checker_run(submission_id: str, *, verdict="passed", state="completed", generation=1) -> str:
    """Execute closed history with real phase custody and controlled image verdicts."""
    from tests.checkers.execution.storage_fixture import seed_storage_run
    return await seed_storage_run(db_session.get_session_factory(), submission_id,
                                  verdict=verdict, state=state, generation=generation)


async def route_retained_checker_remediation(submission_id: str, *, generation: int = 1) -> str:
    """Give a retained packet the real completed failure and authorized route."""
    from types import SimpleNamespace

    from sqlalchemy import text

    from app.adapters.tasks import evaluation_completion_handler
    from app.modules.checkers.models import CheckerRun
    from app.modules.outbox.api import HandlerOutcome
    from tests.authorization.post_submit_routing.support import provision_router
    from tests.checkers.execution.storage_fixture import storage_request
    from tests.tasks.post_submit_routing.outcome_support import invoked_completion

    factory = db_session.get_session_factory()
    run_id = await seed_retained_checker_run(
        submission_id, verdict="failed", generation=generation,
    )
    async with factory() as session:
        run = await session.get(CheckerRun, run_id)
        assert run is not None and run.routing_recommendation == "needs_revision"
        assert run.completion_event_id is not None
        request = await storage_request(session, submission_id, generation=generation)
    await provision_router(factory)
    source = SimpleNamespace(
        factory=factory,
        service=None,
        request=request,
        source={"completion_event_id": run.completion_event_id},
    )
    envelope = await invoked_completion(source)
    assert await evaluation_completion_handler(sessions=factory)(envelope) is HandlerOutcome.ACKNOWLEDGE
    async with factory() as session:
        result = (await session.execute(text("""
            SELECT m.id, m.routing_recommendation, t.status,
                   public.task_routing_outcome_complete(m) AS complete
              FROM public.task_post_submit_routing_manifests m
              JOIN public.workstream_tasks t ON t.id = m.task_id
             WHERE m.checker_run_id = :run_id
        """), {"run_id": run_id})).one()
        assert result.routing_recommendation == result.status == "needs_revision"
        assert result.complete is True
        return str(result.id)
