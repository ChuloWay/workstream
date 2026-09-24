"""Exact binding audit vocabulary and real authorized lifecycle persistence."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.adapters.auth import compensation_adapter_binding_authorization
from app.core.identifiers import new_record_id
from app.db import session as db_session
from app.modules.actors.compensation_adapter import CompensationAdapterActorEligibility
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorProfile, ActorIdentityLink
from app.modules.compensation.api import (
    AdapterBindingCreateRequest, AdapterBindingReadRequest, AdapterBindingResumeRequest,
    AdapterBindingSuspendRequest,
)
from app.modules.compensation.service import AdapterBindingService
from app.modules.projects.compensation_binding import ProjectCompensationBindingEligibility
from app.modules.tasks.models import AuditEvent
from .postgresql_support import world
from .foreign_fixtures import foreign_project
from .audit_schema_support import clone_decision, schema_value, CONSTRAINTS

ACTIONS = tuple("compensation.adapter_binding." + name for name in ("read", "create", "suspend", "resume"))


async def binding_lifecycle(admin_access):
    """Run all four existing actions through canonical AUTH and product owners."""
    target = await world(admin_access)
    # CON's historical binding seed uses a verifier actor and already fills both
    # instruments. Fresh binding creation needs its own eligible adapter and project.
    project, _ = await foreign_project(target)
    await admin_access.signed.grant(
        admin_access.admin, admin_access.target, role="finance_authority", project_id=project,
    )
    target = replace(target, project=project)
    factory = db_session.get_session_factory()
    adapter_id = new_record_id()
    async with factory() as session, session.begin():
        session.add(ActorProfile(
            id=str(adapter_id), actor_kind="service", status="active",
            provisioning_method="manual_service_provisioning",
            service_identity=ServiceIdentity.COMPENSATION_ADAPTER.value,
            created_by=str(target.context.actor_profile_id),
        ))
        await session.flush()
        session.add(ActorIdentityLink(
            id=str(new_record_id()), actor_profile_id=str(adapter_id), issuer="https://compensation.test",
            subject="binding-audit-" + adapter_id.hex, subject_kind="service", status="active",
            linked_by=str(target.context.actor_profile_id), last_verified_at=datetime.now(UTC),
        ))
    async with factory() as session:
        authority = compensation_adapter_binding_authorization(session, target.context)
        service = AdapterBindingService(
            session, read_authorization=authority, mutation_authorization=authority,
            projects=ProjectCompensationBindingEligibility(session),
            actors=CompensationAdapterActorEligibility(session),
        )
        async with session.begin():
            created = await service.create(AdapterBindingCreateRequest(
                operation_id=uuid4(), actor_profile_id=target.context.actor_profile_id,
                project_id=target.project, instrument_type="project_points",
                adapter_actor_id=adapter_id, route_key="points.primary",
            ))
        identity = dict(actor_profile_id=target.context.actor_profile_id,
                        project_id=target.project, adapter_binding_id=created.adapter_binding_id)
        async with session.begin():
            view = await service.read(AdapterBindingReadRequest(**identity))
            assert view.status == "active"
        async with session.begin():
            await service.suspend(AdapterBindingSuspendRequest(
                **identity, operation_id=uuid4(), expected_lifecycle_version=1,
            ))
        async with session.begin():
            resumed = await service.resume(AdapterBindingResumeRequest(
                **identity, operation_id=uuid4(), expected_lifecycle_version=2,
            ))
            assert resumed.to_status == "active" and resumed.to_lifecycle_version == 3
    async with factory() as session:
        events = (await session.scalars(select(AuditEvent).where(
            AuditEvent.project_id == str(target.project), AuditEvent.action_id.in_(ACTIONS),
        ))).all()
    assert {event.action_id for event in events} == set(ACTIONS)
    assert all(event.resource_type == "compensation_adapter_binding" and
               event.permission_id == "compensation.adapter_binding.manage" for event in events)
    return target, events


@pytest.mark.asyncio
async def test_all_binding_actions_persist_required_audit(admin_access):
    await binding_lifecycle(admin_access)


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper,constraint", (
    ({"resource_type": "unregistered_binding_resource"}, CONSTRAINTS[0]),
    ({"permission_id": "project.read"}, CONSTRAINTS[1]),
    ({"action_id": "compensation.adapter_binding.unknown"}, CONSTRAINTS[1]),
    ({"after_facts": {"private_material": "not-permitted"}}, "ck_audit_events_fact_bounds"),
))
async def test_binding_audit_sql_preserves_privacy_and_permission_guards(admin_access, tamper, constraint):
    _, events = await binding_lifecycle(admin_access)
    event = events[0]
    if "after_facts" in tamper:
        tamper = {**tamper, "after_facts": {**event.after_facts, **tamper["after_facts"]}}
    control = await clone_decision(event, {})
    assert await schema_value(f"select count(*) from audit_events where id='{control}'") == 1
    count = await schema_value("select count(*) from audit_events")
    with pytest.raises(DBAPIError, match=constraint):
        await clone_decision(event, tamper)
    assert await schema_value("select count(*) from audit_events") == count

