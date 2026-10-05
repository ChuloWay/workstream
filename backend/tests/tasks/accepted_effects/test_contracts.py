"""Strict public contract and hidden-construction proof."""

from inspect import iscoroutinefunction
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.identifiers import new_record_id
from app.modules.tasks import api as task_api
from app.modules.tasks.accepted_effects import TaskAcceptedEffectsParticipant
from app.modules.tasks.api import (
    TaskAcceptedEffectsFence,
    TaskAcceptedEffectsPort,
    TaskAcceptedEffectsRequest,
    TaskAcceptedEffectsResult,
    TaskAcceptedEffectsUnavailable,
    TaskAcceptedPreparation,
)

SHA = "sha256:" + "a" * 64


def values(**changes):
    result = {
        "project_id": new_record_id(),
        "task_id": new_record_id(),
        "assignment_id": new_record_id(),
        "submission_id": new_record_id(),
        "submission_version": 1,
        "contributor_id": new_record_id(),
        "contribution_policy_version_id": new_record_id(),
        "content_id": new_record_id(),
        "content_sha256": SHA,
        "final_acceptance_id": new_record_id(),
        "expected_task_status": "evaluation_pending",
    }
    result.update(changes)
    return result


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("project_id", str(new_record_id())),
        ("submission_version", "1"),
        ("submission_version", True),
        ("content_sha256", "sha256:" + "A" * 64),
        ("expected_task_status", "accepted"),
        ("routing_manifest_id", new_record_id()),
    ),
)
def test_request_is_strict(field, value):
    with pytest.raises(ValidationError):
        TaskAcceptedEffectsRequest(**values(**{field: value}))


def test_two_phase_contract_is_exact_and_concrete_participant_is_hidden():
    request = TaskAcceptedEffectsRequest(**values())
    preparation = TaskAcceptedPreparation(
        disposition="new", locked_review_policy_id=new_record_id()
    )
    result = TaskAcceptedEffectsResult(
        request=request, task_status="accepted", assignment_status="completed"
    )

    assert preparation.disposition == "new"
    assert result.request == request
    assert iscoroutinefunction(TaskAcceptedEffectsPort.lock_accepted_effects)
    assert iscoroutinefunction(TaskAcceptedEffectsPort.apply_accepted_effects)
    assert iscoroutinefunction(TaskAcceptedEffectsPort.require_routing_source)
    assert iscoroutinefunction(TaskAcceptedEffectsFence.acquire)
    assert issubclass(TaskAcceptedEffectsUnavailable, RuntimeError)
    assert not hasattr(task_api, "TaskAcceptedEffectsParticipant")
    for value in (
        {"disposition": "pending", "locked_review_policy_id": new_record_id()},
        {"disposition": "new", "locked_review_policy_id": str(new_record_id())},
    ):
        with pytest.raises(ValidationError):
            TaskAcceptedPreparation(**value)


def test_nested_request_instances_are_revalidated():
    request = TaskAcceptedEffectsRequest(**values())
    object.__setattr__(request, "expected_task_status", "accepted")

    with pytest.raises(ValidationError):
        TaskAcceptedEffectsResult(
            request=request,
            task_status="accepted",
            assignment_status="completed",
        )


class _RoutingManifestRead:
    """Return one stored-shape transport row while recording owner qualification."""

    def __init__(self, source):
        self.source = source
        self.scope = None

    async def read_routing_manifest(self, **scope):
        self.scope = scope
        return self.source


def _routing_source(request, **changes):
    source = {
        "project_id": str(request.project_id),
        "task_id": str(request.task_id),
        "submission_id": str(request.submission_id),
        "submission_version": request.submission_version,
        "assignment_id": str(request.assignment_id),
        "contributor_id": str(request.contributor_id),
        "contribution_policy_version_id": request.contribution_policy_version_id,
        "content_sha256": request.content_sha256,
        "human_review_required": False,
    }
    source.update(changes)
    return SimpleNamespace(**source)


def _routing_owner(source):
    repository = _RoutingManifestRead(source)
    owner = object.__new__(TaskAcceptedEffectsParticipant)
    owner._repository = repository
    return owner, repository


async def test_exact_false_transport_row_is_owner_qualified_without_activation_claim():
    request = TaskAcceptedEffectsRequest(**values())
    manifest_id = new_record_id()
    owner, repository = _routing_owner(_routing_source(request))

    assert await owner.require_routing_source(request, manifest_id) is None
    assert repository.scope == {
        "manifest_id": manifest_id,
        "project_id": request.project_id,
        "task_id": request.task_id,
        "submission_id": request.submission_id,
    }


@pytest.mark.parametrize(
    "changes",
    (
        {"project_id": str(new_record_id())},
        {"task_id": str(new_record_id())},
        {"submission_id": str(new_record_id())},
        {"submission_version": 2},
        {"assignment_id": str(new_record_id())},
        {"contributor_id": str(new_record_id())},
        {"contribution_policy_version_id": new_record_id()},
        {"content_sha256": "sha256:" + "b" * 64},
        {"human_review_required": True},
    ),
)
async def test_each_stored_routing_source_mismatch_is_rejected(changes):
    request = TaskAcceptedEffectsRequest(**values())
    owner, _ = _routing_owner(_routing_source(request, **changes))

    with pytest.raises(TaskAcceptedEffectsUnavailable):
        await owner.require_routing_source(request, new_record_id())
