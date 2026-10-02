"""Direct PostgreSQL custody proofs independent of the packet repository."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.reviews.packet.support import packet_source, raw_insert


async def valid_control(h):
    async with h.factory() as session:
        await raw_insert(session, h)
        await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        await session.rollback()


@pytest.mark.asyncio
async def test_packet_rejects_null_source_fields(tmp_path, clean_postgres_database):
    async with packet_source(tmp_path, clean_postgres_database) as h:
        await valid_control(h)
        fields = tuple(type(h.membership.request).model_fields) + (
            "review_lease_id",
            "review_queue_entry_id",
            "packet_manifest_generation",
            "packet_manifest_digest",
            "submission_binding_id",
            "submission_logical_role",
            "submission_media_type",
        )
        for field in fields:
            async with h.factory() as session:
                with pytest.raises(DBAPIError):
                    await raw_insert(session, h, header={field: None})
                    await session.commit()
                await session.rollback()


@pytest.mark.asyncio
async def test_packet_creation_time_is_database_owned(tmp_path, clean_postgres_database):
    async with packet_source(tmp_path, clean_postgres_database) as h:
        for supplied in (None, datetime(2000, 1, 1, tzinfo=UTC), datetime(2100, 1, 1, tzinfo=UTC)):
            async with h.factory() as session:
                start = await session.scalar(text("SELECT clock_timestamp()"))
                packet_id = await raw_insert(session, h, header={"created_at": supplied})
                await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                stored = await session.scalar(
                    text("SELECT created_at FROM public.review_packet_manifests WHERE id=:id"),
                    {"id": packet_id},
                )
                end = await session.scalar(text("SELECT clock_timestamp()"))
                assert start <= stored <= end
                assert stored != supplied
                await session.rollback()


@pytest.mark.asyncio
async def test_packet_requires_complete_canonical_guide_set(tmp_path, clean_postgres_database):
    async with packet_source(tmp_path, clean_postgres_database) as h:
        await valid_control(h)
        members = list(h.membership.guide_documents)
        assert len(members) == 2
        variants = [
            [],
            members[:1],
            list(reversed(members)),
            [
                members[0].model_copy(update={"ingest_id": members[1].ingest_id}),
                members[1].model_copy(update={"ingest_id": members[0].ingest_id}),
            ],
            [members[0].model_copy(update={"item_order": 2}), members[1]],
            [
                members[0].model_copy(
                    update={
                        "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    }
                ),
                members[1],
            ],
        ]
        # Input order alone is irrelevant to normalized storage; canonical read restores order.
        variants.pop(2)
        for changed in variants:
            async with h.factory() as session:
                with pytest.raises(DBAPIError, match="canonical guide membership"):
                    await raw_insert(session, h, members=changed)
                    await session.commit()
                await session.rollback()


@pytest.mark.asyncio
async def test_packet_deferred_failure_rolls_back(tmp_path, clean_postgres_database):
    async with packet_source(tmp_path, clean_postgres_database) as h:
        await valid_control(h)
        async with h.factory() as session:
            await raw_insert(session, h, header={"packet_manifest_digest": "sha256:" + "0" * 64})
            with pytest.raises(DBAPIError, match="semantic digest mismatch"):
                await session.commit()
            await session.rollback()
        async with h.factory() as session:
            assert (
                await session.scalar(text("SELECT count(*) FROM public.review_packet_manifests"))
                == 0
            )
            assert (
                await session.scalar(text("SELECT count(*) FROM public.review_packet_guide_items"))
                == 0
            )


@pytest.mark.asyncio
async def test_packet_and_ingest_facts_are_immutable(tmp_path, clean_postgres_database):
    async with packet_source(tmp_path, clean_postgres_database) as h:
        async with h.factory() as session:
            packet_id = await raw_insert(session, h)
            await session.commit()
        for table, column in (
            ("review_packet_manifests", "packet_manifest_digest"),
            ("review_packet_guide_items", "media_type"),
            ("guide_source_artifact_ingests", "media_type"),
        ):
            for statement in (
                f"UPDATE public.{table} SET {column}={column}",
                f"DELETE FROM public.{table}",
                f"TRUNCATE public.{table} CASCADE",
            ):
                async with h.factory() as session:
                    with pytest.raises(DBAPIError, match="immutable"):
                        await session.execute(text(statement))
                    await session.rollback()
        async with h.factory() as session:
            assert (
                await session.scalar(text("SELECT id FROM public.review_packet_manifests"))
                == packet_id
            )
            assert await session.scalar(
                text("SELECT count(*) FROM public.review_packet_guide_items")
            ) == len(h.membership.guide_documents)


@pytest.mark.asyncio
async def test_packet_requires_active_exact_lease(tmp_path, clean_postgres_database):
    async with packet_source(tmp_path, clean_postgres_database) as h:
        await valid_control(h)
        async with h.factory() as session:
            await session.execute(
                text(
                    "UPDATE public.review_leases SET status='released',close_reason='manual_release',closed_at=clock_timestamp() WHERE id=:id"
                ),
                {"id": h.lease_id},
            )
            await session.execute(
                text(
                    "UPDATE public.review_queue_entries SET queue_state='pending',active_lease_id=NULL WHERE id=:id"
                ),
                {"id": h.queue_id},
            )
            await session.commit()
        async with h.factory() as session:
            with pytest.raises(DBAPIError, match="requires exact active lease"):
                await raw_insert(session, h)
            await session.rollback()

        from app.core.identifiers import new_record_id
        from app.modules.reviews.models import ReviewLease, ReviewQueueEntry
        from app.modules.reviews.repository import ReviewQueueRepository
        from app.modules.reviews.schemas import ReviewLeaseInput

        async with h.factory() as session:
            prior = await session.get(ReviewLease, h.lease_id)
            successor = await ReviewQueueRepository(session).add_lease(
                ReviewLeaseInput(
                    id=new_record_id(),
                    review_queue_entry_id=h.queue_id,
                    project_id=prior.project_id,
                    task_id=prior.task_id,
                    submission_id=prior.submission_id,
                    submission_version=prior.submission_version,
                    reviewer_id=prior.reviewer_id,
                    reviewer_contribution_policy_version_id=prior.reviewer_contribution_policy_version_id,
                    attempt_generation=2,
                    expires_at=prior.expires_at,
                )
            )
            queue = await session.get(ReviewQueueEntry, h.queue_id)
            queue.queue_state = "leased"
            successor_id = successor.id
            queue.active_lease_id = successor_id
            await session.commit()
            with pytest.raises(DBAPIError, match="requires exact active lease"):
                await raw_insert(session, h)
            await session.rollback()
            packet_id = await raw_insert(
                session,
                h,
                header={"review_lease_id": successor_id, "packet_manifest_generation": 2},
            )
            await session.commit()
            assert (
                await session.scalar(
                    text(
                        "SELECT packet_manifest_generation FROM public.review_packet_manifests WHERE id=:id"
                    ),
                    {"id": packet_id},
                )
                == 2
            )


@pytest.mark.asyncio
async def test_packet_shadow_tables_cannot_change_custody(tmp_path, clean_postgres_database):
    async with packet_source(tmp_path, clean_postgres_database) as h:
        await valid_control(h)
        async with h.factory() as session:
            for name in (
                "review_packet_manifests",
                "review_packet_guide_items",
                "submissions",
                "checker_runs",
                "guide_source_artifact_ingests",
                "artifact_put_attempts",
                "review_leases",
                "review_queue_entries",
            ):
                await session.execute(
                    text(f"CREATE TEMP TABLE {name} (LIKE public.{name} INCLUDING ALL)")
                )
            with pytest.raises(DBAPIError, match="canonical guide membership"):
                await raw_insert(session, h, members=[])
                await session.commit()
            await session.rollback()


@pytest.mark.asyncio
async def test_packet_rejects_numeric_version_and_generation(tmp_path, clean_postgres_database):
    async with packet_source(tmp_path, clean_postgres_database) as h:
        await valid_control(h)
        for field in ("submission_version", "packet_manifest_generation", "setup_generation"):
            async with h.factory() as session:
                with pytest.raises(DBAPIError):
                    await raw_insert(session, h, header={field: 999})
                    await session.commit()
                await session.rollback()


@pytest.mark.asyncio
async def test_packet_rejects_coherent_owner_substitutions(tmp_path, clean_postgres_database):
    async with packet_source(tmp_path / "first", clean_postgres_database) as h:
        async with packet_source(
            tmp_path / "foreign",
            clean_postgres_database,
            storage_settings=h.settings,
            provision_services=False,
        ) as foreign:
            await valid_control(h)
            await valid_control(foreign)
            foreign_header = foreign.membership.request.model_dump()
            for field in (
                "project_id",
                "task_id",
                "submission_id",
                "checker_run_id",
                "result_id",
                "guide_id",
                "source_snapshot_id",
                "project_setup_run_id",
            ):
                assert getattr(h.membership.request, field) != foreign_header[field]
                async with h.factory() as session:
                    with pytest.raises(DBAPIError):
                        await raw_insert(session, h, header={field: foreign_header[field]})
                        await session.commit()
                    await session.rollback()
            for header, members in (
                ({"submission_binding_id": foreign.membership.submission.binding_id}, None),
                ({}, foreign.membership.guide_documents),
                (
                    {},
                    (
                        *h.membership.guide_documents,
                        foreign.membership.guide_documents[0].model_copy(update={"item_order": 10}),
                    ),
                ),
            ):
                async with h.factory() as session:
                    with pytest.raises(DBAPIError):
                        await raw_insert(session, h, header=header, members=members)
                        await session.commit()
                    await session.rollback()
            # Stored foreign rows, not nonexistent UUIDs, exercise concealed reads.
            from app.modules.reviews.packet.repository import ReviewPacketRepository

            async with h.factory() as session:
                await raw_insert(session, foreign)
                await session.commit()
                assert (
                    await ReviewPacketRepository(session).read(
                        h.membership.request.project_id, foreign.lease_id
                    )
                    is None
                )
            # A valid foreign member cannot be appended to an already committed packet.
            async with h.factory() as session:
                packet_id = await raw_insert(session, h)
                await session.commit()
                member = foreign.membership.guide_documents[0]
                await session.execute(
                    text("INSERT INTO public.review_packet_guide_items VALUES (:p,:s,:i,10,:r,:m)"),
                    {
                        "p": packet_id,
                        "s": member.source_item_id,
                        "i": member.ingest_id,
                        "r": member.logical_role,
                        "m": member.media_type,
                    },
                )
                with pytest.raises(DBAPIError, match="canonical guide membership"):
                    await session.commit()
                await session.rollback()


@pytest.mark.asyncio
async def test_packet_requires_committed_guide_upload(tmp_path, clean_postgres_database):
    async with packet_source(tmp_path, clean_postgres_database) as h:
        await valid_control(h)
        item = h.membership.guide_documents[0]
        # Change only mutable put custody, leaving the prepared ingest and activation intact.
        changes = (
            "receipt_id=NULL",
            "status='prepared',terminal_result_code=NULL,terminal_at=NULL,receipt_id=NULL,replica_id=NULL,execution_generation=0,next_run_at=NULL,executor_id=NULL,lease_expires_at=NULL",
            "request_digest='sha256:' || repeat('0',64)",
            "byte_count=byte_count+1",
            "sha256='sha256:' || repeat('0',64)",
            "media_type='application/zip'",
        )
        for assignment in changes:
            async with h.factory() as session:
                await session.execute(
                    text(
                        f"UPDATE public.artifact_put_attempts SET {assignment} WHERE guide_source_item_id=:id"
                    ),
                    {"id": item.source_item_id},
                )
                with pytest.raises(DBAPIError, match="canonical guide membership"):
                    await raw_insert(session, h)
                    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                await session.rollback()

        async with h.factory() as session:
            # A valid ZIP replica is still not this guide's original document.
            await session.execute(
                text(
                    "UPDATE public.artifact_put_attempts SET replica_id=:replica WHERE guide_source_item_id=:item"
                ),
                {"replica": h.material["replica_id"], "item": item.source_item_id},
            )
            with pytest.raises(DBAPIError, match="canonical guide membership"):
                await raw_insert(session, h)
                await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            await session.rollback()
            # Namespace identity is already enforced earlier by ART's singleton FK.
            with pytest.raises(DBAPIError, match="fk_artifact_put_attempts_namespace_fingerprint"):
                await session.execute(
                    text(
                        "UPDATE public.artifact_put_attempts SET namespace_fingerprint='sha256:' || repeat('0',64) WHERE guide_source_item_id=:id"
                    ),
                    {"id": item.source_item_id},
                )
            await session.rollback()


@pytest.mark.asyncio
async def test_packet_accepts_observed_confirmed_upload(tmp_path, clean_postgres_database):
    from sqlalchemy import select
    from app.core.identifiers import new_record_id
    from app.modules.artifacts.models import ArtifactPutAttempt, ArtifactPutObservationReceipt

    async with packet_source(tmp_path, clean_postgres_database) as h:
        async with h.factory() as session:
            put = await session.scalar(
                select(ArtifactPutAttempt).where(
                    ArtifactPutAttempt.guide_source_item_id
                    == str(h.membership.guide_documents[0].source_item_id)
                )
            )
            observation = ArtifactPutObservationReceipt(
                id=str(new_record_id()),
                put_attempt_id=put.id,
                execution_generation=put.execution_generation,
                outcome="observed_confirmed",
                expected_sha256=put.sha256,
                expected_byte_count=put.byte_count,
                observed_sha256=put.sha256,
                observed_byte_count=put.byte_count,
            )
            session.add(observation)
            put.receipt_id = None
            put.terminal_result_code = "document_stored_observed"
            await session.commit()
        await valid_control(h)
        for assignment in (
            "execution_generation=execution_generation+1",
            "byte_count=byte_count+1",
        ):
            async with h.factory() as session:
                await session.execute(
                    text(f"UPDATE public.artifact_put_attempts SET {assignment} WHERE id=:id"),
                    {"id": put.id},
                )
                with pytest.raises(DBAPIError, match="canonical guide membership"):
                    await raw_insert(session, h)
                    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
                await session.rollback()


async def assert_packet_rejected(session, h, *, message, header=None, members=None):
    with pytest.raises(DBAPIError, match=message):
        await raw_insert(session, h, header=header, members=members)
        await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.asyncio
async def test_packet_guard_removal_probes(tmp_path, clean_postgres_database):
    """Negative assertions fail after removing their exact validator rejection."""
    async with packet_source(tmp_path, clean_postgres_database) as h:
        await valid_control(h)
        for message, header, members in (
            (
                "review packet canonical guide membership mismatch",
                None,
                h.membership.guide_documents[:1],
            ),
            (
                "review packet semantic digest mismatch",
                {"packet_manifest_digest": "sha256:" + "0" * 64},
                None,
            ),
        ):
            async with h.factory() as session:
                await assert_packet_rejected(
                    session, h, message=message, header=header, members=members
                )
                await session.rollback()
                definition = await session.scalar(
                    text(
                        "SELECT pg_get_functiondef('public.validate_review_packet(uuid)'::regprocedure)"
                    )
                )
                target = f"RAISE EXCEPTION '{message}' USING ERRCODE='23514';"
                assert definition.count(target) == 1
                await session.execute(text(definition.replace(target, "NULL;")))
                with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                    await assert_packet_rejected(
                        session, h, message=message, header=header, members=members
                    )
                await session.rollback()
        async with h.factory() as session:
            from app.core.identifiers import new_record_id

            with pytest.raises(DBAPIError, match="review packet parent unavailable"):
                await session.execute(
                    text("SELECT public.validate_review_packet(:id)"), {"id": new_record_id()}
                )
            await session.rollback()
        for mode in ("receipt", "lease"):
            message = (
                "review packet canonical guide membership mismatch"
                if mode == "receipt"
                else "review packet requires exact active lease"
            )
            signature = (
                "public.validate_review_packet(uuid)"
                if mode == "receipt"
                else "public.guard_review_packet_creation()"
            )

            async def prepare(session):
                if mode == "receipt":
                    await session.execute(
                        text(
                            "UPDATE public.artifact_put_attempts SET receipt_id=NULL WHERE guide_source_item_id=:id"
                        ),
                        {"id": h.membership.guide_documents[0].source_item_id},
                    )
                else:
                    await session.execute(
                        text(
                            "UPDATE public.review_leases SET status='released',close_reason='manual_release',closed_at=clock_timestamp() WHERE id=:id"
                        ),
                        {"id": h.lease_id},
                    )
                    await session.execute(
                        text(
                            "UPDATE public.review_queue_entries SET queue_state='pending',active_lease_id=NULL WHERE id=:id"
                        ),
                        {"id": h.queue_id},
                    )

            async with h.factory() as session:
                await prepare(session)
                await assert_packet_rejected(session, h, message=message)
                await session.rollback()
                definition = await session.scalar(
                    text("SELECT pg_get_functiondef(CAST(:name AS regprocedure))"),
                    {"name": signature},
                )
                target = f"RAISE EXCEPTION '{message}' USING ERRCODE='23514';"
                assert definition.count(target) == 1
                await session.execute(text(definition.replace(target, "NULL;")))
                await prepare(session)
                with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                    await assert_packet_rejected(session, h, message=message)
                await session.rollback()
        # Source-fact mutation has its own independently reached assertion.
        async with h.factory() as session:
            statement = text(
                "UPDATE public.guide_source_artifact_ingests SET byte_count=byte_count+1 WHERE id=:id"
            )
            params = {"id": h.membership.guide_documents[0].ingest_id}
            with pytest.raises(DBAPIError, match="immutable"):
                await session.execute(statement, params)
            await session.rollback()
            await session.execute(
                text(
                    "DROP TRIGGER guide_source_artifact_ingests_immutable ON public.guide_source_artifact_ingests"
                )
            )
            with pytest.raises(pytest.fail.Exception, match="DID NOT RAISE"):
                with pytest.raises(DBAPIError, match="immutable"):
                    await session.execute(statement, params)
            await session.rollback()
