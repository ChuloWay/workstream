"""Native immutable source ancestry used by atomic import and provider-free replay."""

import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.artifacts.api.task_import_source import TaskImportSourceError
from app.modules.artifacts.models import ArtifactReplica
from app.modules.artifacts.task_import_sources import ArtifactTaskImportSourceCommands
from app.modules.authorization.runtime import (
    ActorKind, ActorStatus, HumanAuthorizationContext, IdentityLinkStatus,
)
from app.modules.authorization.task_import_sources import PreparedTaskImportSourceAuthorization
from tests.test_task_import_sources import (
    import_source_client as import_source_client, _declare, _path, _project,
)
from tests.test_tasks import auth_headers, task_database_env as task_database_env
from tests.tasks.test_task_import_contract import document


def _unexpected_runtime():
    raise AssertionError("immutable source replay must never acquire provider runtime")


async def test_native_binding_survives_operational_health_and_rejects_substitutions(import_source_client):
    """Current health may change; the exact verified native byte ancestry may not."""
    client = import_source_client
    project = await _project(client)
    raw = json.dumps(document()).encode()
    source = await _declare(client, project, raw)
    uploaded = await client.put(_path(project, source) + "/content",
                                headers=auth_headers() | {"Content-Type": "application/json"}, content=raw)
    assert uploaded.status_code == 200 and uploaded.json()["status"] == "verified", uploaded.text
    async with db_session.get_session_factory()() as session:
        async with session.begin():
            link = (await session.scalars(select(ActorIdentityLink).join(
                ActorProfile, ActorProfile.id == ActorIdentityLink.actor_profile_id,
            ).where(ActorIdentityLink.subject == "project-manager-subject"))).one()
            context = HumanAuthorizationContext(
                actor_profile_id=UUID(link.actor_profile_id), identity_link_id=UUID(link.id),
                actor_kind=ActorKind.HUMAN, actor_status=ActorStatus.ACTIVE,
                identity_link_status=IdentityLinkStatus.ACTIVE, request_id=uuid4(), correlation_id=uuid4(),
            )
            commands = ArtifactTaskImportSourceCommands(
                session, actor_profile_id=context.actor_profile_id, identity_link_id=context.identity_link_id,
                authorization=PreparedTaskImportSourceAuthorization(session, context), runtime=_unexpected_runtime,
            )
            binding = await commands.prepare_binding(UUID(project), UUID(source["source_id"]))
            assert await commands.authorize_binding(binding)
        async with session.begin():
            replica = await session.get(ArtifactReplica, str(binding.replica_id))
            replica.availability_state = "unavailable"
        async with session.begin():
            assert await commands.prepare_binding(UUID(project), binding.source_id, binding) == binding
            assert await commands.authorize_binding(binding)
        for replacement in (
            {"verification_receipt_id": uuid4()}, {"sha256": "sha256:" + "a" * 64},
            {"put_attempt_id": uuid4()}, {"project_id": uuid4()},
            {"operation_receipt_id": None, "observation_receipt_id": uuid4()},
        ):
            changed = binding.model_copy(update=replacement)
            async with session.begin():
                with pytest.raises(TaskImportSourceError):
                    await commands.prepare_binding(UUID(project), binding.source_id, changed)
