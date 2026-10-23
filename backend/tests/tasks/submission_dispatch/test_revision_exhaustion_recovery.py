"""Recover a genuinely guarded 0047 cap-blocked source without rewriting history."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

from alembic import command
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.adapters.tasks import task_revision_recovery
from app.core.identifiers import new_record_id
from app.modules.actors.api import ServiceIdentity
from app.modules.authorization.runtime import AuthorizationDenied, PreparedAuthorizationUnsupported
from app.modules.outbox.service import OutboxService
from app.modules.projects.api import ProjectLockedPolicyContextRequest
from app.modules.tasks.post_submit_routing.source import TaskRoutingSourcePreparer
from app.modules.tasks.revision.models import TaskRevisionExhaustion
from app.modules.tasks.revision.service import select_candidate
from tests.checkers.execution.support import service_link_state
from tests.migration_fixtures import current_schema_revision
from tests.migration_revision_fixtures import (
    assert_historical_revision_guards, enter_predecessor_owner_shape,
    historical_revision_source, leave_predecessor_owner_shape, insert_0047_preparation,
    retained_revision_rows,
)
from tests.tasks.post_submit_routing.outcome_support import invoked_completion
from tests.tasks.post_submit_routing.support import revision_archive
from tests.tasks.submission_dispatch.test_replacement_creation import (
    _create, _creation_request, _ready_replacement,
)
from tests.tasks.submission_dispatch.test_revision_capacity import _fail_current_submission
from tests.tasks.submission_dispatch.test_revision_exhaustion import (
    StagedFailure, _apply, _assert_exhausted_assignment_immutable, _history_rejects_source,
    _snapshot, _submit_initial_after_reclaim,
)
from tests.tasks.submission_dispatch.test_revision_expiry import _provision_expirer
from tests.tasks.test_public_submission_intake import _client
from tests.test_alembic import _alembic_config, _execute


pytestmark = pytest.mark.postgres_schema_contract


async def _0047_head(session, manifest_id):
    """Read actual historical columns while current ORM has additive clock fields."""
    row = (await session.execute(text("""
        SELECT p.* FROM public.task_revision_preparations p
        WHERE p.routing_manifest_id=:id AND NOT EXISTS(
          SELECT 1 FROM public.task_revision_preparations child WHERE child.predecessor_id=p.id)
    """), {"id": manifest_id})).mappings().one_or_none()
    return None if row is None else SimpleNamespace(
        **row, remaining_microseconds=None, clock_observed_at=None,
    )


@asynccontextmanager
async def _retained_cap_source(tmp_path, database_url, monkeypatch):
    """Execute old source selection before real AUTH with every 0047 guard enabled."""
    await _execute(database_url, "drop schema public cascade; create schema public")
    await asyncio.to_thread(command.upgrade, _alembic_config(), "0047_revision_recovery")
    shape = pytest.MonkeyPatch()
    await enter_predecessor_owner_shape(_execute, database_url, shape)
    original = TaskRoutingSourcePreparer.prepare

    async def old_source(preparer, *args, **kwargs):
        source = await original(preparer, *args, **kwargs)
        if source.exhaustion is None:
            return source
        policy = source.source.locked_policy
        context = await preparer._projects.lock_locked_policy_context(ProjectLockedPolicyContextRequest(
            project_id=source.source.project_id, guide_version=policy.locked_guide_version,
            source_snapshot_id=policy.locked_guide_source_snapshot_id,
            source_snapshot_hash=policy.locked_guide_source_snapshot_hash,
            effective_policy_id=policy.locked_effective_project_submission_artifact_policy_id,
            effective_policy_hash=policy.locked_effective_project_submission_artifact_policy_hash,
            pre_submit_policy_id=policy.locked_pre_submit_checker_policy_id,
            pre_submit_policy_bundle_hash=policy.locked_pre_submit_checker_bundle_hash,
        ))
        candidate = await select_candidate(preparer._projects, context)
        assert candidate.max_revision_rounds == 1
        return source.model_copy(update={"exhaustion": None, "revision_candidate": candidate})

    async with historical_revision_source(
        tmp_path,
        database_url,
        monkeypatch,
        "0047_revision_source_cap_one",
    ) as h:
        await assert_historical_revision_guards(h.factory, "0047_revision_recovery")
        h.envelope = await invoked_completion(h)
        await assert_historical_revision_guards(h.factory, "0047_revision_recovery")
        with monkeypatch.context() as patch:
            patch.setattr(TaskRoutingSourcePreparer, "prepare", old_source)
            patch.setattr("app.modules.tasks.post_submit_routing.outcome.prepare_revision", insert_0047_preparation)
            patch.setattr("app.modules.tasks.revision.service.head_for_source", _0047_head)
            patch.setattr("app.modules.tasks.submission_context.head_for_source", _0047_head)
            initial = await _apply(h)
            async with h.factory() as session:
                first = await _0047_head(session, initial.routing_manifest_id)
                h.revision_preparation_id = first.id
                h.revision_preparation_sha256 = first.preparation_sha256
            h.data = revision_archive(h.data)
            prepared, admission = await _ready_replacement(h, h.data)
            h.created = await _create(h, _creation_request(h, prepared, admission))
            assert h.created.submission_version == 2
            retained = await _fail_current_submission(h, terminal=True)
            async with h.factory() as session:
                blocked = await _0047_head(session, retained.routing_manifest_id)
                assert (blocked.outcome, blocked.blocked_reason) == ("blocked", "revision_limit_reached")
                assert blocked.next_revision_round == 2 and blocked.max_revision_rounds == 1
                before = await retained_revision_rows(session, retained.routing_manifest_id)
                assert await session.scalar(text("""
                    SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
                    JOIN pg_namespace n ON n.oid=c.relnamespace
                    WHERE n.nspname='public' AND NOT t.tgisinternal AND t.tgenabled='D'
                """)) == 0
        shape.undo()
        await leave_predecessor_owner_shape(_execute, database_url)
        await asyncio.to_thread(command.upgrade, _alembic_config(), current_schema_revision())
        async with h.factory() as session:
            assert await retained_revision_rows(session, retained.routing_manifest_id) == before
        yield h, retained, before


async def _recover(h, manifest_id):
    async with h.factory() as session, session.begin():
        return await task_revision_recovery(session).recover(manifest_id)


async def test_retained_cap_recovery_releases_once_and_preserves_exact_routing_replay(
    tmp_path, isolated_database_env, migration_lock, monkeypatch,
):
    """Fresh service authority closes old cap holds atomically; reclaim keeps history."""
    with migration_lock():
        async with _retained_cap_source(tmp_path, isolated_database_env, monkeypatch) as (h, routed, old):
            source_id = routed.routing_manifest_id
            original_envelope = h.envelope
            await _provision_expirer(h.factory)
            await service_link_state(h.factory, ServiceIdentity.TASK_REVISION_EXPIRER, active=False)
            before = await _snapshot(h)
            with pytest.raises((AuthorizationDenied, PreparedAuthorizationUnsupported)):
                await _recover(h, source_id)
            assert await _snapshot(h) == before
            await service_link_state(h.factory, ServiceIdentity.TASK_REVISION_EXPIRER, active=True)
            before = await _snapshot(h)
            with pytest.raises(DBAPIError) as rejected:
                async with h.factory() as session, session.begin():
                    await session.execute(text("""
                        INSERT INTO public.task_revision_expirations (id,task_id,source_submission_id)
                        VALUES (:id,:task,:source)
                    """), {"id": new_record_id(), "task": h.request.task_id, "source": h.created.submission_id})
            assert rejected.value.orig.sqlstate == "23514"
            database_error = rejected.value.orig.__cause__
            assert database_error.constraint_name == "ck_revision_expiration_source_not_exhausted"
            assert await _snapshot(h) == before
            async with h.factory() as session:
                await session.begin()
                assert await task_revision_recovery(session).recover(source_id) is True
                assert await session.scalar(select(TaskRevisionExhaustion.id)) is not None
                await session.rollback()
            assert await _snapshot(h) == before

            append = OutboxService.append
            reached = []

            async def fail_after_append(owner, *args, **kwargs):
                result = await append(owner, *args, **kwargs)
                reached.append(result)
                raise StagedFailure("after real recovery outbox write")

            with monkeypatch.context() as patch:
                patch.setattr(OutboxService, "append", fail_after_append)
                with pytest.raises(StagedFailure, match="after real recovery outbox write"):
                    await _recover(h, source_id)
            assert len(reached) == 1
            assert await _snapshot(h) == before
            assert await _recover(h, source_id) is True
            async with h.factory() as session:
                receipt = await session.scalar(select(TaskRevisionExhaustion).where(
                    TaskRevisionExhaustion.routing_manifest_id == source_id,
                ))
                assert receipt is not None and receipt.recovery_authority_context is not None
                assert await session.scalar(text(
                    "SELECT public.task_revision_exhaustion_complete(:id)"
                ), {"id": receipt.id}) is True
                assert receipt.revision_round == receipt.max_revision_rounds == 1
                assert receipt.source_submission_id == str(h.created.submission_id)
                state = (await session.execute(text("""
                    SELECT t.status,t.assigned_to,a.status,a.released_at,
                      (SELECT action_id FROM public.audit_events WHERE id=:decision)
                    FROM public.workstream_tasks t JOIN public.task_assignments a ON a.id=:assignment
                    WHERE t.id=:task
                """), {"decision": receipt.authorization_decision_id,
                       "assignment": h.request.assignment_id, "task": h.request.task_id})).one()
                assert state == ("ready", None, "revision_exhausted", receipt.exhausted_at, "task.revision.recover")
                retained = await retained_revision_rows(session, source_id)
                for owner in ("revision_policies", "submissions", "task_revision_preparations",
                              "task_post_submit_routing_manifests", "outbox_events"):
                    assert retained[owner] == old[owner], owner
            await _assert_exhausted_assignment_immutable(h, receipt)
            committed = await _snapshot(h)
            assert await _recover(h, source_id) is False
            assert await _snapshot(h) == committed
            async with _client(h, monkeypatch, isolated_database_env) as client:
                await _history_rejects_source(h, client, h.created.submission_id)
                h.created = await _submit_initial_after_reclaim(h, client)
                assert h.created.submission_version == 3
            async with h.factory() as session:
                assert await session.scalar(text(
                    "SELECT public.task_revision_exhaustion_complete(:id)"
                ), {"id": receipt.id}) is True
            reclaimed = await _snapshot(h)
            assert await _apply(h, original_envelope) == routed.model_copy(update={"replayed": True})
            assert await _snapshot(h) == reclaimed
            await service_link_state(h.factory, ServiceIdentity.TASK_POST_SUBMIT_ROUTER, active=False)
            revoked = await _snapshot(h)
            with pytest.raises((AuthorizationDenied, PreparedAuthorizationUnsupported)):
                await _apply(h, original_envelope)
            assert await _snapshot(h) == revoked


async def test_upgrade_backfills_assignments_around_a_retained_exhausted_assignment(
    tmp_path, isolated_database_env, migration_lock, monkeypatch,
):
    """0049's assignment backfill must not trip the terminal-assignment immutability guard."""
    database_url = isolated_database_env
    await _execute(database_url, "drop schema public cascade; create schema public")
    await asyncio.to_thread(command.upgrade, _alembic_config(), "0048_revision_exhaustion")
    shape = pytest.MonkeyPatch()
    await enter_predecessor_owner_shape(_execute, database_url, shape)
    async with historical_revision_source(
        tmp_path,
        database_url,
        monkeypatch,
        "0048_revision_source_cap_zero",
    ) as h:
        await assert_historical_revision_guards(h.factory, "0048_revision_exhaustion")
        h.envelope = await invoked_completion(h)
        await assert_historical_revision_guards(h.factory, "0048_revision_exhaustion")
        exhausted = await _apply(h)
        async with h.factory() as session:
            receipt = await session.scalar(select(TaskRevisionExhaustion).where(
                TaskRevisionExhaustion.routing_manifest_id == exhausted.routing_manifest_id,
            ))
            assert receipt is not None
            before = await session.scalar(text(
                "SELECT to_jsonb(a)-ARRAY['started_at','updated_at'] "
                "FROM public.task_assignments a WHERE id=:id"
            ), {"id": receipt.assignment_id})
            assert before["status"] == "revision_exhausted"
        shape.undo()
        await leave_predecessor_owner_shape(_execute, database_url)
        await asyncio.to_thread(command.upgrade, _alembic_config(), current_schema_revision())
        async with h.factory() as session:
            after = (await session.execute(text(
                "SELECT to_jsonb(a)-ARRAY['started_at','updated_at'],a.updated_at "
                "FROM public.task_assignments a WHERE id=:id"
            ), {"id": receipt.assignment_id})).one()
            assert after[0] == before
            assert after[1] == receipt.exhausted_at
            assert await session.scalar(text("""
                SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND NOT t.tgisinternal AND t.tgenabled='D'
            """)) == 0
        await _assert_exhausted_assignment_immutable(h, receipt)
