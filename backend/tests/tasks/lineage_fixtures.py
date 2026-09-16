"""Canonical initial stamping for downstream ART arrangements, not claim authority proof."""

from app.core.config import get_settings

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.tasks import task_service
from app.modules.tasks.models import TaskAssignment, WorkstreamTask
from app.schemas.auth import ActorContext


async def seed_started_task_for_artifact_test(connection, params):
    """Screen/ready through TASK, then arrange the exact assignment for ART-only tests."""
    async with AsyncSession(bind=connection, expire_on_commit=False) as session:
        task = WorkstreamTask(
            id=params["task"],
            project_id=params["project"],
            title="Evidence task",
            description="Complete the work described by the approved guide.",
            acceptance_criteria="The work and evidence satisfy the guide.",
            status="draft",
            created_by=params["actor"],
        )
        session.add(task)
        await session.flush()
        actor = ActorContext(
            actor_id=params["actor"],
            external_subject=params["actor"],
            external_issuer="flow-test",
            roles=("project_manager",),
            claim_snapshot={},
            auth_source="dev_mock",
            is_dev_auth=True,
        )
        service = task_service(session, settings=get_settings())
        await service.move_to_screening(actor, task.id, "ART fixture initial screening")
        await service.release_to_ready(actor, task.id, "ART fixture ready")
        session.add(
            TaskAssignment(
                id=params["assignment"],
                task_id=task.id,
                project_id=task.project_id,
                contributor_id=params["actor"],
                assigned_by=params["actor"],
                status="active",
                submitter_contribution_policy_version_id=task.locked_contribution_policy_version_id,
            )
        )
        task.assigned_to = params["actor"]
        task.status = "in_progress"
        await session.flush()
