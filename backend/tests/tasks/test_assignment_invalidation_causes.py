"""Real AUTH cause controls and substitutions through the actual AUDIT reader."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.adapters.audit import committed_authority_invalidation
from app.modules.audit.repository import AuditRepository
from app.modules.outbox.api import HandlerOutcome
from app.modules.tasks.models import AuditEvent
from tests.test_tasks import (
    task_client as task_client,
    task_database_env as task_database_env,
    auth_headers,
    set_dev_actor,
)
from tests.tasks.invalidation_support import setup_assignment, revoke, invoked, snapshot


@pytest.mark.parametrize("kind", ["grant", "suspend", "deactivate", "link"])
async def test_reader_rejects_mixed_and_malformed_real_cause_chain(task_client, monkeypatch, kind):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s, kind)
    reader = committed_authority_invalidation(s.sessions)
    control = await reader.read_invalidation(s.invalidation_id)
    assert control is not None and control.contributor_id == UUID(s.grant["actor_profile_id"])
    assert await reader.read_invalidation(uuid4()) is None
    assert await reader.read_invalidation("invalid") is None
    async with s.sessions() as session:
        rows = await AuditRepository(session).invalidation_chain(s.invalidation_id)
        originals = [
            {column.key: getattr(row, column.key) for column in AuditEvent.__table__.columns}
            for row in rows
        ]
    replacements = [
        (0, {"event_domain": "legacy_lifecycle"}),
        (1, {"auth_source": "other"}),
        (0, {"event_version": 2}),
        (1, {"is_dev_auth": True}),
        (0, {"invalidation_cause_event_id": str(uuid4())}),
        (1, {"request_id": str(uuid4())}),
        (1, {"correlation_id": str(uuid4())}),
        (0, {"idempotency_reference": None}),
        (1, {"target_actor_ref": str(uuid4())}),
        (1, {"target_ref_id": str(uuid4())}),
        (0, {"resource_id": str(uuid4())}),
        (0, {"invalidation_target_ref": str(uuid4())}),
        (0, {"after_facts": {**originals[0]["after_facts"], "effective": True}}),
        (1, {"target_actor_ref_kind": None}),
        (1, {"entity_id": str(uuid4())}),
    ]
    if kind == "grant":
        replacements += [
            (0, {"target_actor_ref": str(uuid4())}),
            (0, {"target_ref_id": str(uuid4())}),
            (
                0,
                {
                    "after_facts": {
                        **originals[0]["after_facts"],
                        "future_obligation": "rev_reviewer_obligation",
                    }
                },
            ),
        ]
    for index, changes in replacements:
        altered = deepcopy(originals)
        altered[index].update(changes)

        async def substituted_chain(owner, event_id):
            assert event_id == s.invalidation_id
            return tuple(SimpleNamespace(**row) for row in altered)

        with monkeypatch.context() as patch:
            patch.setattr(AuditRepository, "invalidation_chain", substituted_chain)
            assert await reader.read_invalidation(s.invalidation_id) is None, (
                kind,
                index,
                tuple(changes),
            )
    assert await reader.read_invalidation(s.invalidation_id) == control


async def test_reviewer_revocation_never_releases_submitter_assignment(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    set_dev_actor(monkeypatch, roles="project_manager", subject="project-manager-subject")
    unavailable = {
        "availability": "unavailable",
        "reference_ids": [],
        "unavailable_reason": "no_record",
    }
    response = await s.client.post(
        f"/api/v1/projects/{s.project['id']}/role-grants",
        headers=auth_headers(),
        json={
            "target_actor_profile_id": s.grant["actor_profile_id"],
            "role": "reviewer",
            "qualification": {
                "skills_snapshot": unavailable,
                "reputation_snapshot": unavailable,
                "prior_project_work_refs": [],
                "external_expertise_refs": [],
            },
            "reason": "Independent reviewer role",
        },
    )
    assert response.status_code == 201, response.text
    grant_id = response.json()["id"]
    revoked = await s.client.post(
        f"/api/v1/projects/{s.project['id']}/role-grants/{grant_id}/revoke",
        headers=auth_headers(),
        json={"reason": "Reviewer authority only"},
    )
    assert revoked.status_code == 200, revoked.text
    async with s.sessions() as session:
        event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "AuthorityInvalidationRequested",
                AuditEvent.invalidation_target_ref == grant_id,
            )
        )
        assert event.after_facts["future_obligation"] == "rev_reviewer_obligation"
        s.invalidation_id = UUID(event.id)
    _, envelope = await invoked(s)
    before = await snapshot(s)
    assert await s.handler(envelope) is HandlerOutcome.REJECT
    assert await snapshot(s) == before
    assert s.trace == []


async def test_reactivation_event_is_not_a_release_cause(task_client, monkeypatch):
    s = await setup_assignment(task_client, monkeypatch)
    await revoke(s, "suspend")
    old_cause = s.invalidation_id
    response = await s.client.post(
        f"/api/v1/actors/{s.grant['actor_profile_id']}/reactivate",
        headers=auth_headers(),
        json={"reason": "Restore authority"},
    )
    assert response.status_code == 200, response.text
    async with s.sessions() as session:
        event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "AuthorityInvalidationRequested",
                AuditEvent.invalidation_target_ref == s.grant["actor_profile_id"],
                AuditEvent.id != str(old_cause),
            )
        )
        assert event.after_facts == {"effective": True}
        s.invalidation_id = UUID(event.id)
    _, envelope = await invoked(s)
    before = await snapshot(s)
    assert await s.handler(envelope) is HandlerOutcome.REJECT
    assert await snapshot(s) == before and s.trace == []
