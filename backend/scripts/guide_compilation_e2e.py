"""Deterministic external runtime and canonical guide owners for the isolated API drill."""

from unittest.mock import patch


from app.core.config import get_settings
from app.core.project_agents import project_guide_runtime_configuration
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
)
from app.workers import project_setup as worker


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


async def attach_verified_task_fixture_material(delivery, report_id):
    """Seed a verified fixture report while preserving the API-created diagnostic."""
    from dataclasses import asdict
    from uuid import UUID, uuid4
    from sqlalchemy import select, text
    from app.db.session import get_session_factory
    from app.interfaces.artifact_operations import GuideSufficiencyMaterialRequest
    from app.interfaces.project_agents import VerifiedGuideMaterialSnapshot
    from app.modules.artifacts.guide_sufficiency_material import (
        SqlAlchemyGuideSufficiencyMaterialAdapter,
    )
    from app.modules.projects.models import (
        GuideSufficiencyReport,
        GuideSufficiencyReportSourceUsage,
        GuideSourceSnapshot,
        ProjectGuide,
    )
    from app.modules.projects.service import build_verified_guide_sufficiency_material
    from run_isolated_tests import NAME_RE

    async with get_session_factory()() as session, session.begin():
        database = await session.scalar(text("select current_database()"))
        if NAME_RE.fullmatch(str(database)) is None:
            raise RuntimeError("task report seed requires an isolated E2E database")
        for table in (
            "project_guide_compilation_attempts",
            "project_guide_component_projection_operations",
            "project_guide_setup_finalizations",
        ):
            assert not await session.scalar(
                text("select 1 from " + table + " where setup_run_id=:id"),
                {"id": str(delivery.setup_run_id)},
            )
        report = await session.scalar(
            select(GuideSufficiencyReport)
            .where(GuideSufficiencyReport.id == report_id)
            .with_for_update()
        )
        assert report is not None and report.source_snapshot_id == str(delivery.source_snapshot_id)
        assert report.project_setup_run_id is None and report.agent_name is None
        loaded = await SqlAlchemyGuideSufficiencyMaterialAdapter(session).load(
            GuideSufficiencyMaterialRequest(
                project_id=delivery.project_id,
                guide_id=delivery.guide_id,
                guide_source_snapshot_id=delivery.source_snapshot_id,
                project_setup_run_id=delivery.setup_run_id,
                setup_generation=delivery.setup_generation,
            )
        )
        guide = await session.get(ProjectGuide, str(delivery.guide_id))
        snapshot = await session.get(GuideSourceSnapshot, str(delivery.source_snapshot_id))
        material = VerifiedGuideMaterialSnapshot.from_material(
            build_verified_guide_sufficiency_material(guide, snapshot, loaded.source_items)
        )
        diagnostic = report
        report = GuideSufficiencyReport(
            id=str(uuid4()),
            project_id=diagnostic.project_id,
            guide_id=diagnostic.guide_id,
            guide_version=diagnostic.guide_version,
            source_snapshot_id=diagnostic.source_snapshot_id,
            source_snapshot_hash=diagnostic.source_snapshot_hash,
            status=diagnostic.status,
            findings=diagnostic.findings,
            summary="Verified material for isolated downstream task fixture.",
            created_by="workstream-api-contract-fixture",
        )
        session.add(report)
        report.project_setup_run_id = str(delivery.setup_run_id)
        report.setup_generation = delivery.setup_generation
        report.agent_material_sha256 = material.canonical_payload_sha256
        report.agent_material_byte_count = len(material.canonical_payload)
        for usage in loaded.provenance:
            session.add(
                GuideSufficiencyReportSourceUsage(
                    id=str(uuid4()),
                    report_id=report.id,
                    **{
                        key: str(value) if isinstance(value, UUID) else value
                        for key, value in asdict(usage).items()
                    },
                    project_setup_run_id=str(delivery.setup_run_id),
                    setup_generation=delivery.setup_generation,
                )
            )
        await session.flush()
        usages = (
            await session.scalars(
                select(GuideSufficiencyReportSourceUsage)
                .where(GuideSufficiencyReportSourceUsage.report_id == report.id)
                .order_by(GuideSufficiencyReportSourceUsage.item_order)
            )
        ).all()
        assert len(usages) == len(loaded.provenance)
        for actual, expected in zip(usages, loaded.provenance, strict=True):
            for key, value in asdict(expected).items():
                assert getattr(actual, key) == (str(value) if isinstance(value, UUID) else value)
        await session.refresh(report)
        assert report.agent_name is None
        assert report.agent_material_sha256 == material.canonical_payload_sha256
        assert report.agent_material_byte_count == len(material.canonical_payload)
        assert diagnostic.project_setup_run_id is None and diagnostic.agent_name is None
        return report.id
