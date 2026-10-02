"""Canonical stored-source proof, without acceptance authority or effects."""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from tests.reviews.acceptance.support import acceptance_source, attach_acceptance, insert_acceptance
from tests.reviews.decision.support import attach_review_source, insert_review, review_source
from tests.reviews.packet.support import prepare_packet
from tests.reviews.packet.test_repository import wait_for_blocker
from tests.tasks.post_submit_routing.support import completed_sibling_source, insert_source


async def reject(h, source, message, **overrides):
    async with h.factory() as session:
        with pytest.raises(DBAPIError, match=message):
            await insert_acceptance(session, source, **overrides)
            await session.commit()
    async with h.factory() as session:
        assert await session.scalar(text("SELECT count(*) FROM public.final_acceptances")) == 0


@pytest.mark.asyncio
async def test_human_acceptance_source(tmp_path, clean_postgres_database):
    async with acceptance_source(tmp_path, clean_postgres_database) as h:
        async with h.factory() as session:
            state_query = text(
                "SELECT t.status,a.status FROM public.workstream_tasks t "
                "JOIN public.task_assignments a ON a.task_id=t.id WHERE t.id=:id"
            )
            state_params = {"id": h.acceptance.task_id}
            before = (await session.execute(state_query, state_params)).one()
            await insert_acceptance(session, h.acceptance)
            await session.commit()
            actual = await session.scalar(
                text("SELECT to_jsonb(a) FROM public.final_acceptances a")
            )
            assert actual.pop("accepted_at") is not None
            assert actual == h.acceptance.model_dump(mode="json")
            # Storage creates neither TASK effects nor contributions or fabricated Review.
            assert await session.scalar(text("SELECT count(*) FROM public.reviews")) == 1
            assert (await session.execute(state_query, state_params)).one() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["reject", "needs_revision"])
async def test_non_accept_review_denied(tmp_path, clean_postgres_database, decision):
    async with acceptance_source(tmp_path, clean_postgres_database, decision=decision) as h:
        await reject(h, h.acceptance, "final acceptance human source mismatch")


@pytest.mark.asyncio
async def test_exclusive_source_shape(tmp_path, clean_postgres_database):
    async with acceptance_source(tmp_path, clean_postgres_database) as h:
        for fields in (
            {"source_review_id": None},
            {"source_routing_manifest_id": new_record_id()},
            {"acceptance_source": "task_post_submit_route"},
            {"acceptance_source": "automatic"},
        ):
            await reject(h, h.acceptance, "ck_final_acceptances_source_shape", **fields)


@pytest.mark.asyncio
async def test_acceptance_owner_substitution(tmp_path, clean_postgres_database):
    async with acceptance_source(tmp_path, clean_postgres_database) as h:
        sibling = await completed_sibling_source(h)
        await prepare_packet(sibling)
        await attach_review_source(sibling)
        async with h.factory() as session:
            await insert_review(session, sibling.review)
            await session.commit()
        await attach_acceptance(sibling)
        for field in (
            "task_id",
            "submission_id",
            "source_review_id",
            "accepted_submitter_id",
            "recorded_by",
        ):
            replacement = getattr(sibling.acceptance, field)
            if field == "accepted_submitter_id":
                replacement = sibling.acceptance.recorded_by
            assert replacement != getattr(h.acceptance, field)
            await reject(
                h,
                h.acceptance.model_copy(update={field: replacement}),
                "final acceptance (canonical lineage|human source) mismatch",
            )
        async with acceptance_source(
            tmp_path / "foreign",
            clean_postgres_database,
            storage_settings=h.settings,
            provision_services=False,
        ) as foreign:
            for field in ("project_id", "policy_context_ref", "source_review_id", "submission_id"):
                await reject(
                    h,
                    h.acceptance.model_copy(update={field: getattr(foreign.acceptance, field)}),
                    "final acceptance (canonical lineage|human source) mismatch",
                )
        # All other joins remain valid; remove only reviewer equality.
        async with h.factory() as session:
            definition = await session.scalar(
                text(
                    "SELECT pg_get_functiondef('public.guard_final_acceptance_source()'::regprocedure)"
                )
            )
            predicate = "AND r.reviewer_id=NEW.recorded_by"
            assert definition.count(predicate) == 1
            await session.execute(text(definition.replace(predicate, "")))
            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                with pytest.raises(DBAPIError, match="final acceptance human source mismatch"):
                    await insert_acceptance(
                        session, h.acceptance, recorded_by=sibling.acceptance.recorded_by
                    )
            await session.rollback()
        async with h.factory() as session:
            await insert_acceptance(session, h.acceptance)
            await session.commit()


@pytest.mark.asyncio
async def test_automated_branch_polarity(tmp_path, clean_postgres_database):
    async with acceptance_source(tmp_path, clean_postgres_database) as h:
        async with h.factory() as session:
            await insert_source(session, h.source)
            await session.commit()
            service = await session.scalar(
                text("SELECT id FROM public.actor_profiles WHERE actor_kind='service' LIMIT 1")
            )
            assert service is not None
        source = h.acceptance.model_copy(
            update={
                "acceptance_source": "task_post_submit_route",
                "source_review_id": None,
                "source_routing_manifest_id": h.source["id"],
                "recorded_by": service,
            }
        )
        await reject(h, source, "final acceptance routing source mismatch")
        async with h.factory() as session:
            definition = await session.scalar(
                text(
                    "SELECT pg_get_functiondef('public.guard_final_acceptance_source()'::regprocedure)"
                )
            )
            predicate = "ROW(manifest.human_review_required,policy_required)=ROW(false,false)"
            assert definition.count(predicate) == 1
            await session.execute(
                text(
                    definition.replace(
                        predicate,
                        "ROW(manifest.human_review_required,policy_required)=ROW(true,true)",
                    )
                )
            )
            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                with pytest.raises(DBAPIError, match="final acceptance routing source mismatch"):
                    await insert_acceptance(session, source)
            await session.rollback()
        await reject(h, source, "final acceptance routing source mismatch")


@pytest.mark.asyncio
async def test_acceptance_clock_and_immutability(tmp_path, clean_postgres_database):
    async with acceptance_source(tmp_path, clean_postgres_database) as h:
        async with h.factory() as session:
            before = await session.scalar(text("SELECT clock_timestamp()"))
            await insert_acceptance(
                session, h.acceptance, accepted_at=datetime(2000, 1, 1, tzinfo=UTC)
            )
            await session.commit()
            stored = await session.scalar(text("SELECT accepted_at FROM public.final_acceptances"))
            after = await session.scalar(text("SELECT clock_timestamp()"))
            assert before <= stored <= after
        for command in (
            "UPDATE public.final_acceptances SET accepted_at=clock_timestamp()",
            "UPDATE public.final_acceptances SET recorded_by=accepted_submitter_id",
            "DELETE FROM public.final_acceptances",
            "TRUNCATE public.final_acceptances",
        ):
            async with h.factory() as session:
                with pytest.raises(DBAPIError, match="immutable"):
                    await session.execute(text(command))
        async with h.factory() as session:
            assert (
                await session.scalar(text("SELECT id FROM public.final_acceptances"))
                == h.acceptance.id
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_first", [True, False])
async def test_acceptance_unique_and_rollback(tmp_path, clean_postgres_database, commit_first):
    async with acceptance_source(tmp_path, clean_postgres_database) as h:
        ready = asyncio.Future()
        duplicate = h.acceptance.model_copy(update={"id": new_record_id()})

        async def competitor():
            async with h.factory() as second:
                ready.set_result(await second.scalar(text("SELECT pg_backend_pid()")))
                if commit_first:
                    with pytest.raises(DBAPIError, match="uq_final_acceptances_task_id"):
                        await insert_acceptance(second, duplicate)
                else:
                    await insert_acceptance(second, duplicate)
                    await second.commit()

        async with h.factory() as first:
            await insert_acceptance(first, h.acceptance)
            contender = asyncio.create_task(competitor())
            try:
                await wait_for_blocker(h.factory, await ready)
                await (first.commit() if commit_first else first.rollback())
                await asyncio.wait_for(contender, 10)
            finally:
                if not contender.done():
                    contender.cancel()
                await asyncio.gather(contender, return_exceptions=True)
        async with h.factory() as session:
            ids = (await session.scalars(text("SELECT id FROM public.final_acceptances"))).all()
            assert ids == [h.acceptance.id if commit_first else duplicate.id]
            assert await session.scalar(text("SELECT id FROM public.reviews")) == h.review.id


@pytest.mark.asyncio
async def test_missing_acceptance_source(tmp_path, clean_postgres_database):
    async with review_source(tmp_path, clean_postgres_database) as h:
        await attach_acceptance(h)
        await reject(h, h.acceptance, "final acceptance human source mismatch")
        async with h.factory() as parent:
            await insert_review(parent, h.review)
            # A real uncommitted parent is invisible to the independent child transaction.
            async with h.factory() as child:
                await child.execute(text("SET LOCAL statement_timeout='2s'"))
                with pytest.raises(DBAPIError, match="final acceptance human source mismatch"):
                    await insert_acceptance(child, h.acceptance)
            await parent.rollback()
        async with h.factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM public.reviews")) == 0
            assert await session.scalar(text("SELECT count(*) FROM public.final_acceptances")) == 0
            await insert_review(session, h.review)
            await insert_acceptance(session, h.acceptance)
            await session.commit()
