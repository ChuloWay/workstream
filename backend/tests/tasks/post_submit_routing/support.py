"""Real completed checker sources and direct-SQL routing-source helpers."""

from contextlib import asynccontextmanager
from dataclasses import asdict
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select, text

from app.adapters.tasks import submitted_bundle_port
from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.core.identifiers import new_record_id
from app.modules.actors.models import ActorIdentityLink
from app.modules.artifacts.api import SubmissionBundlePreparationRequest
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.checkers.api import (
    ExpectedPostSubmitContext,
    ObservedPostSubmitContext,
    PostSubmitEvidenceEntry,
    PostSubmitPolicyInputs,
)
from app.modules.checkers.models import CheckerRun
from app.modules.projects.models import (
    EffectiveProjectSubmissionArtifactPolicy,
    ReviewPolicy,
)
from app.modules.tasks.api import SubmissionCreationRequest
from app.modules.tasks.api.post_submit_routing import TaskPostSubmitManifestFacts
from app.modules.tasks.api.submitted_bundle import SubmittedBundleRequest
from app.modules.tasks.api.transition_audit import TaskPolicyLineage
from app.modules.tasks.models import Submission, TaskAssignment, WorkstreamTask
from tests.checkers.execution.support import live_executor, reserve
from tests.checkers.post_submit.support import change_request
from tests.post_submit_materialization_helpers import material_fixture
from tests.tasks.lineage_fixtures import seed_started_task_for_artifact_test
from tests.tasks.submission_lineage_support import _verified_admission
from tests.test_artifact_admission import _context
from tests.test_default_pre_submit_execution import _bytes


SOURCE_COLUMNS = (
    "id",
    "created_at",
    "project_id",
    "task_id",
    "submission_id",
    "submission_version",
    "assignment_id",
    "contributor_id",
    "contribution_policy_version_id",
    "checker_run_id",
    "evaluation_request_id",
    "request_digest",
    "evaluation_generation",
    "result_id",
    "result_digest",
    "completion_event_id",
    "execute_evidence_id",
    "finalize_evidence_id",
    "human_review_required",
    "replica_id",
    "content_sha256",
    "byte_count",
    "semantic_manifest_sha256",
)

_INSERT_SOURCE_WITH_CREATED_AT = text(
    "INSERT INTO public.task_post_submit_routing_manifests ("
    + ",".join(SOURCE_COLUMNS)
    + ") VALUES ("
    + ",".join(f":{column}" for column in SOURCE_COLUMNS)
    + ")"
)
_DEFAULTED_SOURCE_COLUMNS = tuple(
    column for column in SOURCE_COLUMNS if column != "created_at"
)
_INSERT_SOURCE = text(
    "INSERT INTO public.task_post_submit_routing_manifests ("
    + ",".join(_DEFAULTED_SOURCE_COLUMNS)
    + ") VALUES ("
    + ",".join(f":{column}" for column in _DEFAULTED_SOURCE_COLUMNS)
    + ")"
)


def as_uuid(value) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def other_hash(value: str) -> str:
    """Return another syntactically valid SHA-256 token."""
    suffix = "0" if value[-1] != "0" else "1"
    return value[:-1] + suffix


async def insert_source(session, values: dict) -> None:
    """Insert exactly one source row through the public SQL boundary."""
    statement = _INSERT_SOURCE_WITH_CREATED_AT if "created_at" in values else _INSERT_SOURCE
    await session.execute(statement, values)


async def source_rows(session) -> list[dict]:
    return list(
        (
            await session.execute(
                text(
                    "SELECT to_jsonb(source) FROM "
                    "public.task_post_submit_routing_manifests AS source ORDER BY source.id"
                )
            )
        ).scalars()
    )


async def rebuild_real_request(h) -> None:
    """Replace permissive helper inputs with archive-backed locked-policy facts."""
    async with h.factory() as session:
        submission = await session.get(Submission, str(h.request.submission_id))
        effective = await session.get(
            EffectiveProjectSubmissionArtifactPolicy,
            submission.locked_effective_project_submission_artifact_policy_id,
        )
        assert effective is not None
        assert effective.effective_policy_hash == h.request.expected_context.effective_policy_hash
        policy = effective.effective_policy

    manifest = {item.artifact: item for item in h.request.structural_input.manifest}
    evidence = []
    required_evidence = [
        str(item["key"])
        for item in policy.get("required_evidence", ())
        if item.get("required", True)
    ]
    for key in required_evidence:
        path = "evidence/" + key
        entry = manifest[path]
        evidence.append(
            PostSubmitEvidenceEntry(
                label=key,
                type="file",
                uri=path,
                hash=entry.hash,
                key=key,
                required_evidence_key=key,
            )
        )
    policy_inputs = PostSubmitPolicyInputs(
        required_evidence_keys=tuple(required_evidence),
        required_artifact_paths=tuple(
            str(item["path"])
            for item in policy.get("required_artifacts", ())
            if item.get("required", True)
        ),
        forbidden_artifact_patterns=tuple(
            str(item["pattern"])
            for item in policy.get("forbidden_artifacts", ())
            if item.get("pattern")
        ),
        required_attestation_terms=tuple(
            str(item) for item in policy.get("attestation_terms", ())
        ),
    )
    h.request = change_request(
        h.request,
        structural_input=h.request.structural_input.model_copy(
            update={"evidence": tuple(evidence), "policy_inputs": policy_inputs}
        ),
    )
    assert h.request.request_sha256 == change_request(h.request).request_sha256


async def next_request(h, *, structural_input=None):
    """Build a genuine later generation for the same immutable Submission."""
    request = change_request(
        h.request,
        evaluation_request_id=new_record_id(),
        evaluation_generation=h.request.evaluation_generation + 1,
        **({"structural_input": structural_input} if structural_input is not None else {}),
    )
    h.request = request
    return request


async def source_values(h, run_id=None) -> dict:
    """Read one row's values only from canonical persisted owners."""
    async with h.factory() as session:
        run = await session.get(CheckerRun, str(run_id or h.result.attempt_id))
        submission = await session.get(Submission, str(h.request.submission_id))
        task = await session.get(WorkstreamTask, submission.task_id)
        assignment = await session.get(TaskAssignment, submission.task_assignment_id)
        review = await session.get(ReviewPolicy, submission.locked_review_policy_id)
        assert all(item is not None for item in (run, submission, task, assignment, review))
    material = run.material_custody or h.material
    return {
        "id": new_record_id(),
        "project_id": as_uuid(run.project_id),
        "task_id": as_uuid(run.task_id),
        "submission_id": as_uuid(run.submission_id),
        "submission_version": run.submission_version,
        "assignment_id": as_uuid(submission.task_assignment_id),
        "contributor_id": as_uuid(submission.contributor_id),
        "contribution_policy_version_id": as_uuid(
            submission.contribution_policy_version_id
        ),
        "checker_run_id": as_uuid(run.id),
        "evaluation_request_id": as_uuid(run.evaluation_request_id),
        "request_digest": run.request_digest,
        "evaluation_generation": run.evaluation_generation,
        "result_id": as_uuid(run.result_id),
        "result_digest": run.result_digest or h.source["result_digest"],
        "completion_event_id": as_uuid(
            run.completion_event_id or h.source["completion_event_id"]
        ),
        "execute_evidence_id": as_uuid(
            run.execute_evidence_id or h.source["execute_evidence_id"]
        ),
        "finalize_evidence_id": as_uuid(
            run.finalize_evidence_id or h.source["finalize_evidence_id"]
        ),
        "human_review_required": review.human_review_required,
        "replica_id": as_uuid(material["replica_id"]),
        "content_sha256": material["content_sha256"],
        "byte_count": material["byte_count"],
        "semantic_manifest_sha256": material["semantic_manifest_sha256"],
    }


async def joined_source_facts(h, stored: dict) -> TaskPostSubmitManifestFacts:
    """Construct the public detached value from canonical join-only owners."""
    async with h.factory() as session:
        submission = await session.get(Submission, str(stored["submission_id"]))
        task = await session.get(WorkstreamTask, submission.task_id)
        predecessor = (
            await session.get(Submission, submission.supersedes_submission_id)
            if submission.supersedes_submission_id
            else None
        )
        run = await session.get(CheckerRun, str(stored["checker_run_id"]))
    material = run.material_custody
    lineage = TaskPolicyLineage(
        locked_guide_version=submission.locked_guide_version,
        locked_guide_source_snapshot_id=as_uuid(
            submission.locked_guide_source_snapshot_id
        ),
        locked_guide_source_snapshot_hash=submission.locked_guide_source_snapshot_hash,
        locked_effective_project_submission_artifact_policy_id=as_uuid(
            submission.locked_effective_project_submission_artifact_policy_id
        ),
        locked_effective_project_submission_artifact_policy_hash=(
            submission.locked_effective_project_submission_artifact_policy_hash
        ),
        locked_pre_submit_checker_policy_id=as_uuid(
            submission.locked_pre_submit_checker_policy_id
        ),
        locked_pre_submit_checker_bundle_hash=submission.locked_pre_submit_checker_bundle_hash,
        locked_post_submit_checker_policy_id=as_uuid(
            submission.locked_post_submit_checker_policy_id
        ),
        locked_post_submit_checker_policy_version=(
            submission.locked_post_submit_checker_policy_version
        ),
        locked_post_submit_checker_policy_hash=(
            submission.locked_post_submit_checker_policy_hash
        ),
        locked_review_policy_id=as_uuid(submission.locked_review_policy_id),
        locked_review_policy_generation=submission.locked_review_policy_generation,
        locked_review_policy_hash=submission.locked_review_policy_hash,
        locked_revision_policy_id=as_uuid(submission.locked_revision_policy_id),
        locked_revision_policy_generation=submission.locked_revision_policy_generation,
        locked_revision_policy_hash=submission.locked_revision_policy_hash,
        locked_contribution_policy_version_id=as_uuid(
            task.locked_contribution_policy_version_id
        ),
    )
    return TaskPostSubmitManifestFacts(
        **{column: stored[column] for column in SOURCE_COLUMNS},
        predecessor_submission_id=(
            as_uuid(submission.supersedes_submission_id)
            if submission.supersedes_submission_id
            else None
        ),
        predecessor_submission_version=predecessor.version if predecessor else None,
        admission_id=as_uuid(material["admission_id"]),
        binding_id=as_uuid(material["binding_id"]),
        content_id=as_uuid(material["content_id"]),
        locked_policy=lineage,
        routing_recommendation=run.routing_recommendation,
    )


@asynccontextmanager
async def completed_source(
    tmp_path,
    database_url,
    *,
    provision_services=True,
    storage_settings=None,
):
    """Yield one real authorized allow-review run and its valid source scalars."""
    async with material_fixture(
        tmp_path,
        database_url,
        provision_services=provision_services,
        storage_settings=storage_settings,
    ) as h:
        await rebuild_real_request(h)
        await reserve(h)
        result = await live_executor(h).evaluate_post_submission(h.request)
        async with h.factory() as session:
            run = await session.get(CheckerRun, str(result.attempt_id))
            assert result.outcome == "completed"
            assert run.routing_recommendation == "allow_review"
            material = dict(run.material_custody)
        h.result, h.material = result, material
        h.source = {}
        h.source = await source_values(h)
        yield h


async def completed_sibling_source(h):
    """Build a real allow-review source for another task in the same project."""
    task_id, assignment_id = new_record_id(), new_record_id()
    async with h.factory() as session:
        original = await session.get(Submission, str(h.request.submission_id))
        identity_link_id = await session.scalar(
            select(ActorIdentityLink.id).where(
                ActorIdentityLink.actor_profile_id == original.contributor_id,
                ActorIdentityLink.status == "active",
            )
        )
        assert identity_link_id is not None
    context = _context(
        actor_profile_id=as_uuid(original.contributor_id),
        identity_link_id=as_uuid(identity_link_id),
    )
    async with h.engine.begin() as connection:
        await seed_started_task_for_artifact_test(
            connection,
            {
                "task": str(task_id),
                "assignment": str(assignment_id),
                "project": str(h.request.project_id),
                "actor": str(context.actor_profile_id),
            },
        )

    preparation = SubmissionBundlePreparationRequest(
        actor=ActorIdentityFacts(
            context.actor_profile_id,
            context.identity_link_id,
            ActorKind.HUMAN,
        ),
        request_id=context.request_id,
        correlation_id=context.correlation_id,
        task_id=task_id,
        assignment_id=assignment_id,
        predecessor_submission_id=None,
        idempotency_key=new_record_id(),
        summary=h.request.structural_input.summary,
        contributor_attestation=h.request.structural_input.worker_attestation,
        media_type="application/zip",
        byte_source=_bytes(h.data),
    )
    admission_id = await _verified_admission(
        h.factory,
        h.store,
        h.namespace,
        h.settings,
        context,
        preparation,
    )
    async with h.factory() as session:
        created = await compose_hidden_submission_creation_command(
            session,
            context,
            request_id=new_record_id(),
            correlation_id=new_record_id(),
        ).create(
            SubmissionCreationRequest(
                task_id=task_id,
                assignment_id=assignment_id,
                contributor_id=context.actor_profile_id,
                predecessor_submission_id=None,
                admission_id=admission_id,
                summary=preparation.summary,
                contributor_attestation=preparation.contributor_attestation,
            )
        )
    async with h.factory() as session:
        facts = await submitted_bundle_port(session).read(
            SubmittedBundleRequest(
                h.request.project_id,
                task_id,
                created.submission_id,
            )
        )
    expected = ExpectedPostSubmitContext(**asdict(facts.context))
    structural_input = h.request.structural_input.model_copy(
        update={"observed_context": ObservedPostSubmitContext(**asdict(facts.context))}
    )
    request = change_request(
        h.request,
        evaluation_request_id=new_record_id(),
        evaluation_generation=1,
        project_id=facts.project_id,
        task_id=facts.task_id,
        assignment_id=facts.assignment_id,
        submission_id=facts.submission_id,
        submission_version=facts.submission_version,
        content_id=facts.content_id,
        binding_id=facts.binding_id,
        expected_context=expected,
        structural_input=structural_input,
    )
    sibling = SimpleNamespace(
        factory=h.factory,
        service=h.service,
        request=request,
        source={},
    )
    await reserve(sibling)
    result = await live_executor(sibling).evaluate_post_submission(request)
    async with h.factory() as session:
        run = await session.get(CheckerRun, str(result.attempt_id))
        assert result.outcome == "completed"
        assert run.routing_recommendation == "allow_review"
        sibling.material = dict(run.material_custody)
    sibling.result = result
    sibling.source = await source_values(sibling)
    return sibling


async def source_count(session) -> int:
    return int(
        await session.scalar(
            text("SELECT count(*) FROM public.task_post_submit_routing_manifests")
        )
    )


async def activate_successor_guide(h):
    """Activate a genuine v2 guide in the source Submission's project."""
    from uuid import uuid4

    from sqlalchemy import select

    from app.interfaces.project_agents import SubmissionArtifactPolicyProposal
    from app.modules.actors.models import ActorIdentityLink, ActorProfile
    from app.modules.projects.api.post_policy import PostPolicyApproval
    from app.modules.projects.models import ProjectGuide
    from tests.authorization.guide_activation.pg_support import activate
    from tests.projects.guide_activation.pg_support import (
        activation_command,
        publish_policy,
    )
    from tests.projects.guide_activation.source_fixtures import create_compiled_guide
    from tests.projects.guide_compilation.helpers import ids, service_actor
    from tests.projects.guide_compilation.proposals.pg_support import (
        seed_review_actor,
        seed_selected_review_revision_inputs,
    )
    from tests.projects.post_policy.pg_support import operate, prepare_post_policy

    values = ids()
    values["project"] = h.request.project_id
    async with h.factory() as session:
        setup_actor, setup_link = (
            await session.execute(
                select(ActorProfile.id, ActorIdentityLink.id)
                .join(
                    ActorIdentityLink,
                    ActorIdentityLink.actor_profile_id == ActorProfile.id,
                )
                .where(
                    ActorProfile.service_identity == "workstream.project.setup",
                    ActorIdentityLink.status == "active",
                )
            )
        ).one()
    values.update(actor=as_uuid(setup_actor), link=as_uuid(setup_link))
    manager, grant = await seed_review_actor(h.factory, h.request.project_id)
    proposal = SubmissionArtifactPolicyProposal(
        maximum_file_size_bytes=1_000_000,
        maximum_package_size_bytes=5_000_000,
        required_artifacts=("task.toml",),
        required_evidence=("results",),
        attestation_terms=("rights_confirmed",),
    )
    values, finalization = await create_compiled_guide(
        h.factory,
        values,
        manager,
        version="v2",
        artifact_proposal=proposal,
    )
    await seed_selected_review_revision_inputs(h.factory, finalization, manager)
    _, derived = await prepare_post_policy(
        h.factory,
        finalization,
        manager,
        grant,
        service_actor(values),
    )
    approved = await operate(
        h.factory,
        manager,
        finalization.project_id,
        grant,
        "approve",
        PostPolicyApproval(target=derived.target, idempotency_key=uuid4()),
    )
    _, contribution_policy = await publish_policy(h.factory, finalization.project_id)
    command = await activation_command(h.factory, approved, contribution_policy)
    async with h.factory() as session:
        current = await session.scalar(
            select(ProjectGuide).where(
                ProjectGuide.project_id == str(h.request.project_id),
                ProjectGuide.status == "active",
            )
        )
    command = command.model_copy(
        update={
            "expected_previous_active_guide_id": as_uuid(current.id),
            "expected_previous_active_guide_generation": current.mutation_generation,
        }
    )
    return await activate(h.factory, manager, command)
