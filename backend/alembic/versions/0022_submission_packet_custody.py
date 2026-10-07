"""Bind each admitted Submission to the contributor packet that passed intake."""

from alembic import op

revision = "0022_submission_packet_custody"
down_revision = "0021_submission_manifest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Read the final row: TASK inserts first, then binds ART in the same transaction.
    # Existing owner triggers already freeze bound identities and upstream evidence.
    op.execute("""
CREATE FUNCTION public.validate_submission_packet_custody() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    stored public.submissions%ROWTYPE;
    expected_packet text;
    actual_packet text;
BEGIN
    IF TG_OP = 'UPDATE' AND
       ROW(NEW.summary, NEW.worker_attestation, NEW.submission_bundle_admission_id,
           NEW.artifact_binding_id, NEW.artifact_content_id) IS NOT DISTINCT FROM
       ROW(OLD.summary, OLD.worker_attestation, OLD.submission_bundle_admission_id,
           OLD.artifact_binding_id, OLD.artifact_content_id) THEN
        RETURN NULL;
    END IF;
    SELECT * INTO stored FROM public.submissions WHERE id = NEW.id;
    IF NOT FOUND OR stored.submission_bundle_admission_id IS NULL THEN
        RETURN NULL;
    END IF;
    SELECT evidence.packet_sha256 INTO expected_packet
      FROM public.submission_bundle_admissions AS admission
      JOIN public.pre_submit_evidence_sets AS evidence
        ON evidence.id = admission.pre_submit_evidence_set_id
     WHERE admission.id = stored.submission_bundle_admission_id;
    actual_packet := 'sha256:' || pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
        public.project_guide_projection_canonical_json(pg_catalog.jsonb_build_object(
            'summary', stored.summary, 'contributor_attestation', stored.worker_attestation
        )), 'UTF8')), 'hex');
    IF expected_packet IS NULL OR actual_packet IS DISTINCT FROM expected_packet THEN
        RAISE EXCEPTION 'submission packet differs from checked evidence' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END;
$$;
""")
    op.execute("""
CREATE CONSTRAINT TRIGGER submission_packet_custody
AFTER INSERT OR UPDATE ON public.submissions
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION public.validate_submission_packet_custody();
""")


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
