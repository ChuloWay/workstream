"""Bounded fixed-membership contribution export snapshots."""

from alembic import op


revision = "0040_contribution_export_page"
down_revision = "0039_false_guide_activation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE public.contribution_export_snapshots (
            id uuid PRIMARY KEY,
            actor_profile_id uuid NOT NULL REFERENCES public.actor_profiles(id) ON DELETE RESTRICT,
            allocation_slot smallint NOT NULL,
            query_digest varchar(71) NOT NULL,
            member_ids uuid[] NOT NULL,
            created_at timestamptz NOT NULL,
            expires_at timestamptz NOT NULL,
            CONSTRAINT ck_contribution_export_snapshots_id_uuid7 CHECK (
                (get_byte(uuid_send(id), 6) >> 4) = 7
                AND (get_byte(uuid_send(id), 8) & 192) = 128
            ),
            CONSTRAINT ck_contribution_export_snapshots_query_digest CHECK (
                query_digest ~ '^sha256:[0-9a-f]{64}$'
            ),
            CONSTRAINT ck_contribution_export_snapshots_allocation_slot CHECK (
                allocation_slot BETWEEN 1 AND 5
            ),
            CONSTRAINT ck_contribution_export_snapshots_members_shape CHECK (
                array_ndims(member_ids)=1 AND array_lower(member_ids,1)=1
                AND cardinality(member_ids) BETWEEN 2 AND 100000
                AND array_position(member_ids, NULL) IS NULL
            ),
            CONSTRAINT ck_contribution_export_snapshots_expiry CHECK (
                expires_at=created_at + interval '1 hour'
            ),
            CONSTRAINT uq_contribution_export_snapshots_actor_slot
                UNIQUE (actor_profile_id, allocation_slot)
        )
    """)
    op.execute("""
        CREATE INDEX ix_contribution_export_snapshots_expiry
        ON public.contribution_export_snapshots (expires_at, id)
    """)
    op.execute("""
        CREATE INDEX ix_contribution_records_project_recorded
        ON public.contribution_records (project_id, created_at, id)
    """)
    op.execute("""
        CREATE INDEX ix_contribution_records_contributor_recorded
        ON public.contribution_records (contributor_id, created_at, id)
    """)
    op.execute("""
        CREATE FUNCTION public.reject_contribution_export_snapshot_update()
        RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
        BEGIN
            RAISE EXCEPTION 'contribution export snapshot is immutable' USING ERRCODE='23514';
        END $$
    """)
    op.execute("""
        CREATE TRIGGER contribution_export_snapshot_immutable
        BEFORE UPDATE ON public.contribution_export_snapshots
        FOR EACH ROW EXECUTE FUNCTION public.reject_contribution_export_snapshot_update()
    """)


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
