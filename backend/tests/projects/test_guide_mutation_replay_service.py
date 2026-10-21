"""Focused guide mutation replay service boundary tests."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.runtime import (
    AuthorizationDenialCode,
    PreparedAuthorizationInput,
    PreparedAuthorizationUnsupported,
)
from app.modules.projects import guide_mutation_router as guide_mutation_router_module
from app.modules.projects.guide_mutation_service import GuideMutationService
from app.modules.projects.schemas import ProjectGuideCreate, ProjectGuideUpdate
from projects.guide_fixtures import complete_guide_payload


def _guide_mutation_edge_subject():
    actor_id, link_id, project_id = (uuid4() for _ in range(3))
    resolved = SimpleNamespace(
        profile=SimpleNamespace(id=str(actor_id)),
        identity_link=SimpleNamespace(id=str(link_id)),
    )

    class Replay:
        def __init__(self):
            self.record = None

        async def find(self, *_args):
            return self.record

    replay = Replay()
    service = GuideMutationService(object())
    service._replay = replay  # type: ignore[assignment]
    return resolved, project_id, replay, service


def _guide_update_replay_record(resolved, project_id, guide_id, key):
    now = datetime.now(UTC).isoformat()
    return SimpleNamespace(
        actor_profile_id=resolved.profile.id,
        identity_link_id=resolved.identity_link.id,
        action_id=ActionId.PROJECT_GUIDE_UPDATE.value,
        idempotency_key=key,
        project_id=str(project_id),
        resource_id=str(guide_id),
        request_digest="digest",
        operation_id=uuid4(),
        status="committed",
        response_json={
            "id": str(guide_id),
            "project_id": str(project_id),
            "version": "v1",
            "status": "draft",
            "change_summary": "Clarified",
            "task_examples": None,
            "task_examples_hash": None,
            "approved_by": None,
            "effective_at": None,
            "created_by": resolved.profile.id,
            "created_at": now,
            "updated_at": now,
            "superseded_at": None,
        },
    )


async def test_guide_mutation_service_classifies_existing_replay() -> None:
    resolved, project_id, replay, service = _guide_mutation_edge_subject()
    guide_id, key = uuid4(), uuid4()
    replay.record = _guide_update_replay_record(resolved, project_id, guide_id, key)
    caller = PreparedAuthorizationInput(
        idempotency_key=key,
        request_value={"operation_id": str(uuid4())},
    )

    class Prepared:
        prepared = []
        closed = []

        async def prepare(self, action, input_value, scope):
            self.prepared.append((action, input_value, scope))
            return object()

        def close_handle(self, handle):
            self.closed.append(handle)

    prepared = Prepared()
    replay.record.identity_link_id = str(uuid4())
    with pytest.raises(
        guide_mutation_router_module.GuideMutationIdempotencyConflict,
        match="idempotency_mismatch",
    ):
        await service._existing(resolved, prepared, key, "digest", caller, project_id, guide_id)
    replay.record.identity_link_id = resolved.identity_link.id
    replay.record.status = "pending"
    replay.record.response_json = None
    with pytest.raises(
        guide_mutation_router_module.GuideMutationIdempotencyConflict,
        match="idempotency_pending",
    ):
        await service._existing(resolved, prepared, key, "digest", caller, project_id, guide_id)

    replay.record.status = "committed"
    replay.record.response_json = _guide_update_replay_record(
        resolved, project_id, guide_id, key
    ).response_json
    existing = await service._existing(
        resolved,
        prepared,
        key,
        "digest",
        caller,
        project_id,
        guide_id,
    )
    assert existing.response.id == str(guide_id)
    assert existing.replayed is True
    assert len(prepared.prepared) == len(prepared.closed) == 1
    assert prepared.prepared[0][1].request_value["operation_id"] == str(replay.record.operation_id)
    replay.record.response_json["id"] = str(uuid4())
    with pytest.raises(RuntimeError, match="lost response custody"):
        await service._existing(resolved, prepared, key, "digest", caller, project_id, guide_id)
    assert len(prepared.prepared) == 1


async def test_guide_update_service_returns_exact_cached_response() -> None:
    resolved, project_id, _replay, _service = _guide_mutation_edge_subject()
    cached = SimpleNamespace(replayed=True)

    async def cached_existing(*_args):
        return cached

    cached_service = GuideMutationService(object())
    cached_service._existing = cached_existing  # type: ignore[method-assign]
    guide_id = uuid4()
    assert (
        await cached_service.update_guide(
            resolved,
            object(),
            uuid4(),
            project_id,
            guide_id,
            ProjectGuideUpdate(change_summary="cached"),
        )
        is cached
    )


def test_guide_mutation_service_classifies_reservation_outcomes() -> None:
    resolved, project_id, _replay, service = _guide_mutation_edge_subject()
    guide_id, key = uuid4(), uuid4()
    record = _guide_update_replay_record(resolved, project_id, guide_id, key)
    with pytest.raises(
        guide_mutation_router_module.GuideMutationIdempotencyConflict,
        match="idempotency_mismatch",
    ):
        service._reservation_outcome(
            "mismatch", record, resolved, key, "digest", project_id, guide_id
        )
    with pytest.raises(
        guide_mutation_router_module.GuideMutationIdempotencyConflict,
        match="idempotency_pending",
    ):
        service._reservation_outcome(
            "pending", record, resolved, key, "digest", project_id, guide_id
        )
    replayed = service._reservation_outcome(
        "replayed", record, resolved, key, "digest", project_id, guide_id
    )
    assert replayed.response.id == str(guide_id)
    assert replayed.replayed is True


def test_guide_mutation_service_rejects_invalid_authority_proof() -> None:
    _resolved, project_id, _replay, service = _guide_mutation_edge_subject()
    with pytest.raises(RuntimeError, match="lacked Project Manager authority"):
        service._prove(
            SimpleNamespace(
                matched_authority_kind=None,
                matched_grant_id=None,
                matched_scope_project_id=None,
            ),
            project_id,
        )


async def test_guide_mutation_service_composes_unsupported_prepare_denial() -> None:
    resolved, project_id, _replay, service = _guide_mutation_edge_subject()

    class Prepared:
        def __init__(self):
            self.denied = None

        async def prepare(self, *_args):
            raise PreparedAuthorizationUnsupported(AuthorizationDenialCode.PERMISSION_NOT_GRANTED)

        async def deny_unsupported(self, *args):
            self.denied = args

    prepared = Prepared()
    caller, _ = service._input(
        ActionId.PROJECT_GUIDE_CREATE,
        "POST /api/v1/projects/{project_id}/guides",
        resolved,
        uuid4(),
        ProjectGuideCreate.model_validate(complete_guide_payload()),
        project_id=project_id,
        target_resource_id=uuid4(),
        operation_id=uuid4(),
    )
    assert (
        await service._prepare(
            prepared,
            ActionId.PROJECT_GUIDE_CREATE,
            caller,
            project_id,
            guide_id=None,
            target_kind="guide_create",
        )
        is None
    )
    assert prepared.denied is not None
    denial_resource = prepared.denied[2]
    assert denial_resource.scope_project_id == project_id
    assert denial_resource.requested_guide_id is None
    assert denial_resource.requested_target_kind == "guide_create"
