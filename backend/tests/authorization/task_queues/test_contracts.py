"""Closed queue requests and canonical cursor adaptation without product SQL."""

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from app.modules.authorization.api.task_queues import (
    TaskQueueReadRequest, TaskQueuePosition, TaskQueueCursorInvalid, TaskQueueReadUnavailable,
)
from app.modules.authorization.domain.task_queues import QueueReadResourceContext
from app.modules.authorization.task_queue_read import TaskQueueReadAuthorization

SECRET = SecretStr("AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=")


@pytest.mark.parametrize("change", [
    {"action": "task.claim"}, {"project_id": "bad"}, {"limit": True}, {"limit": 0},
    {"limit": 101}, {"presented_cursor": 1}, {"presented_cursor": "a" * 513},
])
def test_queue_request_is_closed(change):
    request = TaskQueueReadRequest("task.queue.read", uuid4(), 1, None)
    with pytest.raises(ValueError, match="invalid task queue request"):
        replace(request, **change)


@pytest.mark.parametrize("change", [{"task_id": "bad"}, {"created_at": "bad"}, {"created_at": datetime(2026, 1, 1)}])
def test_queue_position_requires_exact_types(change):
    with pytest.raises(ValueError, match="invalid task queue position"):
        replace(TaskQueuePosition(datetime.now(UTC), uuid4()), **change)


def test_queue_resource_requires_exact_project():
    project = uuid4()
    args = dict(resource_id=project, scope_project_id=project, request_digest="sha256:" + "a" * 64)
    assert QueueReadResourceContext(**args).resource_id == project
    with pytest.raises(ValidationError, match="queue project scope differs"):
        QueueReadResourceContext(**(args | {"scope_project_id": uuid4()}))


async def test_queue_adapter_reuses_cursor_and_binds_presented_page():
    kernel = AsyncMock()
    adapter = TaskQueueReadAuthorization(kernel, SECRET)
    request = TaskQueueReadRequest("task.queue.read", uuid4(), 1, None)
    assert await adapter.authorize_and_decode(request) is None
    first_digest = kernel.require.call_args.args[1].request_digest
    position = TaskQueuePosition(datetime.now(UTC), uuid4())
    cursor = adapter.encode(request, position)
    assert await adapter.authorize_and_decode(replace(request, presented_cursor=cursor)) == position
    assert kernel.require.call_args.args[1].request_digest != first_digest
    for changed in (replace(request, limit=2), replace(request, project_id=uuid4()),
                    replace(request, action="project.task.queue.read")):
        with pytest.raises(TaskQueueCursorInvalid):
            await adapter.authorize_and_decode(replace(changed, presented_cursor=cursor))
    with pytest.raises(TaskQueueCursorInvalid):
        await adapter.authorize_and_decode(replace(request, presented_cursor="broken"))
    with pytest.raises(TaskQueueReadUnavailable):
        await TaskQueueReadAuthorization(kernel, None).authorize_and_decode(request)


async def test_queue_domain_rejects_wrong_resource_and_unavailable_action():
    from types import SimpleNamespace
    from app.modules.authorization.catalogue import ActionAvailability
    from app.modules.authorization.domain.audit import AuthorizationDenialCode
    from app.modules.authorization.domain.task_queues import queue_read_denial

    repository = AsyncMock()
    action = SimpleNamespace(availability=ActionAvailability.PLANNED)
    project = uuid4()
    valid = QueueReadResourceContext(resource_id=project, scope_project_id=project, request_digest="sha256:" + "a" * 64)
    for resource, expected in (({}, AuthorizationDenialCode.RESOURCE_GUARD_DENIED),
                               (valid, AuthorizationDenialCode.ACTION_UNAVAILABLE)):
        result = await queue_read_denial(action, resource, None, repository, None, None)
        assert result[0] is expected
        repository.lock_request_actor.assert_not_called()
