"""Real PostgreSQL proof of immutable Review source custody."""

import pytest
from sqlalchemy import text

from tests.reviews.decision.support import finding, insert_review, review_source


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["accept", "needs_revision", "reject"])
async def test_complete_decision_aggregate(tmp_path, clean_postgres_database, decision):
    async with review_source(tmp_path, clean_postgres_database) as h:
        source = h.review.model_copy(
            update={
                "decision": decision,
                "findings": (finding(),) if decision == "needs_revision" else (),
            }
        )
        async with h.factory() as session:
            from datetime import UTC, datetime

            before = await session.scalar(text("SELECT clock_timestamp()"))
            await insert_review(
                session, source, header={"completed_at": datetime(2000, 1, 1, tzinfo=UTC)}
            )
            await session.commit()
            completed = await session.scalar(
                text("SELECT completed_at FROM public.reviews WHERE id=:id"), {"id": source.id}
            )
            after = await session.scalar(text("SELECT clock_timestamp()"))
            assert before <= completed <= after
            payload = await session.scalar(
                text("SELECT public.review_source_payload(:id,false)"), {"id": source.id}
            )
            assert payload == source.semantic_payload()
            request_payload = await session.scalar(
                text("SELECT public.review_source_payload(:id,true)"), {"id": source.id}
            )
            assert request_payload == source.semantic_payload(request=True)


async def assert_rejected(h, source, message, **options):
    from sqlalchemy.exc import DBAPIError

    async with h.factory() as session:
        with pytest.raises(DBAPIError, match=message):
            await insert_review(session, source, **options)
            await session.commit()
    async with h.factory() as session:
        assert await session.scalar(text("SELECT count(*) FROM public.reviews")) == 0
        assert (
            await session.scalar(text("SELECT count(*) FROM public.review_decision_requests")) == 0
        )


@pytest.mark.asyncio
async def test_owner_substitution(tmp_path, clean_postgres_database):
    from sqlalchemy.exc import DBAPIError
    from tests.reviews.packet.support import prepare_packet
    from tests.tasks.post_submit_routing.support import completed_sibling_source
    from tests.reviews.decision.support import attach_review_source

    async with review_source(tmp_path, clean_postgres_database) as h:
        sibling = await completed_sibling_source(h)
        await prepare_packet(sibling)
        await attach_review_source(sibling)
        for name in (
            "submission_id",
            "task_assignment_id",
            "reviewer_id",
            "packet_manifest_id",
            "task_id",
        ):
            replacement = getattr(sibling.review, name)
            assert replacement != getattr(h.review, name)
            altered = h.review.model_copy(update={name: replacement})
            await assert_rejected(h, altered, "review source canonical ownership mismatch")
        # The reviewer is a valid human from another lease. All hashes reflect it.
        altered = h.review.model_copy(update={"reviewer_id": sibling.review.reviewer_id})
        async with h.factory() as session:
            definition = await session.scalar(
                text(
                    "SELECT pg_get_functiondef('public.validate_review_source(uuid)'::regprocedure)"
                )
            )
            predicate = "AND l.reviewer_id=r.reviewer_id"
            assert definition.count(predicate) == 1
            await session.execute(text(definition.replace(predicate, "")))
            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                with pytest.raises(DBAPIError, match="review source canonical ownership mismatch"):
                    await insert_review(session, altered)
                    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            await session.rollback()
        async with review_source(
            tmp_path / "foreign",
            clean_postgres_database,
            storage_settings=h.settings,
            provision_services=False,
        ) as foreign:
            for name in (
                "project_id",
                "locked_review_policy_id",
                "packet_manifest_id",
                "reviewer_contribution_policy_version_id",
            ):
                await assert_rejected(
                    h,
                    h.review.model_copy(update={name: getattr(foreign.review, name)}),
                    "review source (lease unavailable|canonical ownership mismatch)",
                )
        for fields in (
            {"submission_version": h.review.submission_version + 1},
            {"locked_guide_version": h.review.locked_guide_version + "-other"},
            {"locked_review_policy_generation": h.review.locked_review_policy_generation + 1},
            {"artifact_hash": "sha256:" + "a" * 64},
            {"packet_manifest_digest": "sha256:" + "b" * 64},
            {"locked_review_policy_hash": "sha256:" + "c" * 64},
        ):
            await assert_rejected(
                h, h.review.model_copy(update=fields), "review source canonical ownership mismatch"
            )
        async with h.factory() as session:
            contributor = await session.scalar(
                text("SELECT contributor_id FROM public.submissions WHERE id=:id"),
                {"id": h.review.submission_id},
            )
        await assert_rejected(
            h,
            h.review.model_copy(update={"reviewer_id": contributor}),
            "review source canonical ownership mismatch",
        )
        async with h.factory() as session:
            await insert_review(session, h.review)
            await session.commit()


@pytest.mark.asyncio
async def test_lease_terminal_custody(tmp_path, clean_postgres_database):
    async with review_source(tmp_path, clean_postgres_database) as h:
        await assert_rejected(
            h, h.review, "review source canonical ownership mismatch", close=False
        )
        async with h.factory() as session:
            await insert_review(session, h.review)
            await session.commit()

        from sqlalchemy.exc import DBAPIError

        async with h.factory() as session:
            with pytest.raises(DBAPIError, match="recorded review queue closure is immutable"):
                await session.execute(
                    text(
                        "UPDATE public.review_queue_entries SET closed_reason='admin_cancelled' WHERE id=:id"
                    ),
                    {"id": h.queue_id},
                )


@pytest.mark.asyncio
async def test_expired_active_lease_cannot_record_review(tmp_path, clean_postgres_database):
    from datetime import timedelta
    from tests.reviews.packet.support import wait_for_lease_expiry

    async with review_source(
        tmp_path, clean_postgres_database, lease_duration=timedelta(seconds=5)
    ) as h:
        async with h.factory() as session:
            await wait_for_lease_expiry(session, h.lease_id)
        await assert_rejected(h, h.review, "review source requires active unexpired lease")


@pytest.mark.asyncio
async def test_request_custody(tmp_path, clean_postgres_database):
    from app.core.identifiers import new_record_id

    async with review_source(tmp_path, clean_postgres_database) as h:
        await assert_rejected(
            h, h.review, "review source completed request mismatch", include_request=False
        )
        await assert_rejected(
            h,
            h.review,
            "review source request digest mismatch",
            request={"request_digest": "sha256:" + "0" * 64},
        )
        # No fake command/CON participant: raw storage remains caller-owned.
        async with h.factory() as session:
            await insert_review(session, h.review)
            await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            await session.rollback()
        async with h.factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM public.reviews")) == 0
            assert await session.scalar(text("SELECT count(*) FROM public.review_findings")) == 0
            key = new_record_id()
            await insert_review(session, h.review, request={"idempotency_key": key})
            await session.commit()
            stored = (
                await session.execute(
                    text("""
                SELECT review_id,request_digest FROM public.review_decision_requests
                WHERE project_id=:project AND reviewer_id=:reviewer AND idempotency_key=:key
            """),
                    {"project": h.review.project_id, "reviewer": h.review.reviewer_id, "key": key},
                )
            ).one()
            assert stored.review_id == h.review.id
            assert stored.request_digest == h.review.request_digest
            assert (
                stored.request_digest
                != h.review.model_copy(update={"summary": "Changed."}).request_digest
            )


@pytest.mark.asyncio
async def test_aggregate_immutability(tmp_path, clean_postgres_database):
    from sqlalchemy import insert
    from sqlalchemy.exc import DBAPIError
    from app.modules.reviews.decision.models import ReviewFinding

    async with review_source(tmp_path, clean_postgres_database) as h:
        source = h.review.model_copy(update={"findings": (finding(kind="advisory"),)})
        await assert_rejected(
            h, source, "review source child counts or order mismatch", header={"finding_count": 0}
        )
        await assert_rejected(
            h,
            source,
            "review source aggregate digest mismatch",
            header={"aggregate_digest": "sha256:" + "0" * 64},
        )
        for decision, findings in [("accept", (finding(),)), ("needs_revision", ())]:
            await assert_rejected(
                h,
                source.model_copy(update={"decision": decision, "findings": findings}),
                "review source blocking findings incompatible with decision",
            )
        await assert_rejected(
            h,
            source.model_copy(update={"decision": "reject", "summary": " \n\t"}),
            "ck_reviews_summary",
        )
        # A complete, correctly rehashed changed nested value exposes the digest guard.
        async with h.factory() as session:
            definition = await session.scalar(
                text(
                    "SELECT pg_get_functiondef('public.validate_review_source(uuid)'::regprocedure)"
                )
            )
            predicate = "IF r.aggregate_digest IS DISTINCT FROM"
            assert definition.count(predicate) == 1
            await session.execute(
                text(
                    definition.replace(
                        predicate, "IF false AND r.aggregate_digest IS DISTINCT FROM"
                    )
                )
            )
            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                with pytest.raises(DBAPIError, match="review source aggregate digest mismatch"):
                    await insert_review(
                        session, source, header={"aggregate_digest": "sha256:" + "0" * 64}
                    )
                    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            await session.rollback()
        async with h.factory() as session:
            await insert_review(session, source)
            await session.commit()
        async with h.factory() as session:
            with pytest.raises(DBAPIError, match="review source child counts or order mismatch"):
                await session.execute(
                    insert(ReviewFinding).values(
                        **finding(kind="advisory").model_dump(), review_id=source.id, item_order=1
                    )
                )
                await session.commit()
        for table in (
            "reviews",
            "review_findings",
            "finding_resolutions",
            "review_decision_requests",
        ):
            for statement in (
                f"UPDATE public.{table} SET id=id",
                f"DELETE FROM public.{table}",
                f"TRUNCATE public.{table} CASCADE",
            ):
                async with h.factory() as session:
                    with pytest.raises(DBAPIError, match="immutable"):
                        await session.execute(text(statement))


@pytest.mark.asyncio
async def test_predecessor_chain(tmp_path, clean_postgres_database):
    from app.core.identifiers import new_record_id
    from app.modules.reviews.decision.schemas import FindingResolutionInput
    from tests.reviews.decision.support import successor_source
    from sqlalchemy.exc import DBAPIError

    async with review_source(tmp_path, clean_postgres_database) as h:
        first = h.review.model_copy(update={"decision": "needs_revision", "findings": (finding(),)})
        async with h.factory() as session:
            await insert_review(session, first)
            await session.commit()
        gap = await successor_source(h, with_packet=False)
        successor = await successor_source(gap)
        resolving = successor.review.model_copy(
            update={
                "predecessor_review_id": first.id,
                "resolutions": (
                    FindingResolutionInput(
                        id=new_record_id(),
                        finding_id=first.findings[0].id,
                        result="resolved",
                        rationale="Corrected in the submitted revision.",
                    ),
                ),
            }
        )
        async with h.factory() as session:
            with pytest.raises(DBAPIError, match="review source predecessor mismatch"):
                await insert_review(
                    session, resolving.model_copy(update={"predecessor_review_id": None})
                )
                await session.commit()
        async with h.factory() as session:
            await insert_review(session, resolving)
            await session.commit()
            assert (
                await session.scalar(
                    text("SELECT predecessor_review_id FROM public.reviews WHERE id=:id"),
                    {"id": resolving.id},
                )
                == first.id
            )

        # A new stored successor cannot branch back to an already-used predecessor.
        later = await successor_source(successor)
        async with h.factory() as session:
            with pytest.raises(DBAPIError, match="uq_reviews_predecessor_review_id"):
                await insert_review(
                    session, later.review.model_copy(update={"predecessor_review_id": first.id})
                )
                await session.commit()


@pytest.mark.asyncio
async def test_concurrent_request_and_child(tmp_path, clean_postgres_database):
    import asyncio

    from sqlalchemy import insert
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.exc import DBAPIError
    from app.core.identifiers import new_record_id
    from app.modules.reviews.decision.models import ReviewDecisionRequest, ReviewFinding
    from tests.reviews.packet.test_repository import wait_for_blocker

    async with review_source(tmp_path, clean_postgres_database) as h:
        source = h.review.model_copy(update={"findings": (finding(kind="advisory"),)})
        duplicate = source.model_copy(
            update={
                "id": new_record_id(),
                "findings": (source.findings[0].model_copy(update={"id": new_record_id()}),),
            }
        )
        assert duplicate.id != source.id
        assert duplicate.aggregate_digest != source.aggregate_digest
        assert duplicate.request_digest == source.request_digest
        # An independent child cannot reference a parent that is not committed.
        async with h.factory() as parent:
            await insert_review(parent, source)
            async with h.factory() as child:
                assert (
                    await child.scalar(
                        text("SELECT count(*) FROM public.reviews WHERE id=:id"), {"id": source.id}
                    )
                    == 0
                )
                with pytest.raises(DBAPIError, match="fk_review_findings_review_id_reviews"):
                    await child.execute(
                        insert(ReviewFinding).values(
                            **finding(kind="advisory").model_dump(),
                            review_id=source.id,
                            item_order=1,
                        )
                    )
            assert (
                await parent.scalar(
                    text("SELECT count(*) FROM public.reviews WHERE id=:id"), {"id": source.id}
                )
                == 1
            )
            await parent.rollback()
        key = new_record_id()
        ready = asyncio.Future()

        async def later_delivery():
            async with h.factory() as second:
                ready.set_result(await second.scalar(text("SELECT pg_backend_pid()")))
                inserted = await second.scalar(
                    pg_insert(ReviewDecisionRequest)
                    .values(
                        id=new_record_id(),
                        operation_id=new_record_id(),
                        project_id=str(duplicate.project_id),
                        reviewer_id=str(duplicate.reviewer_id),
                        idempotency_key=key,
                        review_id=duplicate.id,
                        request_digest=duplicate.request_digest,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["project_id", "reviewer_id", "idempotency_key"]
                    )
                    .returning(ReviewDecisionRequest.review_id)
                )
                assert inserted is None
                row = (
                    await second.execute(
                        text("""
                    SELECT review_id,request_digest FROM public.review_decision_requests
                    WHERE project_id=:project AND reviewer_id=:reviewer AND idempotency_key=:key
                """),
                        {
                            "project": duplicate.project_id,
                            "reviewer": duplicate.reviewer_id,
                            "key": key,
                        },
                    )
                ).one()
                assert row.review_id == source.id
                assert row.request_digest == duplicate.request_digest
                assert (
                    row.request_digest
                    != duplicate.model_copy(update={"summary": "Changed content"}).request_digest
                )
                await second.commit()
                return row.review_id

        async with h.factory() as first:
            # Request first is valid only because the exact source arrives in this transaction.
            await first.execute(
                insert(ReviewDecisionRequest).values(
                    id=new_record_id(),
                    operation_id=new_record_id(),
                    project_id=str(source.project_id),
                    reviewer_id=str(source.reviewer_id),
                    idempotency_key=key,
                    review_id=source.id,
                    request_digest=source.request_digest,
                )
            )
            task = asyncio.create_task(later_delivery())
            try:
                await wait_for_blocker(h.factory, await ready)
                await insert_review(first, source, include_request=False)
                await first.commit()
                assert await asyncio.wait_for(task, 10) == source.id
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        async with h.factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM public.reviews")) == 1
            assert await session.scalar(text("SELECT count(*) FROM public.review_findings")) == 1


@pytest.mark.asyncio
async def test_finding_carry_forward(tmp_path, clean_postgres_database):
    from app.core.identifiers import new_record_id
    from app.modules.reviews.decision.schemas import FindingResolutionInput
    from sqlalchemy.exc import DBAPIError
    from tests.reviews.decision.support import successor_source

    async with review_source(tmp_path, clean_postgres_database) as h:
        first = h.review.model_copy(
            update={
                "decision": "needs_revision",
                "findings": tuple(finding(label=f"Issue {i}") for i in range(100)),
            }
        )
        async with h.factory() as session:
            await insert_review(session, first)
            await session.commit()
        next_h = await successor_source(h)
        unresolved = tuple(
            FindingResolutionInput(
                id=new_record_id(),
                finding_id=f.id,
                result="unresolved",
                rationale="The requested correction remains incomplete.",
            )
            for f in first.findings
        )
        next_review = next_h.review.model_copy(
            update={
                "decision": "needs_revision",
                "predecessor_review_id": first.id,
                "resolutions": unresolved,
            }
        )
        for bad, message in (
            (
                next_review.model_copy(update={"resolutions": unresolved[:-1]}),
                "review source finding ancestry or completeness mismatch",
            ),
            (
                next_review.model_copy(update={"decision": "accept"}),
                "review source blocking findings incompatible with decision",
            ),
            (
                next_review.model_copy(update={"findings": (finding(),)}),
                "review source blocking findings incompatible with decision",
            ),
        ):
            async with h.factory() as session:
                with pytest.raises(DBAPIError, match=message):
                    await insert_review(session, bad)
                    await session.commit()
        # Inherited-only needs_revision needs no duplicate new finding.
        async with h.factory() as session:
            await insert_review(session, next_review)
            await session.commit()
        third_h = await successor_source(next_h)
        # Close 99 findings; exactly one unresolved finding remains for another round.
        results = tuple(
            r.model_copy(
                update={
                    "id": new_record_id(),
                    "result": (
                        "unresolved" if i == 99 else "resolved" if i % 2 else "not_applicable"
                    ),
                }
            )
            for i, r in enumerate(unresolved)
        )
        third = third_h.review.model_copy(
            update={
                "decision": "needs_revision",
                "predecessor_review_id": next_review.id,
                "resolutions": results,
            }
        )
        async with h.factory() as session:
            await insert_review(session, third)
            await session.commit()
        final_h = await successor_source(third_h)
        last = final_h.review.model_copy(
            update={
                "predecessor_review_id": third.id,
                "resolutions": (
                    results[-1].model_copy(update={"id": new_record_id(), "result": "resolved"}),
                ),
            }
        )
        reopened = last.model_copy(
            update={
                "resolutions": (
                    *last.resolutions,
                    results[0].model_copy(update={"id": new_record_id(), "result": "unresolved"}),
                )
            }
        )
        async with h.factory() as session:
            with pytest.raises(
                DBAPIError, match="review source finding ancestry or completeness mismatch"
            ):
                await insert_review(session, reopened)
                await session.commit()
        async with h.factory() as session:
            await insert_review(session, last)
            await session.commit()
            assert (
                await session.scalar(
                    text("SELECT public.review_source_payload(:id,false)"), {"id": last.id}
                )
                == last.semantic_payload()
            )


@pytest.mark.asyncio
async def test_first_review_after_checker_only_correction(tmp_path, clean_postgres_database):
    from tests.reviews.decision.support import successor_source

    async with review_source(tmp_path, clean_postgres_database) as h:
        successor = await successor_source(h)
        assert successor.review.submission_version > h.review.submission_version
        assert successor.review.predecessor_review_id is None
        async with h.factory() as session:
            await insert_review(session, successor.review)
            await session.commit()
            assert await session.scalar(text("SELECT count(*) FROM public.reviews")) == 1


@pytest.mark.asyncio
async def test_self_review_guard_is_independent(tmp_path, clean_postgres_database, monkeypatch):
    from sqlalchemy.exc import DBAPIError
    from tests.reviews.packet import support as packet_support

    async def contributor_as_reviewer(session, *, label):
        return str(await session.scalar(text("SELECT contributor_id FROM public.submissions")))

    monkeypatch.setattr(packet_support, "_human_actor", contributor_as_reviewer)
    async with review_source(tmp_path, clean_postgres_database) as h:
        await assert_rejected(h, h.review, "review source canonical ownership mismatch")
        async with h.factory() as session:
            definition = await session.scalar(
                text(
                    "SELECT pg_get_functiondef('public.validate_review_source(uuid)'::regprocedure)"
                )
            )
            predicate = "AND r.reviewer_id<>s.contributor_id"
            assert definition.count(predicate) == 1
            await session.execute(text(definition.replace(predicate, "")))
            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                with pytest.raises(DBAPIError, match="review source canonical ownership mismatch"):
                    await insert_review(session, h.review)
                    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            await session.rollback()


@pytest.mark.asyncio
async def test_human_required_guard_is_reached(tmp_path, clean_postgres_database):
    from sqlalchemy.exc import DBAPIError

    async with review_source(tmp_path, clean_postgres_database) as h:
        async with h.factory() as session:
            definition = await session.scalar(
                text(
                    "SELECT pg_get_functiondef('public.validate_review_source(uuid)'::regprocedure)"
                )
            )
            predicate = "AND policy.human_review_required IS TRUE"
            assert definition.count(predicate) == 1
            await session.execute(
                text(definition.replace(predicate, "AND policy.human_review_required IS FALSE"))
            )
            with pytest.raises(DBAPIError, match="review source canonical ownership mismatch"):
                await insert_review(session, h.review)
                await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            await session.rollback()
        async with h.factory() as session:
            await insert_review(session, h.review)
            await session.commit()
