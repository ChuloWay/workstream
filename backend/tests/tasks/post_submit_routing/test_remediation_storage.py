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
async def test_remediation_partial_effects_roll_back(tmp_path, isolated_database_env, target):
    async with remediation_source(tmp_path, isolated_database_env) as h:
        async with h.factory() as session:
            before = await outcome_snapshot(session)
        async with h.factory() as session:
            with pytest.raises(
                DBAPIError if target == "audit_events" else OutboxPersistenceError,
                match="controlled routing insert failure" if target == "audit_events" else "outbox_persistence_failed",
            ) as caught:
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
                assert isinstance(caught.value.__context__, DBAPIError)
                assert "controlled routing insert failure" in str(caught.value.__context__)
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
