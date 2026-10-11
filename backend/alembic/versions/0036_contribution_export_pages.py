"""Install private fixed-membership contribution export custody."""

from alembic import op

revision = "0036_contribution_export_pages"
down_revision = "0035_task_batch_transitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE INDEX ix_contribution_records_self_export
ON public.contribution_records (contributor_id, created_at, id)
""")
    op.execute("""
CREATE INDEX ix_contribution_records_project_export
ON public.contribution_records (project_id, created_at, id)
""")
    op.execute("""
CREATE TABLE public.contribution_export_memberships (
    id UUID NOT NULL,
    actor_profile_id UUID NOT NULL,
    audience VARCHAR(16) NOT NULL,
    project_id UUID,
    output_format VARCHAR(4) NOT NULL,
    page_size INTEGER NOT NULL,
    contribution_type VARCHAR(32),
    recorded_from TIMESTAMP WITH TIME ZONE,
    recorded_before TIMESTAMP WITH TIME ZONE,
    member_count INTEGER NOT NULL,
    sealed BOOLEAN NOT NULL,
    query_digest VARCHAR(71) NOT NULL,
    exported_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_contribution_export_memberships PRIMARY KEY (id),
    CONSTRAINT ck_contribution_export_memberships_id_uuid7
      CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7
        AND (get_byte(uuid_send(id), 8) & 192) = 128),
    CONSTRAINT ck_contribution_export_memberships_query_digest
      CHECK (query_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT ck_contribution_export_memberships_expiry
      CHECK (expires_at = exported_at + interval '15 minutes'),
    CONSTRAINT ck_contribution_export_memberships_member_count
      CHECK (member_count BETWEEN 0 AND 100000),
    CONSTRAINT ck_contribution_export_memberships_audience
      CHECK (audience IN ('self','project')
        AND (audience <> 'project' OR project_id IS NOT NULL)),
    CONSTRAINT ck_contribution_export_memberships_output_format
      CHECK (output_format IN ('json','csv')),
    CONSTRAINT ck_contribution_export_memberships_page_size
      CHECK (page_size BETWEEN 1 AND 1000),
    CONSTRAINT ck_contribution_export_memberships_contribution_type
      CHECK (contribution_type IS NULL
        OR contribution_type IN ('accepted_submission','completed_review')),
    CONSTRAINT ck_contribution_export_memberships_recorded_interval
      CHECK (recorded_from IS NULL OR recorded_before IS NULL
        OR recorded_from < recorded_before),
    CONSTRAINT fk_contribution_export_memberships_actor_profile_id_act_4609
      FOREIGN KEY(actor_profile_id) REFERENCES public.actor_profiles (id)
      ON DELETE RESTRICT,
    CONSTRAINT fk_contribution_export_memberships_project_id_projects
      FOREIGN KEY(project_id) REFERENCES public.projects (id)
      ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE INDEX ix_contribution_export_memberships_expires_at
ON public.contribution_export_memberships (expires_at)
""")
    op.execute("""
CREATE TABLE public.contribution_export_members (
    export_id UUID NOT NULL,
    contribution_id UUID NOT NULL,
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_contribution_export_members
      PRIMARY KEY (export_id, contribution_id),
    CONSTRAINT fk_contribution_export_members_export_id_contribution_e_3433
      FOREIGN KEY(export_id) REFERENCES public.contribution_export_memberships (id)
      ON DELETE CASCADE,
    CONSTRAINT fk_contribution_export_members_contribution_id_contribu_5e22
      FOREIGN KEY(contribution_id) REFERENCES public.contribution_records (id)
      ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE INDEX ix_contribution_export_members_order
ON public.contribution_export_members (export_id, recorded_at, contribution_id)
""")
    op.execute("""
CREATE FUNCTION public.guard_contribution_export_member() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
    export_row public.contribution_export_memberships%ROWTYPE;
    contribution_row public.contribution_records%ROWTYPE;
BEGIN
    SELECT * INTO export_row
      FROM public.contribution_export_memberships
      WHERE id=NEW.export_id FOR UPDATE;
    IF NOT FOUND OR export_row.sealed THEN
        RAISE EXCEPTION 'contribution export membership is not capturing'
          USING ERRCODE='23514';
    END IF;

    SELECT * INTO contribution_row
      FROM public.contribution_records WHERE id=NEW.contribution_id;
    IF NOT FOUND
      OR NEW.recorded_at IS DISTINCT FROM contribution_row.created_at
      OR (export_row.audience='self'
          AND contribution_row.contributor_id IS DISTINCT FROM export_row.actor_profile_id)
      OR (export_row.project_id IS NOT NULL
          AND contribution_row.project_id IS DISTINCT FROM export_row.project_id)
      OR (export_row.contribution_type IS NOT NULL
          AND contribution_row.contribution_type IS DISTINCT FROM export_row.contribution_type)
      OR (export_row.recorded_from IS NOT NULL
          AND contribution_row.created_at < export_row.recorded_from)
      OR (export_row.recorded_before IS NOT NULL
          AND contribution_row.created_at >= export_row.recorded_before)
    THEN
        RAISE EXCEPTION 'contribution export member does not match the sealed query'
          USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$
""")
    op.execute("""
CREATE TRIGGER contribution_export_member_custody
BEFORE INSERT ON public.contribution_export_members
FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_export_member()
""")
    op.execute("""
CREATE FUNCTION public.guard_contribution_export_membership_insert() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    IF NEW.sealed THEN
        RAISE EXCEPTION 'contribution export membership must begin unsealed'
          USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$
""")
    op.execute("""
CREATE TRIGGER contribution_export_membership_insert
BEFORE INSERT ON public.contribution_export_memberships
FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_export_membership_insert()
""")
    op.execute("""
CREATE FUNCTION public.guard_contribution_export_membership_update() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    IF OLD.sealed OR NOT NEW.sealed
      OR NEW.id IS DISTINCT FROM OLD.id
      OR NEW.actor_profile_id IS DISTINCT FROM OLD.actor_profile_id
      OR NEW.audience IS DISTINCT FROM OLD.audience
      OR NEW.project_id IS DISTINCT FROM OLD.project_id
      OR NEW.output_format IS DISTINCT FROM OLD.output_format
      OR NEW.page_size IS DISTINCT FROM OLD.page_size
      OR NEW.contribution_type IS DISTINCT FROM OLD.contribution_type
      OR NEW.recorded_from IS DISTINCT FROM OLD.recorded_from
      OR NEW.recorded_before IS DISTINCT FROM OLD.recorded_before
      OR NEW.member_count IS DISTINCT FROM OLD.member_count
      OR NEW.query_digest IS DISTINCT FROM OLD.query_digest
      OR NEW.exported_at IS DISTINCT FROM OLD.exported_at
      OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
    THEN
        RAISE EXCEPTION 'contribution export membership facts are immutable'
          USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$
""")
    op.execute("""
CREATE TRIGGER contribution_export_membership_update
BEFORE UPDATE ON public.contribution_export_memberships
FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_export_membership_update()
""")
    op.execute("""
CREATE FUNCTION public.guard_contribution_export_membership_delete() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    IF OLD.expires_at > pg_catalog.clock_timestamp() THEN
        RAISE EXCEPTION 'active contribution export membership cannot be deleted'
          USING ERRCODE='23514';
    END IF;
    RETURN OLD;
END $$
""")
    op.execute("""
CREATE TRIGGER contribution_export_membership_delete
BEFORE DELETE ON public.contribution_export_memberships
FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_export_membership_delete()
""")
    op.execute("""
CREATE FUNCTION public.guard_contribution_export_member_mutation() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
    expiry timestamptz;
BEGIN
    IF TG_OP='UPDATE' THEN
        RAISE EXCEPTION 'contribution export members are immutable'
          USING ERRCODE='23514';
    END IF;
    SELECT expires_at INTO expiry
      FROM public.contribution_export_memberships WHERE id=OLD.export_id;
    IF pg_catalog.pg_trigger_depth() <= 1 OR expiry IS NOT NULL THEN
        RAISE EXCEPTION 'contribution export members can be deleted only with an expired parent'
          USING ERRCODE='23514';
    END IF;
    RETURN OLD;
END $$
""")
    op.execute("""
CREATE TRIGGER contribution_export_member_mutation
BEFORE UPDATE OR DELETE ON public.contribution_export_members
FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_export_member_mutation()
""")
    op.execute("""
CREATE FUNCTION public.validate_contribution_export_membership(export_uuid uuid) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
    export_row public.contribution_export_memberships%ROWTYPE;
    stored_count bigint;
    selected_count bigint;
BEGIN
    SELECT * INTO export_row
      FROM public.contribution_export_memberships WHERE id=export_uuid;
    IF NOT FOUND THEN
        RETURN;
    END IF;
    IF NOT export_row.sealed THEN
        RAISE EXCEPTION 'contribution export membership must be sealed before commit'
          USING ERRCODE='23514';
    END IF;

    SELECT count(*) INTO stored_count
      FROM public.contribution_export_members WHERE export_id=export_uuid;
    SELECT count(*) INTO selected_count
      FROM public.contribution_records c
      WHERE (export_row.audience<>'self' OR c.contributor_id=export_row.actor_profile_id)
        AND (export_row.project_id IS NULL OR c.project_id=export_row.project_id)
        AND (export_row.contribution_type IS NULL
             OR c.contribution_type=export_row.contribution_type)
        AND (export_row.recorded_from IS NULL OR c.created_at>=export_row.recorded_from)
        AND (export_row.recorded_before IS NULL OR c.created_at<export_row.recorded_before);
    IF stored_count IS DISTINCT FROM export_row.member_count
      OR selected_count IS DISTINCT FROM export_row.member_count
      OR EXISTS (
        SELECT 1 FROM public.contribution_records c
        WHERE (export_row.audience<>'self' OR c.contributor_id=export_row.actor_profile_id)
          AND (export_row.project_id IS NULL OR c.project_id=export_row.project_id)
          AND (export_row.contribution_type IS NULL
               OR c.contribution_type=export_row.contribution_type)
          AND (export_row.recorded_from IS NULL OR c.created_at>=export_row.recorded_from)
          AND (export_row.recorded_before IS NULL OR c.created_at<export_row.recorded_before)
          AND NOT EXISTS (
            SELECT 1 FROM public.contribution_export_members m
            WHERE m.export_id=export_uuid AND m.contribution_id=c.id
              AND m.recorded_at=c.created_at
          )
      )
    THEN
        RAISE EXCEPTION 'contribution export membership is incomplete'
          USING ERRCODE='23514';
    END IF;
END $$
""")
    op.execute("""
CREATE FUNCTION public.enforce_contribution_export_membership() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    PERFORM public.validate_contribution_export_membership(NEW.id);
    RETURN NULL;
END $$
""")
    op.execute("""
CREATE CONSTRAINT TRIGGER contribution_export_membership_complete
AFTER INSERT OR UPDATE ON public.contribution_export_memberships
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION public.enforce_contribution_export_membership()
""")
    op.execute("""
CREATE FUNCTION public.reject_contribution_export_truncate() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    RAISE EXCEPTION 'contribution export custody tables cannot be truncated'
      USING ERRCODE='23514';
END $$
""")
    op.execute("""
CREATE TRIGGER contribution_export_membership_truncate
BEFORE TRUNCATE ON public.contribution_export_memberships
FOR EACH STATEMENT EXECUTE FUNCTION public.reject_contribution_export_truncate()
""")
    op.execute("""
CREATE TRIGGER contribution_export_member_truncate
BEFORE TRUNCATE ON public.contribution_export_members
FOR EACH STATEMENT EXECUTE FUNCTION public.reject_contribution_export_truncate()
""")


def downgrade() -> None:
    connection = op.get_bind()
    retained = connection.exec_driver_sql(
        "SELECT EXISTS (SELECT 1 FROM public.contribution_export_memberships) "
        "OR EXISTS (SELECT 1 FROM public.contribution_export_members)"
    ).scalar_one()
    if retained:
        raise RuntimeError(
            "0036_contribution_export_pages cannot be downgraded while retained "
            "contribution export custody exists"
        )
    raise RuntimeError(
        "Workstream v0.1 migrations cannot be downgraded; recreate the database"
    )
