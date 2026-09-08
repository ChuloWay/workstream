"""Foreign historical parents reuse the already provisioned fixed service identity."""

from uuid import uuid4

from app.db import session as db_session
from app.modules.compensation.models import ProjectCompensationAdapterBinding
from adapter_binding_fixtures import created_binding_events
from project_create_fixtures import insert_historical_project


async def foreign_project(target, *, with_binding=False):
    """Seed distinct project/binding rows without creating another service identity."""
    project, binding = uuid4(), uuid4()
    assert project != target.project and binding != target.binding
    async with db_session.get_session_factory()() as session, session.begin():
        await insert_historical_project(
            session, project_id=str(project), name="Foreign policy", slug="foreign-" + project.hex
        )
        if with_binding:
            original = await session.get(ProjectCompensationAdapterBinding, target.binding)
            session.add(
                ProjectCompensationAdapterBinding(
                    id=binding,
                    project_id=str(project),
                    instrument_type="money",
                    adapter_actor_id=original.adapter_actor_id,
                    route_key="foreign.money",
                    status="active",
                    binding_lifecycle_version=1,
                    created_by=original.created_by,
                )
            )
            await session.flush()
            session.add(
                created_binding_events(str(project), original.created_by, binding)[0]
            )
    return project, binding
