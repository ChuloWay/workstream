"""Deterministic external runtime and canonical guide owners for the isolated API drill."""

from unittest.mock import patch
from uuid import UUID

from sqlalchemy import text

from app.core.config import get_settings
from app.core.project_agents import project_guide_runtime_configuration
from app.db.session import get_session_factory
from app.interfaces.external_services import ExternalServiceAdapterFactory
from app.interfaces.project_agents import (
    ProjectGuideAgentRuntime,
    ProjectGuideCompilationResult,
    SubmissionArtifactPolicyProposal,
    PROJECT_GUIDE_COMPILATION_AGENT_NAME,
    PROJECT_GUIDE_COMPILATION_AGENT_VERSION,
    PROJECT_GUIDE_COMPILATION_SCHEMA_VERSION,
)
from app.modules.projects.api.guide_compilation import (
    ProjectGuideCompilationDelivery,
    ProjectGuideCompilationExecutionCommand,
    ProjectGuideCompilationExecutionClassification,
)
from app.modules.projects.api.guide_compilation_projections import ProjectGuideProjectionCommand
from app.modules.projects.guide_compilation.automatic_request import (
    AutomaticCompilationInputs,
    automatic_operation_id,
)
from app.modules.projects.guide_compilation.service import GuideCompilationService
from app.workers import project_setup as worker
from run_isolated_tests import NAME_RE


class E2EProjectGuideRuntime:
    """One deterministic external inference, with the production closed result contract."""

    def __init__(self, configuration):
        self.identity = configuration.adapter_identity
        self.calls = 0

    async def compile_project_guide(self, context):
        self.calls += 1
        return ProjectGuideCompilationResult(
            status="draft_ready",
            findings=(),
            submission_artifact_policy=SubmissionArtifactPolicyProposal(
                required_artifacts=("answer",),
                maximum_file_size_bytes=1_000_000,
                maximum_package_size_bytes=5_000_000,
            ),
            requirements=(),
            pre_submit_bindings=(),
            post_submit_bindings=(),
            capability_suggestions=(),
            setup_notes=(),
            agent_name=PROJECT_GUIDE_COMPILATION_AGENT_NAME,
            agent_version=PROJECT_GUIDE_COMPILATION_AGENT_VERSION,
            schema_version=PROJECT_GUIDE_COMPILATION_SCHEMA_VERSION,
        )


def runtime_factory(runtime):
    """Register the isolated external test adapter through the shared typed factory."""

    def create(configuration):
        factory = ExternalServiceAdapterFactory[ProjectGuideAgentRuntime](
            "project_guide_compilation"
        )
        factory.register(configuration.runtime_key, lambda: runtime)
        return factory.create(configuration.runtime_key)

    return create


async def compile_live_guide(delivery: ProjectGuideCompilationDelivery) -> dict:
    """Drive the sole worker delivery and prove its finalization replays without inference."""
    runtime = E2EProjectGuideRuntime(project_guide_runtime_configuration(get_settings()))
    with patch.object(worker, "create_project_guide_runtime", runtime_factory(runtime)):
        first = await worker._run_project_guide_compilation(delivery)
        replay = await worker._run_project_guide_compilation(delivery)
    assert first == replay, "live finalization replay changed the receipt"
    assert first["status"] == "policy_draft_ready", first
    assert runtime.calls == 1, "live replay invoked inference again"
    return first


async def project_unfinalized_task_fixture(delivery: ProjectGuideCompilationDelivery) -> dict:
    """Preserve canonical source custody for isolated task fixtures; never finalize this guide."""
    sessions = get_session_factory()
    async with sessions() as session:
        database = await session.scalar(text("select current_database()"))
        if NAME_RE.fullmatch(str(database)) is None:
            raise RuntimeError("task lineage fixture requires an isolated E2E database")
        finalization = await session.scalar(
            text("select 1 from project_guide_setup_finalizations where setup_run_id=:id"),
            {"id": str(delivery.setup_run_id)},
        )
        if finalization:
            raise RuntimeError("task lineage fixture refuses finalized setup")
    configuration = project_guide_runtime_configuration(get_settings())
    runtime = E2EProjectGuideRuntime(configuration)
    with patch.object(worker, "create_project_guide_runtime", runtime_factory(runtime)):
        coordinator = worker._coordinator(sessions)
        await coordinator._admit(delivery)
        async with sessions() as session:
            async with worker.guide_compilation_request_authority(
                session, automatic_operation_id(delivery.setup_run_id, delivery.setup_generation)
            ) as (authority, actor):
                request = await GuideCompilationService(
                    session,
                    authority,
                    automatic_inputs=AutomaticCompilationInputs(
                        coordinator._material(session),
                        coordinator._pre,
                        coordinator._post,
                        configuration,
                    ),
                ).request_automatic(actor=actor, setup_run_id=delivery.setup_run_id)
        outcome = await coordinator._execution.execute(
            ProjectGuideCompilationExecutionCommand(attempt_id=request.attempt_id)
        )
        assert outcome.classification is ProjectGuideCompilationExecutionClassification.PERSISTED, (
            outcome
        )
        command = ProjectGuideProjectionCommand(attempt_id=UUID(str(outcome.attempt_id)))
        report = await coordinator._projections.project_guide_sufficiency(command)
        policy = await coordinator._projections.project_submission_artifact_policy(command)
    assert runtime.calls == 1
    return {
        "output_sufficiency_report_id": str(report.output_id),
        "output_submission_artifact_policy_id": str(policy.output_id),
    }
