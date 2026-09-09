"""A second real setup/material generation for cross-generation custody probes."""

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import null, select, text

from app.interfaces.artifact_operations import GuideSufficiencyMaterialRequest
from app.interfaces.project_agents import VerifiedGuideMaterialSnapshot
from app.modules.artifacts.guide_sufficiency_material import (
    SqlAlchemyGuideSufficiencyMaterialAdapter,
)
from app.modules.artifacts.models import (
    GuideSourceArtifactBinding,
    GuideSourceFormatClassification,
    GuideSourceExtractionAttempt,
    GuideSourceExtractionUsage,
)
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.models import ProjectSetupRun, ProjectGuide, GuideSourceSnapshot
from app.modules.projects.service import build_verified_guide_sufficiency_material
from app.modules.projects.api.setup_identity import project_guide_compilation_task_id
from ..helpers import context


async def clone_row(session, model, source_id, **changes):
    """Copy a real parent row while naming each new immutable lineage edge."""
    source = await session.get(model, str(source_id))
    assert source is not None
    values = {column.key: getattr(source, column.key) for column in model.__table__.columns}
    values.update(changes)
    row = model(**values)
    session.add(row)
    await session.flush()
    return row


async def second_generation(factory, values):
    """Persist independent binding/classification/attempt/usage before rebuilding material."""
    async with factory() as session, session.begin():
        await session.execute(text("alter table project_setup_runs disable trigger user"))
        setup_id = str(values["setup_2"])
        source = await session.get(ProjectSetupRun, str(values["setup_1"]))
        created = source.created_at + timedelta(microseconds=1)
        await clone_row(
            session,
            ProjectSetupRun,
            values["setup_1"],
            id=setup_id,
            setup_generation=2,
            created_at=created,
            updated_at=created,
            # ORM JSON None becomes JSON null; a pristine setup requires SQL NULL.
            post_submit_derivation_summary=null(),
            celery_task_id=project_guide_compilation_task_id(setup_id, 2),
        )
        await session.execute(text("alter table project_setup_runs enable trigger user"))
        latest = await ProjectRepository(session).lock_latest_project_setup_run(
            str(values["project"]), str(values["guide"]), "v1"
        )
        assert latest.id == setup_id and latest.setup_generation == 2
        assert await session.scalar(
            select(ProjectSetupRun.post_submit_derivation_summary.is_(None)).where(
                ProjectSetupRun.id == setup_id
            )
        )
        original_binding = await session.scalar(select(GuideSourceArtifactBinding))
        original_classification = await session.scalar(select(GuideSourceFormatClassification))
        original_attempt = await session.scalar(select(GuideSourceExtractionAttempt))
        original_usage = await session.scalar(select(GuideSourceExtractionUsage))
        binding, classification, attempt, usage = (str(uuid4()) for _ in range(4))
        await clone_row(
            session,
            GuideSourceArtifactBinding,
            original_binding.id,
            id=binding,
            project_setup_run_id=setup_id,
            setup_generation=2,
        )
        await clone_row(
            session,
            GuideSourceFormatClassification,
            original_classification.id,
            id=classification,
            binding_id=binding,
            setup_generation=2,
        )
        await clone_row(
            session,
            GuideSourceExtractionAttempt,
            original_attempt.id,
            id=attempt,
            binding_id=binding,
            classification_id=classification,
            setup_generation=2,
        )
        await clone_row(
            session,
            GuideSourceExtractionUsage,
            original_usage.id,
            id=usage,
            binding_id=binding,
            extraction_attempt_id=attempt,
            project_setup_run_id=setup_id,
            setup_generation=2,
        )
        material = await SqlAlchemyGuideSufficiencyMaterialAdapter(session).load(
            GuideSufficiencyMaterialRequest(
                project_id=values["project"],
                guide_id=values["guide"],
                guide_source_snapshot_id=values["snapshot"],
                project_setup_run_id=values["setup_2"],
                setup_generation=2,
            )
        )
        guide = await session.get(ProjectGuide, str(values["guide"]))
        snapshot = await session.get(GuideSourceSnapshot, str(values["snapshot"]))
        verified = VerifiedGuideMaterialSnapshot.from_material(
            build_verified_guide_sufficiency_material(guide, snapshot, material.source_items)
        )
    return context(values, generation=2).model_copy(update={"material": verified})
