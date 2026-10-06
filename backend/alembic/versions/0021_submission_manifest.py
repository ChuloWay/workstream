"""Retain inspected ZIP metadata without rewriting historical evidence."""

from alembic import op
import sqlalchemy as sa

revision = "0021_submission_manifest"
down_revision = "0020_review_admission_lock_order"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Require bound metadata on new evidence; preserve existing rows unchanged."""
    op.execute("SET LOCAL search_path = pg_catalog, public, pg_temp")
    op.add_column("pre_submit_evidence_sets", sa.Column("semantic_manifest_body", sa.JSON(), nullable=True), schema="public")
    op.execute("""
CREATE FUNCTION public.submission_manifest_metadata_valid(body jsonb, expected_digest text)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    item jsonb;
    path text;
    previous_path text;
    expanded numeric := 0;
    amount numeric;
BEGIN
    IF body IS NULL OR pg_catalog.jsonb_typeof(body) IS DISTINCT FROM 'object'
       OR body->>'schema_version' IS DISTINCT FROM 'workstream.submission_bundle_manifest.v1'
       OR pg_catalog.jsonb_typeof(body->'entries') IS DISTINCT FROM 'array'
       OR body - ARRAY['schema_version','entries'] IS DISTINCT FROM '{}'::jsonb
    THEN RETURN false; END IF;
    IF pg_catalog.jsonb_array_length(body->'entries') > 100000 THEN RETURN false; END IF;
    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(body->'entries') LOOP
        IF pg_catalog.jsonb_typeof(item) IS DISTINCT FROM 'object'
           OR pg_catalog.jsonb_typeof(item->'normalized_path') IS DISTINCT FROM 'string'
        THEN RETURN false; END IF;
        path := item->>'normalized_path';
        IF path = '' OR (previous_path IS NOT NULL AND path COLLATE "C" <= previous_path COLLATE "C")
        THEN RETURN false; END IF;
        previous_path := path;
        IF item->>'entry_type' = 'directory' THEN
            IF item - ARRAY['normalized_path','entry_type'] IS DISTINCT FROM '{}'::jsonb
            THEN RETURN false; END IF;
        ELSIF item->>'entry_type' = 'file' THEN
            IF item - ARRAY['normalized_path','entry_type','sha256','byte_count','executable']
                    IS DISTINCT FROM '{}'::jsonb
               OR pg_catalog.jsonb_typeof(item->'sha256') IS DISTINCT FROM 'string'
               OR (item->>'sha256') !~ '^sha256:[0-9a-f]{64}$'
               OR pg_catalog.jsonb_typeof(item->'byte_count') IS DISTINCT FROM 'number'
               OR (item->>'byte_count') !~ '^[0-9]+$'
               OR pg_catalog.jsonb_typeof(item->'executable') IS DISTINCT FROM 'boolean'
            THEN RETURN false; END IF;
            amount := (item->>'byte_count')::numeric;
            expanded := expanded + amount;
            IF expanded > 536870912 THEN RETURN false; END IF;
        ELSE RETURN false;
        END IF;
    END LOOP;
    RETURN expected_digest IS NOT NULL AND expected_digest = 'sha256:' || pg_catalog.encode(
        pg_catalog.sha256(pg_catalog.convert_to(public.project_guide_projection_canonical_json(body), 'UTF8')), 'hex');
END;
$$;
""")
    op.execute("""
CREATE FUNCTION public.guard_submission_manifest_metadata() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
BEGIN
    IF NOT public.submission_manifest_metadata_valid(NEW.semantic_manifest_body::jsonb, NEW.semantic_manifest_sha256)
    THEN RAISE EXCEPTION 'pre-submit manifest metadata invalid' USING ERRCODE='23514'; END IF;
    RETURN NEW;
END;
$$;
""")
    op.execute("""
CREATE TRIGGER trg_submission_manifest_metadata
BEFORE INSERT ON public.pre_submit_evidence_sets
FOR EACH ROW EXECUTE FUNCTION public.guard_submission_manifest_metadata();
""")


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
