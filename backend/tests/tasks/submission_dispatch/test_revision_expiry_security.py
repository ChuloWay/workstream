"""Real service, stored-event and SQL custody failures leave no expiry effect."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.audit import task_revision_expiry_audit
from app.adapters.auth import revision_expiry_authorization
from app.adapters.outbox import outbox_append, outbox_invocation_fence
from app.adapters.tasks import task_revision_recovery
from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.audit.repository import AuditRepository
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.prepared import PreparedAuthorizationService
from app.modules.authorization.prepared import fixed_service_action_context
from app.modules.authorization.runtime import (
    AuthorizationDenialCode, AuthorizationDenied, PreparedAuthorizationUnsupported,
)
from app.modules.outbox.api import HandlerOutcome, OutboxAppendInput
from app.modules.outbox.delivery import CommittedInvocationReader
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.service import OutboxService
from app.modules.tasks.api.revision_expiry import REVISION_EXPIRED_EVENT, TaskRevisionExpiryUnavailable
from app.modules.tasks.revision.expiry import TaskRevisionExpiryOperation
from app.modules.tasks.revision.models import TaskRevisionExpiration
from app.modules.tasks.repository import TaskRepository
from tests.tasks.post_submit_routing.remediation_support import remediation_source, no_economic_effects
from tests.tasks.submission_dispatch.test_revision_capacity import _retain_pre_revision_source
from tests.tasks.submission_dispatch.test_revision_expiry import (
    _provision_expirer, expire_retained_revision,
)
from tests.test_submission_predecessor_custody import _fixture_revision_context


async def _snapshot(h):
    """Read committed evidence through a connection independent of the effect."""
    async with h.factory() as session:
        custody = (await session.execute(text("""
            SELECT to_jsonb(t),to_jsonb(a),to_jsonb(s)
            FROM public.workstream_tasks t
            JOIN public.task_assignments a ON a.id=:assignment
            JOIN public.submissions s ON s.id=:submission WHERE t.id=:task
        """), {"task": h.request.task_id, "assignment": h.request.assignment_id,
               "submission": h.created.submission_id})).one()
        evidence = []
        for table, where in (
            ("task_revision_preparations", "TRUE"),
            ("task_revision_expirations", "TRUE"),
            ("audit_events", "action_id IN ('task.revision.expire','task.revision.recover') "
             "OR event_type IN ('TaskRevisionExpired','TaskRevisionContextRepaired')"),
            ("outbox_events", "event_type='TaskRevisionExpired'"),
        ):
            evidence.append(await session.scalar(text(
                f"SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY to_jsonb(r)::text),'[]'::jsonb) "
                f"FROM public.{table} r WHERE {where}"
            )))
        await no_economic_effects(session)
        return tuple(custody), evidence


async def _invalidate_service(session, actor_id, state):
    """Arrange valid ACTORS lifecycle rows without claiming administrative authority."""
    if state == "suspended":
        await session.execute(text("""
            UPDATE public.actor_profiles SET status='suspended',
                suspended_by='expiry-security-fixture', suspended_at=clock_timestamp(),
                suspension_reason='Expiry service suspended'
            WHERE id=:actor
        """), {"actor": actor_id})
    elif state == "revoked":
        await session.execute(text("""
            UPDATE public.actor_identity_links SET status='revoked',
                revoked_by='expiry-security-fixture', revoked_at=clock_timestamp(),
                revoked_reason='Expiry identity revoked'
            WHERE actor_profile_id=:actor
        """), {"actor": actor_id})


async def _provision_wrong_service(h):
    identity = ServiceIdentity.REVIEW_PREFERENCE_EXPIRY
    actor_id = new_record_id()
    async with h.factory() as session, session.begin():
        session.add(ActorProfile(
            id=str(actor_id), actor_kind="service", status="active",
            provisioning_method="manual_service_provisioning",
            service_identity=identity.value, created_by="expiry-security-fixture",
        ))
        await session.flush()
        session.add(ActorIdentityLink(
            id=str(new_record_id()), actor_profile_id=str(actor_id),
            issuer="workstream.internal", subject=identity.value,
            subject_kind="service", status="active", linked_by="expiry-security-fixture",
        ))


def _expiry_operation(h, session):
    return TaskRevisionExpiryOperation(
        session, observer=CommittedInvocationReader(h.factory),
        fence=outbox_invocation_fence(session),
        authorization=revision_expiry_authorization(session),
        audit=task_revision_expiry_audit(session), outbox=outbox_append(session),
    )


async def _invocation(h, event_id):
    claim = await h.expiry_delivery.claim(event_id, h.request.project_id, "expiry-security-proof")
    assert claim is not None
    envelope = await h.expiry_delivery._begin_invocation(claim)
    assert envelope is not None
    assert await CommittedInvocationReader(h.factory).observe_invocation(envelope) is not None
    return envelope


def _revoke_at_consume(monkeypatch, actor_id, action):
    original = PreparedAuthorizationService.consume
    observed = []

    async def revoke(service, handle, action_id, *args, **kwargs):
        if action_id == action:
            await _invalidate_service(service._session, actor_id, "revoked")
            observed.append(action_id)
        return await original(service, handle, action_id, *args, **kwargs)

    monkeypatch.setattr(PreparedAuthorizationService, "consume", revoke)
    return observed


async def test_recovery_requires_exact_active_service_and_fresh_consume(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        source_id = await _fixture_revision_context(h)
        await _retain_pre_revision_source(h, source_id)
        await _provision_wrong_service(h)
        before = await _snapshot(h)
        # Another active service cannot substitute for the absent fixed expirer.
        with pytest.raises(PreparedAuthorizationUnsupported) as denied:
            async with h.factory() as session, session.begin():
                await task_revision_recovery(session).recover(source_id)
        assert denied.value.denial_code is AuthorizationDenialCode.ACTOR_NOT_FOUND
        assert await _snapshot(h) == before
        actor_id = await _provision_expirer(h.factory)
        before = await _snapshot(h)
        for state in ("suspended", "revoked"):
            with pytest.raises((AuthorizationDenied, PreparedAuthorizationUnsupported)):
                async with h.factory() as session, session.begin():
                    await _invalidate_service(session, actor_id, state)
                    await task_revision_recovery(session).recover(source_id)
            assert await _snapshot(h) == before
        with monkeypatch.context() as patch:
            consumed = _revoke_at_consume(patch, actor_id, ActionId.TASK_REVISION_RECOVER)
            with pytest.raises((AuthorizationDenied, PreparedAuthorizationUnsupported)):
                async with h.factory() as session, session.begin():
                    await task_revision_recovery(session).recover(source_id)
            assert consumed == [ActionId.TASK_REVISION_RECOVER]
        assert await _snapshot(h) == before
        # The unchanged real service can recover the same source after every denial.
        async with h.factory() as session, session.begin():
            assert await task_revision_recovery(session).recover(source_id) is True


async def test_expiry_denies_invalid_service_and_committed_resource_substitution(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        _, _, event_id = await expire_retained_revision(
            h, monkeypatch=monkeypatch, isolated_database_env=isolated_database_env,
            deliver=False,
        )
        envelope = await _invocation(h, event_id)
        async with h.factory() as session:
            actor_id = await session.scalar(text(
                "SELECT id FROM public.actor_profiles WHERE service_identity=:identity"
            ), {"identity": ServiceIdentity.TASK_REVISION_EXPIRER.value})
            event = await session.get(OutboxEvent, event_id)
        await _provision_wrong_service(h)
        before = await _snapshot(h)
        for state in ("suspended", "revoked"):
            with pytest.raises(TaskRevisionExpiryUnavailable, match="authority unavailable"):
                async with h.factory() as session, session.begin():
                    await _invalidate_service(session, actor_id, state)
                    await _expiry_operation(h, session).expire(envelope)
            assert await _snapshot(h) == before
        # Canonical AUTH also denies this expiry action to a real wrong service.
        # This is the fixed-service action matrix, separate from the TASK adapter.
        with pytest.raises(PreparedAuthorizationUnsupported) as denied:
            async with h.factory() as session, session.begin():
                await fixed_service_action_context(
                    session, service_identity=ServiceIdentity.REVIEW_PREFERENCE_EXPIRY,
                    action_id=ActionId.TASK_REVISION_EXPIRE,
                    request_id=event_id, correlation_id=h.revision_preparation_id,
                )
        assert denied.value.denial_code is AuthorizationDenialCode.PERMISSION_NOT_GRANTED
        assert await _snapshot(h) == before
        with monkeypatch.context() as patch:
            consumed = _revoke_at_consume(patch, actor_id, ActionId.TASK_REVISION_EXPIRE)
            with pytest.raises(TaskRevisionExpiryUnavailable, match="authority unavailable"):
                async with h.factory() as session, session.begin():
                    await _expiry_operation(h, session).expire(envelope)
            assert consumed == [ActionId.TASK_REVISION_EXPIRE]
        assert await _snapshot(h) == before
        async with remediation_source(
            tmp_path / "foreign", isolated_database_env,
            provision_services=False, provision_checker=False,
        ) as foreign:
            await _fixture_revision_context(foreign)
            assert foreign.request.project_id != h.request.project_id
            before = await _snapshot(h)
            for field, value in (
                ("project_id", foreign.request.project_id),
                ("root_preparation_id", foreign.revision_preparation_id),
                ("source_submission_id", foreign.created.submission_id),
            ):
                payload = dict(event.payload, **{field: str(value)})
                # Append, claim and invoke the adversarial event using real OUTBOX.
                # The replacement resource belongs to a second committed journey.
                async with h.factory() as session, session.begin():
                    forged = await outbox_append(session).append(OutboxAppendInput(
                        event_type=event.event_type, event_version=event.event_version,
                        aggregate_type=event.aggregate_type, aggregate_id=event.aggregate_id,
                        project_id=h.request.project_id, correlation_id=event.correlation_id,
                        causation_event_id=event.causation_event_id,
                        idempotency_key=f"expiry.security:{new_record_id()}", payload=payload,
                        not_before_at=event.not_before_at,
                    ))
                forged_envelope = await _invocation(h, forged.event_id)
                read_manifest = TaskRepository.read_routing_manifest
                reached_source_guard = []

                async def observed_manifest(repository, **selectors):
                    manifest = await read_manifest(repository, **selectors)
                    reached_source_guard.append(manifest is not None)
                    return manifest

                with monkeypatch.context() as patch:
                    patch.setattr(TaskRepository, "read_routing_manifest", observed_manifest)
                    async with h.factory() as session, session.begin():
                        assert await _expiry_operation(h, session).expire(forged_envelope) is HandlerOutcome.REJECT
                # TASK rejects root/source lineage before comparing the event key;
                # foreign project fails the claim/payload project binding first.
                assert reached_source_guard == {
                    "project_id": [], "root_preparation_id": [True],
                    "source_submission_id": [False],
                }[field]
                assert await _snapshot(h) == before
        async with h.factory() as session, session.begin():
            assert await _expiry_operation(h, session).expire(envelope) is HandlerOutcome.ACKNOWLEDGE


class ParticipantFailure(RuntimeError):
    pass


async def test_expiry_real_outbox_and_audit_staging_roll_back_every_owner(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        _, _, event_id = await expire_retained_revision(
            h, monkeypatch=monkeypatch, isolated_database_env=isolated_database_env,
            deliver=False,
        )
        envelope = await _invocation(h, event_id)
        before = await _snapshot(h)
        for participant in ("outbox", "audit"):
            staged = []
            with monkeypatch.context() as patch:
                owner = OutboxService if participant == "outbox" else AuditRepository
                method = "append" if participant == "outbox" else "_add_validated_lifecycle_event"
                original = getattr(owner, method)

                async def fail_after_staging(owner_instance, value):
                    result = await original(owner_instance, value)
                    if value.event_type == REVISION_EXPIRED_EVENT:
                        session = (owner_instance._repository._session
                                   if participant == "outbox" else owner_instance._session)
                        assert await session.scalar(text(
                            "SELECT count(*) FROM public.outbox_events WHERE event_type='TaskRevisionExpired'"
                        )) == 1
                        assert await session.scalar(text(
                            "SELECT count(*) FROM public.audit_events WHERE action_id='task.revision.expire'"
                        )) == 1
                        if participant == "audit":
                            await session.flush()
                            assert await session.scalar(text(
                                "SELECT count(*) FROM public.task_revision_expirations"
                            )) == 1
                            assert await session.scalar(text(
                                "SELECT status FROM public.workstream_tasks WHERE id=:task"
                            ), {"task": h.request.task_id}) == "ready"
                            assert await session.scalar(text(
                                "SELECT status FROM public.task_assignments WHERE id=:assignment"
                            ), {"assignment": h.request.assignment_id}) == "revision_expired"
                        staged.append(result)
                        assert await _snapshot(h) == before
                        raise ParticipantFailure("after real expiry participant staging")
                    return result

                patch.setattr(owner, method, fail_after_staging)
                with pytest.raises(ParticipantFailure, match="after real expiry participant staging"):
                    async with h.factory() as session, session.begin():
                        await _expiry_operation(h, session).expire(envelope)
            assert len(staged) == 1
            assert await _snapshot(h) == before


async def test_receipt_sql_binding_deferred_closure_and_immutability(
    tmp_path, isolated_database_env, monkeypatch,
):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        _, _, event_id = await expire_retained_revision(
            h, monkeypatch=monkeypatch, isolated_database_env=isolated_database_env,
            deliver=False,
        )
        envelope = await _invocation(h, event_id)
        before = await _snapshot(h)
        async with h.factory() as session:
            foreign_decision = await session.scalar(text(
                "SELECT authorization_decision_id FROM public.task_revision_preparations WHERE id=:root"
            ), {"root": h.revision_preparation_id})
        for field, value in (
            ("root_preparation_id", new_record_id()),
            ("head_preparation_sha256", "sha256:" + "0" * 64),
            ("authorization_decision_id", foreign_decision),
        ):
            original_add = AsyncSession.add
            attempted = []

            def substitute(session, instance, **kwargs):
                if isinstance(instance, TaskRevisionExpiration):
                    setattr(instance, field, value)
                    attempted.append(field)
                return original_add(session, instance, **kwargs)

            with monkeypatch.context() as patch:
                patch.setattr(AsyncSession, "add", substitute)
                with pytest.raises(DBAPIError, match="revision expiry source or authority differs"):
                    async with h.factory() as session, session.begin():
                        await _expiry_operation(h, session).expire(envelope)
            assert attempted == [field]
            assert await _snapshot(h) == before
        for failure in ("missing", "mismatched"):
            original_audit = AuditRepository._add_validated_lifecycle_event
            attempted = []

            async def corrupt_closure(repository, audit):
                if audit.event_type == REVISION_EXPIRED_EVENT:
                    attempted.append(failure)
                    if failure == "missing":
                        # A participant returning its intended ID without writing
                        # evidence must still fail the deferred database closure.
                        return audit
                    audit.to_status = "needs_revision"
                return await original_audit(repository, audit)

            with monkeypatch.context() as patch:
                patch.setattr(AuditRepository, "_add_validated_lifecycle_event", corrupt_closure)
                with pytest.raises(DBAPIError, match="revision expiry closure unavailable"):
                    async with h.factory() as session, session.begin():
                        assert await _expiry_operation(h, session).expire(envelope) is HandlerOutcome.ACKNOWLEDGE
                        assert await _snapshot(h) == before
                        await session.execute(text("SET CONSTRAINTS revision_expiration_closure IMMEDIATE"))
            assert attempted == [failure]
            assert await _snapshot(h) == before
        async with h.factory() as session, session.begin():
            assert await _expiry_operation(h, session).expire(envelope) is HandlerOutcome.ACKNOWLEDGE
        committed = await _snapshot(h)
        for statement in (
            "UPDATE public.task_revision_expirations SET expired_at=expired_at",
            "DELETE FROM public.task_revision_expirations",
            "TRUNCATE public.task_revision_expirations",
        ):
            with pytest.raises(DBAPIError, match="revision expirations are immutable"):
                async with h.factory() as session, session.begin():
                    await session.execute(text(statement))
            assert await _snapshot(h) == committed
