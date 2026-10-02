"""Observable packet persistence, replay and caller transaction guarantees."""

import pytest
from sqlalchemy import text

from app.core.hashing import canonical_json_hash
from app.core.identifiers import new_record_id
from app.modules.reviews.packet.repository import ReviewPacketRepository
from app.modules.reviews.packet.schemas import ReviewPacketConflict
from tests.reviews.packet.support import packet_source


@pytest.mark.asyncio
async def test_packet_matches_canonical_owners_and_digest(tmp_path, clean_postgres_database):
    async with packet_source(tmp_path, clean_postgres_database) as h:
        async with h.factory() as session:
            repository = ReviewPacketRepository(session)
            stored = await repository.store(h.lease_id, h.membership)
            await session.commit()
            assert set(stored.model_dump()) == {
                "packet_manifest_id",
                "review_lease_id",
                "review_queue_entry_id",
                "packet_manifest_generation",
                "packet_manifest_digest",
                "created_at",
                "membership",
            }
            assert stored.membership == h.membership
            assert stored.packet_manifest_digest == canonical_json_hash(
                h.membership.model_dump(mode="json")
            )
            assert stored.packet_manifest_generation == 1
            assert stored.review_queue_entry_id == h.queue_id
            assert stored.review_lease_id == h.lease_id
            assert await repository.read(h.membership.request.project_id, h.lease_id) == stored
            assert await repository.store(h.lease_id, h.membership) == stored
            changed = h.membership.model_copy(
                update={
                    "submission": h.membership.submission.model_copy(
                        update={"binding_id": new_record_id()}
                    )
                }
            )
            with pytest.raises(ReviewPacketConflict):
                await repository.store(h.lease_id, changed)
            assert (
                await session.scalar(text("SELECT count(*) FROM public.review_packet_manifests"))
                == 1
            )
            assert await session.scalar(
                text("SELECT count(*) FROM public.review_packet_guide_items")
            ) == len(h.membership.guide_documents)


@pytest.mark.asyncio
async def test_packet_read_conceals_foreign_project(tmp_path, clean_postgres_database):
    async with packet_source(tmp_path, clean_postgres_database) as h:
        async with h.factory() as session:
            await ReviewPacketRepository(session).store(h.lease_id, h.membership)
            await session.commit()
        async with h.factory() as session:
            assert await ReviewPacketRepository(session).read(new_record_id(), h.lease_id) is None


@pytest.mark.asyncio
async def test_packet_caller_rollback(tmp_path, clean_postgres_database):
    async with packet_source(tmp_path, clean_postgres_database) as h:
        async with h.factory() as session:
            await ReviewPacketRepository(session).store(h.lease_id, h.membership)
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


async def wait_for_blocker(factory, pid):
    import asyncio

    async def observe():
        async with factory() as session:
            while not await session.scalar(
                text("SELECT cardinality(pg_blocking_pids(:pid))>0"), {"pid": pid}
            ):
                await asyncio.sleep(0.01)

    await asyncio.wait_for(observe(), 10)


@pytest.mark.asyncio
async def test_packet_same_lease_concurrency(tmp_path, clean_postgres_database):
    import asyncio

    async with packet_source(tmp_path, clean_postgres_database) as h:
        for conflicting in (False, True):
            ready = asyncio.Future()

            async def second():
                async with h.factory() as session:
                    ready.set_result(await session.scalar(text("SELECT pg_backend_pid()")))
                    membership = h.membership
                    if conflicting:
                        membership = membership.model_copy(
                            update={
                                "submission": membership.submission.model_copy(
                                    update={"binding_id": new_record_id()}
                                )
                            }
                        )
                    result = await ReviewPacketRepository(session).store(h.lease_id, membership)
                    await session.commit()
                    return result

            async with h.factory() as first:
                original = await ReviewPacketRepository(first).store(h.lease_id, h.membership)
                task = asyncio.create_task(second())
                try:
                    await wait_for_blocker(h.factory, await ready)
                    await first.commit()
                    if conflicting:
                        with pytest.raises(ReviewPacketConflict):
                            await asyncio.wait_for(task, 10)
                    else:
                        assert await asyncio.wait_for(task, 10) == original
                finally:
                    if not task.done():
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
        async with h.factory() as session:
            assert (
                await session.scalar(text("SELECT count(*) FROM public.review_packet_manifests"))
                == 1
            )

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
            assert await ReviewPacketRepository(session).store(h.lease_id, h.membership) == original
            await session.commit()


@pytest.mark.asyncio
async def test_packet_creation_serializes_with_lease_closure(tmp_path, clean_postgres_database):
    import asyncio
    from app.modules.artifacts.api.review_packet import ReviewPacketMembershipUnavailable

    async with packet_source(tmp_path, clean_postgres_database) as h:
        ready = asyncio.Future()

        async def store():
            async with h.factory() as session:
                ready.set_result(await session.scalar(text("SELECT pg_backend_pid()")))
                return await ReviewPacketRepository(session).store(h.lease_id, h.membership)

        async with h.factory() as first:
            await first.execute(
                text(
                    "UPDATE public.review_leases SET status='released',close_reason='manual_release',closed_at=clock_timestamp() WHERE id=:id"
                ),
                {"id": h.lease_id},
            )
            await first.execute(
                text(
                    "UPDATE public.review_queue_entries SET queue_state='pending',active_lease_id=NULL WHERE id=:id"
                ),
                {"id": h.queue_id},
            )
            task = asyncio.create_task(store())
            try:
                await wait_for_blocker(h.factory, await ready)
                await first.commit()
                with pytest.raises(ReviewPacketMembershipUnavailable):
                    await asyncio.wait_for(task, 10)
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
        async with h.factory() as session:
            assert (
                await session.scalar(text("SELECT count(*) FROM public.review_packet_manifests"))
                == 0
            )


@pytest.mark.asyncio
async def test_packet_retains_superseded_guide_lineage(tmp_path, clean_postgres_database):
    from uuid import UUID
    from sqlalchemy import select
    from app.modules.actors.models import ActorIdentityLink
    from app.modules.authorization.models import AdminRoleGrant
    from app.modules.authorization.api import ActorIdentityFacts, ActorKind
    from app.modules.projects.models import ProjectGuide
    from app.modules.projects.guide_activation.custody import load_guide_activation
    from tests.projects.guide_activation.test_successor import successor_command
    from tests.projects.guide_activation.pg_support import publish_policy
    from tests.authorization.guide_activation.pg_support import activate

    async with packet_source(tmp_path, clean_postgres_database) as h:
        async with h.factory() as session:
            guide = await session.get(ProjectGuide, str(h.membership.request.guide_id))
            first = await load_guide_activation(session, guide)
            grant, link = (
                await session.execute(
                    select(AdminRoleGrant, ActorIdentityLink)
                    .join(
                        ActorIdentityLink,
                        ActorIdentityLink.actor_profile_id
                        == AdminRoleGrant.target_actor_profile_id,
                    )
                    .where(
                        AdminRoleGrant.scope_project_id == str(h.membership.request.project_id),
                        AdminRoleGrant.role == "project_manager",
                        AdminRoleGrant.status == "active",
                        ActorIdentityLink.status == "active",
                    )
                    .order_by(AdminRoleGrant.id, ActorIdentityLink.id)
                    .limit(1)
                )
            ).one()
            actor = ActorIdentityFacts(
                UUID(grant.target_actor_profile_id), UUID(link.id), ActorKind.HUMAN
            )
        _, policy = await publish_policy(h.factory, h.membership.request.project_id)
        command = await successor_command(h.factory, first.command, actor, grant.id, policy)
        command = command.model_copy(
            update={
                "expected_previous_active_guide_id": h.membership.request.guide_id,
                "expected_previous_active_guide_generation": first.activation_generation,
            }
        )
        successor = await activate(h.factory, actor, command)
        assert successor.command.target.proposal.guide_id != h.membership.request.guide_id
        async with h.factory() as session:
            guide = await session.get(ProjectGuide, str(h.membership.request.guide_id))
            assert guide.status == "superseded"
            # First creation must resolve the historical guide, not only replay a packet.
            original = await ReviewPacketRepository(session).store(h.lease_id, h.membership)
            await session.commit()
            assert original.membership == h.membership
            assert original.packet_manifest_digest == canonical_json_hash(
                h.membership.model_dump(mode="json")
            )
            assert (
                await ReviewPacketRepository(session).read(
                    h.membership.request.project_id, h.lease_id
                )
                == original
            )
            assert await ReviewPacketRepository(session).store(h.lease_id, h.membership) == original
            await session.commit()


@pytest.mark.asyncio
async def test_exact_packet_replay_survives_expiry_then_closure(tmp_path, clean_postgres_database):
    from datetime import timedelta
    from tests.reviews.packet.support import wait_for_lease_expiry

    async with packet_source(
        tmp_path, clean_postgres_database, lease_duration=timedelta(seconds=5)
    ) as h:
        async with h.factory() as session:
            stored = await ReviewPacketRepository(session).store(h.lease_id, h.membership)
            await session.commit()
            await wait_for_lease_expiry(session, h.lease_id)
            assert await ReviewPacketRepository(session).store(h.lease_id, h.membership) == stored
            await session.execute(
                text(
                    "UPDATE public.review_leases SET status='expired',close_reason='lease_expired',closed_at=clock_timestamp() WHERE id=:id"
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
            assert await ReviewPacketRepository(session).store(h.lease_id, h.membership) == stored
            await session.commit()
