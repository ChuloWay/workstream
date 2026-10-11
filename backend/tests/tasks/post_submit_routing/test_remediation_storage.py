"""Actual SQL closure and rollback guard the new contributor-only consequence."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.adapters.tasks import evaluation_completion_handler
from app.modules.outbox.api import OutboxPersistenceError
from app.modules.tasks.post_submit_routing.outcome import TaskPostSubmitOutcome
from app.modules.tasks.post_submit_routing.requests import TaskRoutingRequestUnavailable
from .outcome_support import apply_outcome, outcome_snapshot
from .remediation_support import remediation_source, no_economic_effects


async def test_remediation_outcome_substitution_rolls_back(tmp_path, isolated_database_env, monkeypatch):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            before = await outcome_snapshot(session)
        original = TaskPostSubmitOutcome.apply

        async def altered(owner, *args, **kwargs):
            result = await original(owner, *args, **kwargs)
            return result.model_copy(update={"routing_recommendation": "allow_review"})

        monkeypatch.setattr(TaskPostSubmitOutcome, "apply", altered)
        with pytest.raises(TaskRoutingRequestUnavailable, match="routing outcome recommendation differs"):
            await evaluation_completion_handler(sessions=h.factory)(h.envelope)
        async with h.factory() as session:
            assert await outcome_snapshot(session) == before


@pytest.mark.parametrize("target", ["audit_events", "outbox_events"])
async def test_remediation_partial_effects_roll_back(tmp_path, isolated_database_env, target, monkeypatch):
    from app.modules.outbox.repository import OutboxRepository

    actual_failures = []
    original_reserve = OutboxRepository.reserve

    async def observed_reserve(owner, *args, **kwargs):
        try:
            return await original_reserve(owner, *args, **kwargs)
        except DBAPIError as error:
            actual_failures.append("controlled routing insert failure" in str(error))
            raise

    monkeypatch.setattr(OutboxRepository, "reserve", observed_reserve)
    async with remediation_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            before = await outcome_snapshot(session)
        async with h.factory() as session:
            with pytest.raises(
                DBAPIError if target == "audit_events" else OutboxPersistenceError,
                match="controlled routing insert failure" if target == "audit_events" else "outbox_persistence_failed",
            ):
                async with session.begin():
                    # Fail the actual owner INSERT, not an unrelated mock write.
                    # DDL and all staged effects disappear with this transaction.
                    await session.execute(text("""
                        CREATE FUNCTION pg_temp.reject_routing_insert() RETURNS trigger
                        LANGUAGE plpgsql AS $$ BEGIN
                          IF NEW.event_type='TaskPostSubmitRouted' THEN
                            RAISE EXCEPTION 'controlled routing insert failure' USING ERRCODE='23514';
                          END IF;
                          RETURN NEW;
                        END $$
                    """))
                    await session.execute(text(
                        f"CREATE TRIGGER test_reject_routing_insert BEFORE INSERT ON public.{target} "
                        "FOR EACH ROW EXECUTE FUNCTION pg_temp.reject_routing_insert()"
                    ))
                    await apply_outcome(session, h, None)
            if target == "outbox_events":
                # The owner intentionally discards database exception context.
                # Observe its real repository call, without manufacturing failure.
                assert actual_failures == [True]
        async with h.factory() as session:
            assert await outcome_snapshot(session) == before
            await no_economic_effects(session)
        async with h.factory() as session, session.begin():
            assert (await apply_outcome(session, h, None)).routing_recommendation == "needs_revision"


async def test_database_rejects_crossed_remediation_recommendation(tmp_path, isolated_database_env, monkeypatch):
    import app.modules.tasks.post_submit_routing.outcome as owner

    async with remediation_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            before = await outcome_snapshot(session)
        original = owner._manifest

        def altered(*args):
            row = original(*args)
            row.routing_recommendation = "allow_review"
            return row

        with monkeypatch.context() as patch:
            patch.setattr(owner, "_manifest", altered)
            async with h.factory() as session:
                with pytest.raises(DBAPIError, match="routing source authority context mismatch"):
                    async with session.begin():
                        await apply_outcome(session, h, None)
        async with h.factory() as session:
            assert await outcome_snapshot(session) == before
        async with h.factory() as session, session.begin():
            assert (await apply_outcome(session, h, None)).routing_recommendation == "needs_revision"


async def test_remediation_notice_requires_exact_manifest_and_receipt(tmp_path, isolated_database_env, monkeypatch):
    import app.modules.tasks.post_submit_routing.outcome as owner
    from app.core.identifiers import new_record_id

    async with remediation_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            before = await outcome_snapshot(session)
        original = owner._notice
        for field in ("routing_manifest_id", "authorization_decision_id"):
            def altered(*args):
                notice = original(*args)
                return notice.model_copy(update={
                    "payload": notice.payload | {field: str(new_record_id())},
                })

            with monkeypatch.context() as patch:
                patch.setattr(owner, "_notice", altered)
                async with h.factory() as session:
                    with pytest.raises(DBAPIError, match="routing authority requires its complete governed outcome"):
                        async with session.begin():
                            await apply_outcome(session, h, None)
            async with h.factory() as session:
                assert await outcome_snapshot(session) == before
        async with h.factory() as session, session.begin():
            assert (await apply_outcome(session, h, None)).routing_recommendation == "needs_revision"


async def test_failure_cannot_authorize_acceptance(tmp_path, isolated_database_env):
    from app.core.identifiers import new_record_id

    async with remediation_source(tmp_path, isolated_database_env, human_review_required=False) as h:
        async with h.factory() as session, session.begin():
            result = await apply_outcome(session, h, None)
        async with h.factory() as session:
            # Exercise the actual SQL context validator with otherwise genuine
            # receipt/source facts. Each forbidden acceptance field is independent.
            assert await session.scalar(text(
                "SELECT public.task_routing_context_valid(m) FROM public.task_post_submit_routing_manifests m WHERE id=:id"
            ), {"id": result.routing_manifest_id}) is True
            for field, value in (("final_acceptance_id", str(new_record_id())), ("authorized_lifecycle_generation", 1)):
                assert await session.scalar(text("""
                    SELECT public.task_routing_context_valid(jsonb_populate_record(
                      NULL::public.task_post_submit_routing_manifests,
                      to_jsonb(m) || jsonb_build_object(CAST(:field AS text),CAST(:value AS text))))
                    FROM public.task_post_submit_routing_manifests m WHERE id=:id
                """), {"id": result.routing_manifest_id, "field": field, "value": str(value)}) is False
            await no_economic_effects(session)
