"""Real PostgreSQL custody and index eligibility for ephemeral export membership."""

import json
from datetime import timedelta
from uuid import uuid4

import asyncpg
import pytest
from sqlalchemy.dialects.postgresql import ARRAY

from app.core.identifiers import new_record_id
from app.modules.contributions.records.models import ContributionExportSnapshot, ContributionRecord


pytestmark = pytest.mark.postgres_schema_contract


async def test_snapshot_storage_bounds_model_parity_and_immutable_membership(isolated_database_env):
    connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
    actor, link, snapshot = new_record_id(), new_record_id(), new_record_id()
    digest = "sha256:" + "a" * 64
    members = [new_record_id(), new_record_id()]
    insert = """
        INSERT INTO public.contribution_export_snapshots
          (id,actor_profile_id,allocation_slot,query_digest,member_ids,created_at,expires_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7)
    """
    try:
        async with connection.transaction():
            await connection.execute("""
                INSERT INTO public.actor_profiles
                  (id,actor_kind,status,provisioning_method,created_by)
                VALUES ($1,'human','active','automatic_first_access','snapshot-migration-test')
            """, actor)
            await connection.execute("""
                INSERT INTO public.actor_identity_links
                  (id,actor_profile_id,issuer,subject,subject_kind,status,linked_by,last_verified_at)
                VALUES ($1,$2,'https://identity.flowresearch.tech',$3,'human','active',
                        'snapshot-migration-test',clock_timestamp())
            """, link, actor, str(actor))
        now = await connection.fetchval("SELECT clock_timestamp()")
        expiry = now + timedelta(hours=1)
        await connection.execute(insert, snapshot, actor, 1, digest, members, now, expiry)
        stored = await connection.fetchrow(
            "SELECT * FROM public.contribution_export_snapshots WHERE id=$1", snapshot,
        )
        assert stored["member_ids"] == members
        assert stored["actor_profile_id"] == actor
        assert stored["created_at"] == now and stored["expires_at"] == expiry
        assert isinstance(ContributionExportSnapshot.__table__.c.member_ids.type, ARRAY)
        assert {index.name for index in ContributionExportSnapshot.__table__.indexes} == {
            "ix_contribution_export_snapshots_expiry",
        }
        assert {index.name for index in ContributionRecord.__table__.indexes} >= {
            "ix_contribution_records_project_recorded",
            "ix_contribution_records_contributor_recorded",
        }

        invalid = (
            (dict(id=uuid4()), "ck_contribution_export_snapshots_id_uuid7"),
            (dict(id=new_record_id(), allocation_slot=0), "ck_contribution_export_snapshots_allocation_slot"),
            (dict(id=new_record_id(), query_digest="bad"), "ck_contribution_export_snapshots_query_digest"),
            (dict(id=new_record_id(), member_ids=[]), "ck_contribution_export_snapshots_members_shape"),
            (dict(id=new_record_id(), member_ids=[members[0], None]), "ck_contribution_export_snapshots_members_shape"),
            (dict(id=new_record_id(), expires_at=expiry - timedelta(seconds=1)),
             "ck_contribution_export_snapshots_expiry"),
        )
        for changes, constraint in invalid:
            values = dict(id=new_record_id(), actor_profile_id=actor, allocation_slot=2,
                          query_digest=digest, member_ids=members, created_at=now,
                          expires_at=expiry) | changes
            with pytest.raises(asyncpg.CheckViolationError) as failure:
                await connection.execute(insert, *(values[key] for key in (
                    "id", "actor_profile_id", "allocation_slot", "query_digest",
                    "member_ids", "created_at", "expires_at",
                )))
            assert failure.value.constraint_name == constraint

        with pytest.raises(asyncpg.UniqueViolationError) as occupied:
            await connection.execute(insert, new_record_id(), actor, 1, digest,
                                     members, now, expiry)
        assert occupied.value.constraint_name == "uq_contribution_export_snapshots_actor_slot"
        with pytest.raises(asyncpg.CheckViolationError, match="snapshot is immutable"):
            await connection.execute(
                "UPDATE public.contribution_export_snapshots SET member_ids=$1 WHERE id=$2",
                list(reversed(members)), snapshot,
            )
        assert await connection.fetchval(
            "SELECT member_ids FROM public.contribution_export_snapshots WHERE id=$1", snapshot,
        ) == members

        too_many = [new_record_id() for _ in range(100_001)]
        await connection.execute(insert, new_record_id(), actor, 2, digest,
                                 too_many[:100_000], now, expiry)
        assert await connection.fetchval("""
            SELECT cardinality(member_ids) FROM public.contribution_export_snapshots
            WHERE actor_profile_id=$1 AND allocation_slot=2
        """, actor) == 100_000
        with pytest.raises(asyncpg.CheckViolationError) as oversized:
            await connection.execute(insert, new_record_id(), actor, 3, digest,
                                     too_many, now, expiry)
        assert oversized.value.constraint_name == "ck_contribution_export_snapshots_members_shape"
        assert await connection.fetchval(
            "SELECT count(*) FROM public.contribution_export_snapshots WHERE actor_profile_id=$1", actor,
        ) == 2
    finally:
        await connection.close()


async def test_snapshot_and_contribution_selection_indexes_are_usable(isolated_database_env):
    """Forced index plans prove eligibility, without claiming production planner choice."""
    connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
    try:
        definitions = {row["indexname"]: row["indexdef"] for row in await connection.fetch("""
            SELECT indexname,indexdef FROM pg_indexes
            WHERE schemaname='public' AND tablename IN
              ('contribution_export_snapshots','contribution_records')
        """)}
        assert "(expires_at, id)" in definitions["ix_contribution_export_snapshots_expiry"]
        assert "(project_id, created_at, id)" in definitions["ix_contribution_records_project_recorded"]
        assert "(contributor_id, created_at, id)" in definitions["ix_contribution_records_contributor_recorded"]
        actor = new_record_id()
        async with connection.transaction():
            await connection.execute("SET LOCAL enable_seqscan=off")
            now = await connection.fetchval("SELECT clock_timestamp()")
            statements = (
                ("ix_contribution_export_snapshots_expiry", """
                    SELECT id FROM public.contribution_export_snapshots
                    WHERE expires_at <= $1 ORDER BY expires_at,id LIMIT 25
                    FOR UPDATE SKIP LOCKED
                """, now),
                ("ix_contribution_records_project_recorded", """
                    SELECT id FROM public.contribution_records WHERE project_id=$1
                    ORDER BY created_at,id LIMIT 100001
                """, actor),
                ("ix_contribution_records_contributor_recorded", """
                    SELECT id FROM public.contribution_records WHERE contributor_id=$1
                    ORDER BY created_at,id LIMIT 100001
                """, actor),
            )
            for name, query, argument in statements:
                raw = await connection.fetchval("EXPLAIN (FORMAT JSON) " + query, argument)
                plan = json.loads(raw) if isinstance(raw, str) else raw
                assert name in json.dumps(plan), plan
    finally:
        await connection.close()
