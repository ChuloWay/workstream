"""Exact binding audit vocabulary and real authorized lifecycle persistence."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.adapters.auth import compensation_adapter_binding_authorization
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
from tests.migration_fixtures import current_schema_revision, run_guarded_revision_downgrade
from .postgresql_support import world
from .foreign_fixtures import foreign_project
from .test_migration import clone_decision, definition, migrate, schema_value, CONSTRAINTS

PRIOR = "0021_pre_submit_attempts"
OWN = "0022_adapter_binding_audit_resource"
RESOURCE = ", ('compensation_adapter_binding'::character varying)::text"
ACTIONS = tuple("compensation.adapter_binding." + name for name in ("read", "create", "suspend", "resume"))


@pytest.fixture
def prior_binding_audit_schema(auth_database_env, migration_lock, migration_schema_at):
    """Initialize the prior schema before entering the asynchronous proof."""
    with migration_lock():
        migration_schema_at(PRIOR)


@pytest.mark.asyncio
@pytest.mark.postgres_schema_contract
async def test_binding_audit_migration_preserves_every_unrelated_clause(
    prior_binding_audit_schema, migration_lock,
):
    before = await definition()
    await migrate("upgrade", OWN, migration_lock)
    after = await definition()
    assert after[CONSTRAINTS[0]].count(RESOURCE) == 1
    assert after[CONSTRAINTS[0]].replace(RESOURCE, "", 1) == before[CONSTRAINTS[0]]
    expression = after[CONSTRAINTS[1]]
    for action in ACTIONS:
        fragment = f" OR (((action_id)::text = '{action}'::text) AND ((permission_id)::text = 'compensation.adapter_binding.manage'::text))"
        assert fragment not in before[CONSTRAINTS[1]] and expression.count(fragment) == 2
        expression = expression.replace(fragment, "")
    assert expression == before[CONSTRAINTS[1]]
    assert after[CONSTRAINTS[2]] == before[CONSTRAINTS[2]]
    await migrate("downgrade", PRIOR, migration_lock)
    assert await definition() == before
    await migrate("upgrade", OWN, migration_lock)
    assert await definition() == after


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
    adapter_id = uuid4()
    async with factory() as session, session.begin():
        session.add(ActorProfile(
            id=str(adapter_id), actor_kind="service", status="active",
            provisioning_method="manual_service_provisioning",
            service_identity=ServiceIdentity.COMPENSATION_ADAPTER.value,
            created_by=str(target.context.actor_profile_id),
        ))
        await session.flush()
        session.add(ActorIdentityLink(
            id=str(uuid4()), actor_profile_id=str(adapter_id), issuer="https://compensation.test",
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


@pytest.mark.asyncio
@pytest.mark.postgres_schema_contract
@pytest.mark.parametrize("shape", ("both", "action_only", "resource_only"))
async def test_binding_audit_downgrade_refuses_retained_evidence(admin_access, migration_lock, shape):
    # Each one-sided retained shape must independently prevent downgrade.
    target = await world(admin_access)
    async with db_session.get_session_factory()() as session:
        event = await session.scalar(select(AuditEvent).where(
            AuditEvent.event_type == "SensitiveAuthorizationAllowed",
            AuditEvent.action_id == "admin_role_grant.issue",
        ).limit(1))
    changes = dict(
        project_id=str(target.project), resource_id=str(target.project),
        resource_type="project" if shape == "action_only" else "compensation_adapter_binding",
        action_id="project.read" if shape == "resource_only" else ACTIONS[0],
        permission_id="project.read" if shape == "resource_only" else "compensation.adapter_binding.manage",
        after_facts={"allowed": True, "resource_context_digest": "sha256:" + "a" * 64},
    )
    identity = await clone_decision(event, changes)
    constraints = await definition()
    count = await schema_value("select count(*) from audit_events")
    with pytest.raises(RuntimeError, match="AdapterBinding audit history prevents downgrade"):
        with migration_lock():
            await run_guarded_revision_downgrade(
                db_session.get_engine().url.render_as_string(hide_password=False), OWN,
            )
    assert await definition() == constraints
    assert await schema_value("select count(*) from audit_events") == count
    assert await schema_value(f"select count(*) from audit_events where id='{identity}'") == 1
    assert await schema_value("select version_num from alembic_version") == current_schema_revision()
