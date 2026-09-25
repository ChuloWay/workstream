"""Real signed actors and stored queue grants, with no allow-port replacement."""

from uuid import UUID

from sqlalchemy import update

from app.db import session as db_session
from app.modules.projects.models import Project
from tests.authorization.task_authority.test_postgresql import project_manager, grant

PATHS = {
    "ready": "/api/v1/projects/{project}/tasks/ready",
    "management": "/api/v1/projects/{project}/tasks",
    "operational": "/api/v1/operations/projects/{project}/tasks",
}
ACTIONS = {
    "ready": "task.queue.read", "management": "project.task.queue.read",
    "operational": "operations.task.queue.read",
}


async def project_fixture(label="Queue", status="active"):
    from tests.projects.guide_activation.pg_support import activation_case
    from tests.authorization.guide_activation.pg_support import activate

    factory = db_session.get_session_factory()
    url = factory.kw["bind"].url.render_as_string(hide_password=False)
    async with activation_case(url) as (sessions, command, actor, grant, world, policy):
        await activate(sessions, actor, command)
        project = command.target.proposal.project_id
    if status != "active":
        async with factory() as session, session.begin():
            await session.execute(update(Project).where(Project.id == str(project)).values(status=status))
    return project


async def grant_queue_role(access, project: UUID, role: str):
    """Issue real project/admin grants through their canonical HTTP operations."""
    if role in {"submitter", "reviewer"}:
        manager = await project_manager(access, project)
        return await grant(access, manager, project, role)
    return await access.signed.grant(
        access.admin, access.target, role="project_manager" if role == "system_manager" else role,
        project_id=None if role in {"system_manager", "operator"} else project,
    )
