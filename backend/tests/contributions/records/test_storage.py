"""Direct PostgreSQL proof of source lineage and exact frozen economics."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from app.modules.compensation.awards.models import CompensationAward
from app.modules.contributions.records.models import ContributionRecord
from tests.reviews.acceptance.support import insert_acceptance
from .support import contribution_source, insert_record, insert_award, award_values, rows, retire_policy_and_suspend_bindings

pytestmark = pytest.mark.postgres_schema_contract


async def reject_record(session, record, message, **changes):
    with pytest.raises(DBAPIError, match=message):
        async with session.begin_nested():
            await insert_record(session, record, **changes)


async def reject_award(session, award, message, **changes):
    with pytest.raises(DBAPIError, match=message):
        async with session.begin_nested():
            await insert_award(session, award, **changes)


@pytest.mark.parametrize("decision", ["accept", "needs_revision", "reject"])
async def test_contribution_sources(tmp_path, isolated_database_env, decision):
    async with contribution_source(tmp_path, isolated_database_env, decision=decision) as h:
        async with h.factory() as session, session.begin():
            await reject_record(session, h.reviewer_record, "ck_contribution_records_source_shape",
                                source_task_assignment_id=h.submitter_record.source_task_assignment_id)
            await insert_record(session, h.reviewer_record)
            await reject_record(session, h.reviewer_record, "uq_contribution_records_source_review_id", id=new_record_id())
            if decision == "accept":
                await insert_record(session, h.submitter_record)
            else:
                with pytest.raises(DBAPIError, match="final acceptance human source mismatch"):
                    async with session.begin_nested():
                        await insert_acceptance(session, h.acceptance)
                await reject_record(session, h.submitter_record, "contribution submitter source mismatch")
        async with h.factory() as session:
            expected = [h.reviewer_record] + ([h.submitter_record] if decision == "accept" else [])
            stored = await rows(session, "contribution_records")
            assert len(stored) == len(expected)
            for record in expected:
                actual = next(r for r in stored if r["id"] == str(record.id))
                assert {k: v for k, v in actual.items() if k != "created_at"} == record.model_dump(mode="json")
            assert await rows(session, "compensation_awards") == []
            assert len(await rows(session, "reviews")) == 1


@pytest.mark.parametrize("historical", [False, True])
async def test_frozen_awards(tmp_path, isolated_database_env, historical):
    async with contribution_source(tmp_path, isolated_database_env, paid=True) as h:
        if historical:
            await retire_policy_and_suspend_bindings(h)
        async with h.factory() as session, session.begin():
            for record in (h.reviewer_record, h.submitter_record):
                await insert_record(session, record)
                awards = await award_values(session, record)
                assert {a["instrument_type"] for a in awards} == {"money", "project_points"}
                for award in awards:
                    await insert_award(session, award)
        async with h.factory() as session:
            actual = (await session.execute(text("""
                SELECT a.*, r.contribution_type, d.quantity AS definition_quantity,
                  d.unit_code AS definition_unit, d.adapter_binding_id AS definition_binding,
                  d.contribution_policy_version_id AS definition_policy,
                  d.contribution_type AS definition_type, r.contributor_id AS record_actor
                FROM public.compensation_awards a
                JOIN public.contribution_records r ON r.id=a.contribution_record_id
                JOIN public.contribution_award_definitions d ON d.id=a.award_definition_id
            """))).mappings().all()
            assert len(actual) == 4
            assert {(a["contribution_type"], a["instrument_type"]) for a in actual} == {
                (kind, instrument) for kind in ("completed_review", "accepted_submission")
                for instrument in ("money", "project_points")
            }
            for a in actual:
                assert a["quantity"] == a["definition_quantity"] == (
                    Decimal("2.125000000000000001") if a["instrument_type"] == "money" else Decimal("7")
                )
                assert a["unit_code"] == a["definition_unit"]
                assert a["adapter_binding_id"] == a["definition_binding"]
                assert a["contribution_policy_version_id"] == a["definition_policy"]
                assert a["contribution_type"] == a["definition_type"]
                assert a["contributor_id"] == a["record_actor"]


async def test_contribution_source_substitution(tmp_path, isolated_database_env):
    from tests.tasks.post_submit_routing.support import completed_sibling_source
    async with contribution_source(tmp_path, isolated_database_env) as h:
        sibling = await completed_sibling_source(h)
        async with contribution_source(
            tmp_path / "foreign", isolated_database_env,
            provision_services=False, storage_settings=h.settings,
        ) as foreign:
            async with h.factory() as session:
                for source in (h.reviewer_record, h.submitter_record):
                    for changes in (
                        {"project_id": foreign.review.project_id},
                        {"task_id": sibling.request.task_id},
                        {"submission_id": sibling.request.submission_id},
                        {"contributor_id": foreign.review.reviewer_id},
                        {"contribution_policy_version_id": foreign.reviewer_record.contribution_policy_version_id},
                        {"artifact_hash": "sha256:" + "0" * 64},
                    ):
                        await reject_record(session, source, "contribution .* mismatch", **changes)
                await reject_record(session, h.reviewer_record, "contribution reviewer source mismatch",
                                    source_review_lease_id=foreign.review.review_lease_id)
                await reject_record(session, h.reviewer_record, "contribution reviewer source mismatch",
                                    source_review_id=foreign.review.id)
                await reject_record(session, h.submitter_record, "contribution submitter source mismatch",
                                    source_final_acceptance_id=foreign.acceptance.id)
                await reject_record(session, h.submitter_record, "contribution submitter source mismatch",
                                    source_task_assignment_id=sibling.request.assignment_id)
                assert await rows(session, "contribution_records") == []
                # All remaining equalities and the FK still hold for this independent assignment.
                definition = await session.scalar(text(
                    "SELECT pg_get_functiondef('public.guard_contribution_source()'::regprocedure)"
                ))
                predicate = "AND assignment.id=NEW.source_task_assignment_id"
                assert definition.count(predicate) == 1
                await session.execute(text(definition.replace(predicate, "")))
                with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                    await reject_record(session, h.submitter_record, "contribution submitter source mismatch",
                                        source_task_assignment_id=sibling.request.assignment_id)
                await session.rollback()
            async with h.factory() as session, session.begin():
                await insert_record(session, h.submitter_record)
                await insert_record(session, h.reviewer_record)


async def test_award_definition_substitution(tmp_path, isolated_database_env):
    async with contribution_source(tmp_path, isolated_database_env, paid=True) as h:
        async with h.factory() as session:
            await insert_record(session, h.reviewer_record)
            reviewer_awards = await award_values(session, h.reviewer_record)
            await session.commit()
        async with h.factory() as session:
            money, points = reviewer_awards
            for changes in (
                {"quantity": money["quantity"] + Decimal("0.000000000000000001")},
                {"unit_code": "EUR"},
                {"adapter_binding_id": points["adapter_binding_id"]},
                {"award_definition_id": points["award_definition_id"]},
                {"instrument_type": "project_points", "quantity": Decimal("7"), "unit_code": "PTS"},
            ):
                await reject_award(session, money, "award frozen definition mismatch", **changes)
            await reject_award(session, money, "award contribution lineage mismatch",
                               contributor_id=h.submitter_record.contributor_id)
            assert await rows(session, "compensation_awards") == []
            definition = await session.scalar(text(
                "SELECT pg_get_functiondef('public.guard_compensation_award()'::regprocedure)"
            ))
            predicate = "AND definition.quantity=NEW.quantity"
            assert definition.count(predicate) == 1
            await session.execute(text(definition.replace(predicate, "")))
            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                await reject_award(session, money, "award frozen definition mismatch",
                                   quantity=money["quantity"] + Decimal("1"))
            await session.rollback()
        async with contribution_source(
            tmp_path / "foreign-awards", isolated_database_env, paid=True,
            provision_services=False, storage_settings=h.settings,
        ) as foreign:
            async with h.factory() as session:
                await insert_record(session, h.submitter_record)
                money, points = await award_values(session, h.submitter_record)
                foreign_money = (await award_values(session, foreign.submitter_record))[0]
                await reject_award(
                    session,
                    money,
                    "award frozen definition mismatch",
                    award_definition_id=reviewer_awards[0]["award_definition_id"],
                )
                await reject_award(session, money, "award contribution lineage mismatch",
                                   project_id=foreign_money["project_id"])
                await reject_award(session, money, "award contribution lineage mismatch",
                                   contribution_policy_version_id=foreign_money["contribution_policy_version_id"])
                await reject_award(session, money, "award frozen definition mismatch",
                                   award_definition_id=foreign_money["award_definition_id"],
                                   adapter_binding_id=foreign_money["adapter_binding_id"])
                assert await rows(session, "compensation_awards") == []
                await insert_award(session, money)
                await insert_award(session, points)
                await session.commit()
        async with h.factory() as session, session.begin():
            await reject_award(session, money, "uq_compensation_awards", id=new_record_id())


async def test_unpaid_rule_rejects_award(tmp_path, isolated_database_env):
    async with contribution_source(tmp_path, isolated_database_env) as h:
        async with contribution_source(
            tmp_path / "paid", isolated_database_env, paid=True,
            provision_services=False, storage_settings=h.settings,
        ) as paid:
            async with h.factory() as session:
                await insert_record(session, h.reviewer_record)
                await insert_record(session, h.submitter_record)
                foreign = (await award_values(session, paid.submitter_record))[0]
                for source in (h.reviewer_record, h.submitter_record):
                    await reject_award(session, foreign, "unpaid contribution cannot receive an award",
                        project_id=source.project_id, contribution_record_id=source.id,
                        contributor_id=source.contributor_id,
                        contribution_policy_version_id=source.contribution_policy_version_id)
                assert await rows(session, "compensation_awards") == []
                await session.commit()


async def test_contribution_award_immutability(tmp_path, isolated_database_env):
    async with contribution_source(tmp_path, isolated_database_env, paid=True) as h:
        async with h.factory() as session:
            before = await session.scalar(select(func.clock_timestamp()))
            await insert_record(session, h.submitter_record, created_at=datetime(2000, 1, 1, tzinfo=UTC))
            awards = await award_values(session, h.submitter_record)
            award = awards[0]
            for values in awards:
                await insert_award(
                    session, values, created_at=datetime(2000, 1, 1, tzinfo=UTC)
                )
            await session.commit()
            after = await session.scalar(select(func.clock_timestamp()))
            record = await session.get(ContributionRecord, h.submitter_record.id)
            stored_award = await session.get(CompensationAward, award["id"])
            assert before <= record.created_at <= after
            assert before <= stored_award.created_at <= after
            saved = {table: await rows(session, table) for table in ("contribution_records", "compensation_awards")}
        for table in saved:
            for statement in (f"UPDATE public.{table} SET created_at=clock_timestamp()",
                              f"DELETE FROM public.{table}", f"TRUNCATE public.{table} CASCADE"):
                async with h.factory() as session:
                    with pytest.raises(DBAPIError, match="immutable"):
                        await session.execute(text(statement))
                    await session.rollback()
                    assert {name: await rows(session, name) for name in saved} == saved


@pytest.mark.parametrize("kind", ["contribution", "award"])
@pytest.mark.parametrize("commit_first", [True, False])
async def test_contribution_award_concurrency(tmp_path, isolated_database_env, kind, commit_first):
    import asyncio
    from tests.reviews.packet.test_repository import wait_for_blocker
    # Contribution source uniqueness is isolated with an unpaid accepted-submission
    # record; the participant owns complete paid-set assembly. Award uniqueness is
    # isolated with a reviewer award until the future reviewer participant exists.
    async with contribution_source(
        tmp_path, isolated_database_env, paid=kind == "award"
    ) as h:
        async with h.factory() as session:
            award = (
                (await award_values(session, h.reviewer_record))[0]
                if kind == "award"
                else None
            )
            if kind == "award":
                await insert_record(session, h.reviewer_record)
                await session.commit()
        first_id = h.submitter_record.id if kind == "contribution" else award["id"]
        duplicate_id = new_record_id()
        ready = asyncio.Future()

        async def insert_candidate(session, identity):
            if kind == "contribution":
                await insert_record(session, h.submitter_record, id=identity)
            else:
                await insert_award(session, award, id=identity)

        async def competitor():
            async with h.factory() as session:
                ready.set_result(await session.scalar(text("SELECT pg_backend_pid()")))
                if commit_first:
                    with pytest.raises(DBAPIError, match="uq_.*"):
                        await insert_candidate(session, duplicate_id)
                else:
                    await insert_candidate(session, duplicate_id)
                    await session.commit()

        async with h.factory() as first:
            await insert_candidate(first, first_id)
            contender = asyncio.create_task(competitor())
            try:
                await wait_for_blocker(h.factory, await ready)
                await (first.commit() if commit_first else first.rollback())
                await asyncio.wait_for(contender, 10)
            finally:
                if not contender.done():
                    contender.cancel()
                await asyncio.gather(contender, return_exceptions=True)
        table = "contribution_records" if kind == "contribution" else "compensation_awards"
        async with h.factory() as session:
            actual = await rows(session, table)
            assert [r["id"] for r in actual] == [str(first_id if commit_first else duplicate_id)]
            before = {name: await rows(session, name) for name in ("contribution_records", "compensation_awards")}
            rollback_record = (
                h.reviewer_record if kind == "contribution" else h.submitter_record
            )
            await insert_record(session, rollback_record)
            for values in await award_values(session, rollback_record):
                await insert_award(session, values)
            await session.rollback()
            assert {name: await rows(session, name) for name in before} == before


async def test_missing_contribution_parent(tmp_path, isolated_database_env):
    async with contribution_source(tmp_path, isolated_database_env, paid=True, persist_acceptance=False) as h:
        async with h.factory() as session:
            await reject_record(session, h.submitter_record, "contribution submitter source mismatch")
            award = (await award_values(session, h.submitter_record))[0]
            await reject_award(session, award, "award contribution lineage mismatch")
        async with h.factory() as parent:
            await insert_acceptance(parent, h.acceptance)
            async with h.factory() as child:
                await child.execute(text("SET LOCAL statement_timeout='2s'"))
                await reject_record(child, h.submitter_record, "contribution submitter source mismatch")
            await insert_record(parent, h.submitter_record)
            async with h.factory() as child:
                await child.execute(text("SET LOCAL statement_timeout='2s'"))
                await reject_award(child, award, "award contribution lineage mismatch")
            await parent.rollback()
        async with h.factory() as session:
            assert await rows(session, "final_acceptances") == []
            assert await rows(session, "contribution_records") == []
            assert await rows(session, "compensation_awards") == []
            await insert_acceptance(session, h.acceptance)
            await insert_record(session, h.submitter_record)
            for values in await award_values(session, h.submitter_record):
                await insert_award(session, values)
            await session.commit()


async def test_accepted_submission_complete_award_set_is_deferred_and_exact(
    tmp_path, isolated_database_env
):
    async with contribution_source(tmp_path, isolated_database_env, paid=True) as paid:
        async with paid.factory() as session:
            awards = await award_values(session, paid.submitter_record)
            await insert_record(session, paid.submitter_record)
            await insert_award(session, awards[0])
            with pytest.raises(DBAPIError, match="incomplete award set"):
                await session.commit()
            await session.rollback()
        async with paid.factory() as session:
            assert await rows(session, "contribution_records") == []
            assert await rows(session, "compensation_awards") == []
            await insert_record(session, paid.submitter_record)
            for award in awards:
                await insert_award(session, award)
            await session.commit()
        async with paid.factory() as session:
            assert len(await rows(session, "contribution_records")) == 1
            assert len(await rows(session, "compensation_awards")) == 2

    async with contribution_source(
        tmp_path / "unpaid", isolated_database_env, provision_services=False,
        storage_settings=paid.settings,
    ) as unpaid:
        async with unpaid.factory() as session:
            await insert_record(session, unpaid.submitter_record)
            await session.commit()
        async with unpaid.factory() as session:
            assert len(await rows(session, "contribution_records")) == 2
            assert len(await rows(session, "compensation_awards")) == 2


async def test_removing_deferred_completeness_guard_breaks_partial_set_rejection(
    tmp_path, isolated_database_env
):
    async with contribution_source(tmp_path, isolated_database_env, paid=True) as h:
        async with h.factory() as session:
            awards = await award_values(session, h.submitter_record)
            await session.execute(text(
                "DROP TRIGGER accepted_submission_award_set_from_contribution "
                "ON public.contribution_records"
            ))
            await session.execute(text(
                "DROP TRIGGER accepted_submission_award_set_from_award "
                "ON public.compensation_awards"
            ))
            await insert_record(session, h.submitter_record)
            await insert_award(session, awards[0])
            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                with pytest.raises(DBAPIError, match="incomplete award set"):
                    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            await session.rollback()
