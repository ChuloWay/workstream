"""Concrete AUTH finalization, fresh lifecycle denial and transaction atomicity."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.modules.audit.service import AuditService
from app.modules.authorization.api import (
    PreparedAuthorizationInvalid,
    setup_finalization_authority_digest,
)
from app.modules.projects.api import ProjectGuideSetupFinalizationError
from app.modules.projects.guide_compilation.finalization import GuideCompilationFinalizationService
from .pg_authorization import ObservedAuthorization, concrete_finalize, revoke, seed_lifecycle_admin
from .pg_support import database_case, stored_state


@pytest.mark.parametrize(
    "classification", ["guide_blocked", "draft_ready", "draft_ready_with_warnings"]
)
async def test_concrete_finalization_is_atomic(clean_postgres_database, classification):
    async with database_case(clean_postgres_database, classification=classification) as (
        values,
        factory,
        command,
    ):
        async with factory() as session, session.begin():
            authority = ObservedAuthorization(session)
            result = await GuideCompilationFinalizationService(session, authority).finalize(command)
            event = (
                (
                    await session.execute(
                        text("select * from audit_events where id=:id"),
                        {"id": str(authority.receipt.decision_event_id)},
                    )
                )
                .mappings()
                .one()
            )
            assert event["event_domain"] == "authority"
            assert event["event_type"] == "SensitiveAuthorizationAllowed"
            assert event["actor_ref_kind"] == "actor_profile"
            assert event["actor_id"] == str(values["actor"])
            assert event["request_id"] == authority.facts.operation_id
            assert event["correlation_id"] == authority.facts.correlation_id
            assert event["resource_type"] == "project_guide_setup_finalization"
            assert event["resource_id"] == str(result.finalization_id)
            assert event["project_id"] == str(command.project_id)
            assert event["denial_code"] is None
            assert event["after_facts"] == {
                "allowed": True,
                "resource_context_digest": setup_finalization_authority_digest(
                    authority.facts, values["actor"], values["link"]
                ),
            }
        setup, receipt, count = await stored_state(factory, command)
        assert count == 1
        assert receipt["authorization_decision_event_id"] == str(
            authority.receipt.decision_event_id
        )
        assert receipt["actor_profile_id"] == str(values["actor"])
        assert receipt["identity_link_id"] == str(values["link"])
        assert setup["status"] == result.setup_outcome
        assert setup["output_sufficiency_report_id"] == str(authority.facts.sufficiency_report_id)
        with pytest.raises(PreparedAuthorizationInvalid):
            await authority.handle.consume_new(authority.facts)


async def test_concrete_replay_is_exact(clean_postgres_database):
    async with database_case(clean_postgres_database) as (_, factory, command):
        original = await concrete_finalize(factory, command)
        before = await stored_state(factory, command)
        assert await concrete_finalize(factory, command) == original
        assert await stored_state(factory, command) == before


@pytest.mark.parametrize("kind", ["actor", "deactivate", "link"])
@pytest.mark.parametrize("replay", [False, True])
async def test_revoked_service_denies_new_and_replay(clean_postgres_database, kind, replay):
    async with database_case(clean_postgres_database) as (values, factory, command):
        # A real successful control precedes each lifecycle case. Rollback retains
        # a queued setup for new-finalization denial; replay retains the receipt.
        async with factory() as session:
            async with session.begin():
                authority = ObservedAuthorization(session)
                await GuideCompilationFinalizationService(session, authority).finalize(command)
                if not replay:
                    await session.rollback()
        admin = await seed_lifecycle_admin(factory)
        async with factory() as session, session.begin():
            await revoke(session, admin, values, kind)
        before = await stored_state(factory, command)
        with pytest.raises(ProjectGuideSetupFinalizationError, match="service_authority_denied"):
            await concrete_finalize(factory, command)
        assert await stored_state(factory, command) == before
        assert before[2] == int(replay)


@pytest.mark.parametrize("fault", ["evidence", "receipt", "close", "caller_rollback"])
async def test_finalization_failure_rolls_back_all_effects(
    clean_postgres_database, monkeypatch, fault
):
    async with database_case(clean_postgres_database) as (_, factory, command):
        before = await stored_state(factory, command)
        original = AuditService.add_authority_event
        evidence_written = []

        async def add(service, value):
            event = await original(service, value)
            if value.action_id.value == "project.setup_run.update":
                evidence_written.append(event.id)
                if fault == "evidence":
                    raise SQLAlchemyError("injected after actual evidence write")
            return event

        monkeypatch.setattr(AuditService, "add_authority_event", add)
        error = RuntimeError if fault == "caller_rollback" else ProjectGuideSetupFinalizationError
        with pytest.raises(error):
            async with factory() as session, session.begin():
                authority = ObservedAuthorization(session, fault=fault)
                await GuideCompilationFinalizationService(session, authority).finalize(command)
                if fault == "caller_rollback":
                    assert (
                        await session.scalar(
                            text("select count(*) from project_guide_setup_finalizations")
                        )
                        == 1
                    )
                    raise RuntimeError("caller rollback")
        assert len(evidence_written) == 1
        assert await stored_state(factory, command) == before
        if authority.handle is not None:
            with pytest.raises(PreparedAuthorizationInvalid):
                await authority.handle.consume_new(authority.facts)
        monkeypatch.setattr(AuditService, "add_authority_event", original)
        await concrete_finalize(factory, command)
        assert (await stored_state(factory, command))[2] == 1


@pytest.mark.parametrize("substitution", ["missing", "foreign", "digest"])
async def test_stored_replay_decision_substitution_denied(clean_postgres_database, substitution):
    async with database_case(clean_postgres_database) as (_, factory, command):
        await concrete_finalize(factory, command)
        before = await stored_state(factory, command)
        with pytest.raises(ProjectGuideSetupFinalizationError, match="service_authority_denied"):
            async with factory() as session, session.begin():
                # Bounded rollback-only fixture corruption reaches AUTH replay
                # despite append-only production constraints. Never commit it.
                decision = str(before[1]["authorization_decision_event_id"])
                if substitution in {"missing", "foreign"}:
                    replacement = (
                        str(uuid4())
                        if substitution == "missing"
                        else await session.scalar(
                            text(
                                "select id from audit_events where event_type='SensitiveAuthorizationAllowed' "
                                "and action_id='project.guide_sufficiency.run' limit 1"
                            )
                        )
                    )
                    assert replacement is not None and replacement != decision
                    # Disable exactly this receipt table's guards, including its
                    # immediate FK, solely to construct an impossible replay input.
                    await session.execute(
                        text("alter table project_guide_setup_finalizations disable trigger all")
                    )
                    await session.execute(
                        text(
                            "update project_guide_setup_finalizations "
                            "set authorization_decision_event_id=:replacement where id=:id"
                        ),
                        {"replacement": replacement, "id": before[1]["id"]},
                    )
                    await session.execute(
                        text("alter table project_guide_setup_finalizations enable trigger all")
                    )
                else:
                    await session.execute(text("alter table audit_events disable trigger user"))
                    await session.execute(
                        text(
                            "update audit_events set after_facts="
                            "jsonb_set(after_facts::jsonb,'{resource_context_digest}',to_jsonb(cast(:digest as text))) "
                            "where id=:id"
                        ),
                        {"id": decision, "digest": "sha256:" + "f" * 64},
                    )
                    await session.execute(text("alter table audit_events enable trigger user"))
                await GuideCompilationFinalizationService(
                    session, ObservedAuthorization(session)
                ).finalize(command)
        assert await stored_state(factory, command) == before
        await concrete_finalize(factory, command)
