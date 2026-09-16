"""Real ZIP, ART custody and hidden TASK creation with exact contribution lineage."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.adapters.artifacts import get_submission_bundle_preparation_command
from app.api.deps.authorization import compose_hidden_submission_creation_command
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.api.service_identities import ServiceIdentity
from app.modules.artifacts.api import (
    SubmissionBundlePreparationRequest,
    SubmissionAdmissionConsumptionError,
)
from app.modules.artifacts.authorization import (
    PreparedArtifactInternalAuthority,
    PreparedSubmissionBundlePreparationAuthorization,
)
from app.modules.artifacts.models import (
    ArtifactVerificationJob,
    SubmissionBundleAdmission,
    ArtifactBinding,
)
from app.modules.artifacts.service import ArtifactStorageOrchestrator
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from app.modules.tasks.api import SubmissionCreationRequest, TaskSubmissionContextUnavailable
from app.modules.tasks.models import Submission, TaskAssignment, WorkstreamTask
from tests.pre_submit_test_helpers import approved_pre_submit_fixture
from tests.submission_preparation_auth_helpers import install_submitter_grant
from tests.tasks.lineage_fixtures import seed_started_task_for_artifact_test
from tests.test_artifact_admission import (
    _settings,
    _namespace,
    _local_store,
    _context,
    _seed_human_actor,
)
from tests.test_default_pre_submit_execution import _archive, _bytes
from app.modules.checkers.catalogue import build_pre_submission_checker_catalogue


async def _seed_services(factory):
    async with factory.begin() as session:
        for identity in (
            ServiceIdentity.ARTIFACT_MATERIALIZER,
            ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            ServiceIdentity.ARTIFACT_VERIFIER,
            ServiceIdentity.ARTIFACT_BINDING,
        ):
            actor_id, link_id = str(uuid4()), str(uuid4())
            session.add(
                ActorProfile(
                    id=actor_id,
                    actor_kind="service",
                    status="active",
                    provisioning_method="manual_service_provisioning",
                    service_identity=identity.value,
                    created_by="cp08-test",
                )
            )
            session.add(
                ActorIdentityLink(
                    id=link_id,
                    actor_profile_id=actor_id,
                    issuer="flow-test",
                    subject=actor_id,
                    subject_kind="service",
                    status="active",
                    linked_by="cp08-test",
                )
            )


async def _verified_admission(factory, store, namespace, settings, context, request):
    """Run the real ART command and independent verifier, returning its ready admission."""
    http = Request(
        {
            "type": "http",
            "headers": [],
            "app": SimpleNamespace(
                state=SimpleNamespace(
                    settings=settings,
                    pre_submission_checker_catalogue=build_pre_submission_checker_catalogue(),
                )
            ),
        }
    )
    async with factory() as session:
        put_authority = PreparedArtifactInternalAuthority(
            session,
            service_identity=ServiceIdentity.ARTIFACT_PUT_RESOLVER,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        result = await get_submission_bundle_preparation_command(
            http,
            session,
            put_authority,
            PreparedSubmissionBundlePreparationAuthorization(session, context),
        ).prepare(request)
        assert result.put_attempt_id is not None
    async with factory() as session:
        job_id = await session.scalar(
            select(ArtifactVerificationJob.id).where(
                ArtifactVerificationJob.originating_put_attempt_id == str(result.put_attempt_id)
            )
        )
        assert job_id is not None
        await session.rollback()
        verifier = PreparedArtifactInternalAuthority(
            session,
            service_identity=ServiceIdentity.ARTIFACT_VERIFIER,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        assert (
            await ArtifactStorageOrchestrator(
                session, store, namespace, settings, verifier
            ).verify_object(UUID(job_id))
            == "verified"
        )
    async with factory() as session:
        admission = (await session.scalars(select(SubmissionBundleAdmission))).one()
        assert admission.status == "ready"
        admission_id = UUID(admission.id)
    return admission_id


async def test_real_zip_admission_and_hidden_creation_copy_exact_assignment(
    isolated_database_env,
    tmp_path,
):
    engine = create_async_engine(isolated_database_env)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = _settings(tmp_path, maximum_bytes=1024 * 1024)
    namespace = _namespace(settings)
    bootstrap, store = _local_store(settings, namespace)
    try:
        plan, policy = await approved_pre_submit_fixture(factory, namespace, guide_version="v1")
        context = _context()
        await _seed_services(factory)
        task_id, assignment_id = uuid4(), uuid4()
        async with factory.begin() as session:
            await _seed_human_actor(session, context)
        async with engine.begin() as connection:
            params = dict(
                task=str(task_id),
                assignment=str(assignment_id),
                project=str(plan.lineage.project_id),
                actor=str(context.actor_profile_id),
            )
            await seed_started_task_for_artifact_test(connection, params)
            await install_submitter_grant(connection, params)
        request = SubmissionBundlePreparationRequest(
            actor=ActorIdentityFacts(
                context.actor_profile_id, context.identity_link_id, ActorKind.HUMAN
            ),
            request_id=context.request_id,
            correlation_id=context.correlation_id,
            task_id=task_id,
            assignment_id=assignment_id,
            predecessor_submission_id=None,
            idempotency_key=uuid4(),
            summary="Completed the required project work and included evidence.",
            contributor_attestation="I confirm no confidential client data, credentials, or copied source material is included in this submission; rights_confirmed. "
            + " ".join(policy["attestation_terms"]),
            media_type="application/zip",
            byte_source=_bytes(_archive(evidence_path=policy["evidence_path"])),
        )
        admission_id = await _verified_admission(
            factory, store, namespace, settings, context, request
        )
        creation = SubmissionCreationRequest(
            task_id=task_id,
            assignment_id=assignment_id,
            contributor_id=context.actor_profile_id,
            predecessor_submission_id=None,
            admission_id=admission_id,
            summary=request.summary,
            contributor_attestation=request.contributor_attestation,
        )
        # ART rejection occurs after TASK insertion; the command must roll the
        # entire root transaction back without stranding a staged Submission.
        async with factory() as session:
            with pytest.raises(SubmissionAdmissionConsumptionError):
                await compose_hidden_submission_creation_command(
                    session,
                    context,
                    request_id=uuid4(),
                    correlation_id=uuid4(),
                ).create(replace(creation, admission_id=uuid4()))
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(Submission)) == 0
            admission = await session.get(SubmissionBundleAdmission, str(admission_id))
            assert admission.status == "ready"

        async def create():
            async with factory() as session:
                return await compose_hidden_submission_creation_command(
                    session,
                    context,
                    request_id=uuid4(),
                    correlation_id=uuid4(),
                ).create(creation)

        results = await asyncio.wait_for(
            asyncio.gather(create(), create(), return_exceptions=True), 30
        )
        successes = [value for value in results if not isinstance(value, BaseException)]
        failures = [value for value in results if isinstance(value, BaseException)]
        assert len(successes) == len(failures) == 1, results
        assert isinstance(failures[0], TaskSubmissionContextUnavailable), results
        created = successes[0]
        async with factory() as session:
            task = await session.get(WorkstreamTask, str(task_id))
            assignment = await session.get(TaskAssignment, str(assignment_id))
            submission = await session.get(Submission, str(created.submission_id))
            admission = await session.get(SubmissionBundleAdmission, str(admission_id))
            binding = await session.get(ArtifactBinding, str(created.artifact_binding_id))
            assert (
                submission.contribution_policy_version_id
                == assignment.submitter_contribution_policy_version_id
                == task.locked_contribution_policy_version_id
            )
            assert submission.task_assignment_id == assignment.id
            assert submission.submission_bundle_admission_id == admission.id
            assert submission.artifact_binding_id == binding.id
            assert (
                submission.artifact_content_id
                == binding.content_id
                == admission.artifact_content_id
            )
            assert admission.status == "consumed"
            assert admission.consumed_by_submission_id == submission.id
            assert submission.locked_payment_policy_version is None
            assert await session.scalar(select(func.count()).select_from(Submission)) == 1
    finally:
        bootstrap.close()
        await engine.dispose()
