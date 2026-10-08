"""Real approved guide and started task for early evaluation-capacity checks."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.identifiers import new_record_id
from app.modules.artifacts.api import SubmissionBundlePreparationRequest
from app.modules.authorization.api import ActorIdentityFacts, ActorKind
from tests.pre_submit_test_helpers import approved_pre_submit_fixture
from tests.submission_preparation_auth_helpers import install_submitter_grant
from tests.tasks.lineage_fixtures import seed_started_task_for_artifact_test
from tests.tasks.submission_lineage_support import _seed_services
from tests.test_artifact_admission import _settings, _namespace, _local_store, _context, _seed_human_actor
from tests.test_default_pre_submit_execution import _archive, _bytes


@asynccontextmanager
async def capacity_fixture(database_url, tmp_path):
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = _settings(tmp_path, maximum_bytes=1024 * 1024)
    namespace = _namespace(settings)
    bootstrap, store = _local_store(settings, namespace)
    try:
        plan, policy = await approved_pre_submit_fixture(factory, namespace, guide_version="v1")
        context = _context()
        await _seed_services(factory)
        task_id, assignment_id = new_record_id(), new_record_id()
        async with factory.begin() as session:
            await _seed_human_actor(session, context)
        async with engine.begin() as connection:
            params = dict(task=str(task_id), assignment=str(assignment_id),
                          project=str(plan.lineage.project_id), actor=str(context.actor_profile_id))
            await seed_started_task_for_artifact_test(connection, params)
            await install_submitter_grant(connection, params)
        request = SubmissionBundlePreparationRequest(
            actor=ActorIdentityFacts(context.actor_profile_id, context.identity_link_id, ActorKind.HUMAN),
            request_id=context.request_id, correlation_id=context.correlation_id,
            task_id=task_id, assignment_id=assignment_id, predecessor_submission_id=None,
            idempotency_key=new_record_id(), summary="Completed the work with verified evidence.",
            contributor_attestation="I confirm no confidential client data, credentials, or copied source material is included; rights_confirmed. "
            + " ".join(policy["attestation_terms"]), media_type="application/zip",
            byte_source=_bytes(_archive(evidence_path=policy["evidence_path"])),
        )
        yield SimpleNamespace(factory=factory, settings=settings, namespace=namespace, store=store,
                              context=context, request=request, plan=plan, policy=policy)
    finally:
        bootstrap.close()
        await engine.dispose()
