"""Seed one disabled shared lifecycle controller; no authority or transition writer."""

from alembic import op
from sqlalchemy import text

from app.core.identifiers import new_record_id

revision = "0016_review_lifecycle_fence"
down_revision = "0015_contribution_awards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE public.joint_lifecycle_release_control (
    id UUID NOT NULL,
    singleton BOOLEAN NOT NULL,
    phase VARCHAR(16) NOT NULL,
    generation BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
    CONSTRAINT pk_joint_lifecycle_release_control PRIMARY KEY (id),
    CONSTRAINT ck_joint_lifecycle_release_control_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128),
    CONSTRAINT ck_joint_lifecycle_release_control_singleton_true CHECK (singleton),
    CONSTRAINT uq_joint_lifecycle_release_control_singleton UNIQUE (singleton),
    CONSTRAINT ck_joint_lifecycle_release_control_phase CHECK (phase in ('disabled','shadow','live','draining')),
    CONSTRAINT ck_joint_lifecycle_release_control_generation_nonnegative CHECK (generation >= 0),
    CONSTRAINT ck_joint_lifecycle_release_control_genesis_disabled CHECK (generation <> 0 or phase='disabled')
)
""")
    op.get_bind().execute(
        text("""
INSERT INTO public.joint_lifecycle_release_control(id,singleton,phase,generation)
VALUES (:id,true,'disabled',0)
"""),
        {"id": new_record_id()},
    )
    op.execute("""
CREATE FUNCTION public.guard_joint_lifecycle_genesis() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    RAISE EXCEPTION 'joint lifecycle genesis is immutable; authorized transitions unavailable'
        USING ERRCODE='23514';
END;
$$
""")
    op.execute("""
CREATE TRIGGER joint_lifecycle_genesis_immutable
BEFORE INSERT OR UPDATE OR DELETE ON public.joint_lifecycle_release_control
FOR EACH STATEMENT EXECUTE FUNCTION public.guard_joint_lifecycle_genesis()
""")
    op.execute("""
CREATE TRIGGER joint_lifecycle_genesis_no_truncate
BEFORE TRUNCATE ON public.joint_lifecycle_release_control
FOR EACH STATEMENT EXECUTE FUNCTION public.guard_joint_lifecycle_genesis();
""")


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
