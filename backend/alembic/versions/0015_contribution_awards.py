"""Immutable contribution and award storage without live economic consumers."""

from alembic import op

revision = "0015_contribution_awards"
down_revision = "0014_final_acceptance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE public.contribution_records (
	id UUID NOT NULL,
	project_id UUID NOT NULL,
	task_id UUID NOT NULL,
	submission_id UUID NOT NULL,
	contribution_type VARCHAR(32) NOT NULL,
	contributor_id UUID NOT NULL,
	source_review_id UUID,
	source_review_lease_id UUID,
	source_final_acceptance_id UUID,
	source_task_assignment_id UUID,
	artifact_hash VARCHAR(71) NOT NULL,
	contribution_policy_version_id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	CONSTRAINT pk_contribution_records PRIMARY KEY (id),
	CONSTRAINT ck_contribution_records_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128),
	CONSTRAINT ck_contribution_records_source_shape CHECK ((contribution_type='completed_review' and source_review_id is not null and source_review_lease_id is not null and source_final_acceptance_id is null and source_task_assignment_id is null) or (contribution_type='accepted_submission' and source_review_id is null and source_review_lease_id is null and source_final_acceptance_id is not null and source_task_assignment_id is not null)),
	CONSTRAINT ck_contribution_records_artifact_hash CHECK (artifact_hash ~ '^sha256:[0-9a-f]{64}$'),
	CONSTRAINT uq_contribution_records_source_review_id UNIQUE (source_review_id),
	CONSTRAINT uq_contribution_records_source_final_acceptance_id UNIQUE (source_final_acceptance_id),
	CONSTRAINT fk_contribution_records_project_id_projects FOREIGN KEY(project_id) REFERENCES public.projects (id) ON DELETE RESTRICT,
	CONSTRAINT fk_contribution_records_task_id_workstream_tasks FOREIGN KEY(task_id) REFERENCES public.workstream_tasks (id) ON DELETE RESTRICT,
	CONSTRAINT fk_contribution_records_submission_id_submissions FOREIGN KEY(submission_id) REFERENCES public.submissions (id) ON DELETE RESTRICT,
	CONSTRAINT fk_contribution_records_contributor_id_actor_profiles FOREIGN KEY(contributor_id) REFERENCES public.actor_profiles (id) ON DELETE RESTRICT,
	CONSTRAINT fk_contribution_records_source_review_id_reviews FOREIGN KEY(source_review_id) REFERENCES public.reviews (id) ON DELETE RESTRICT,
	CONSTRAINT fk_contribution_records_source_review_lease_id_review_leases FOREIGN KEY(source_review_lease_id) REFERENCES public.review_leases (id) ON DELETE RESTRICT,
	CONSTRAINT fk_contribution_records_source_final_acceptance_id_fina_374b FOREIGN KEY(source_final_acceptance_id) REFERENCES public.final_acceptances (id) ON DELETE RESTRICT,
	CONSTRAINT fk_contribution_records_source_task_assignment_id_task__7d76 FOREIGN KEY(source_task_assignment_id) REFERENCES public.task_assignments (id) ON DELETE RESTRICT,
	CONSTRAINT fk_contribution_records_contribution_policy_version_id__b9f5 FOREIGN KEY(contribution_policy_version_id) REFERENCES public.contribution_policy_versions (id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE public.compensation_awards (
	id UUID NOT NULL,
	project_id UUID NOT NULL,
	contribution_record_id UUID NOT NULL,
	contributor_id UUID NOT NULL,
	contribution_policy_version_id UUID NOT NULL,
	award_definition_id UUID NOT NULL,
	adapter_binding_id UUID NOT NULL,
	instrument_type VARCHAR(32) NOT NULL,
	unit_code VARCHAR(32) NOT NULL,
	quantity NUMERIC NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	correlation_id UUID NOT NULL,
	CONSTRAINT pk_compensation_awards PRIMARY KEY (id),
	CONSTRAINT ck_compensation_awards_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128),
	CONSTRAINT uq_compensation_awards_contribution_record_id UNIQUE (contribution_record_id, instrument_type),
	CONSTRAINT ck_compensation_awards_instrument_type CHECK (instrument_type in ('money','project_points')),
	CONSTRAINT ck_compensation_awards_quantity_exact_bounds CHECK (quantity > 0 and quantity < 100000000000000000000 and scale(quantity) between 0 and 18),
	CONSTRAINT ck_compensation_awards_project_points_whole CHECK (instrument_type <> 'project_points' or scale(quantity)=0),
	CONSTRAINT fk_compensation_awards_project_id_projects FOREIGN KEY(project_id) REFERENCES public.projects (id) ON DELETE RESTRICT,
	CONSTRAINT fk_compensation_awards_contribution_record_id_contribut_9b9a FOREIGN KEY(contribution_record_id) REFERENCES public.contribution_records (id) ON DELETE RESTRICT,
	CONSTRAINT fk_compensation_awards_contributor_id_actor_profiles FOREIGN KEY(contributor_id) REFERENCES public.actor_profiles (id) ON DELETE RESTRICT,
	CONSTRAINT fk_compensation_awards_contribution_policy_version_id_c_6094 FOREIGN KEY(contribution_policy_version_id) REFERENCES public.contribution_policy_versions (id) ON DELETE RESTRICT,
	CONSTRAINT fk_compensation_awards_award_definition_id_contribution_da4d FOREIGN KEY(award_definition_id) REFERENCES public.contribution_award_definitions (id) ON DELETE RESTRICT,
	CONSTRAINT fk_compensation_awards_adapter_binding_id_project_compe_1382 FOREIGN KEY(adapter_binding_id) REFERENCES public.project_compensation_adapter_bindings (id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE FUNCTION public.guard_contribution_source() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    NEW.created_at := pg_catalog.clock_timestamp();
    IF NOT EXISTS (
      SELECT 1 FROM public.submissions s
      JOIN public.workstream_tasks task ON task.id=s.task_id
      JOIN public.task_assignments assignment ON assignment.id=s.task_assignment_id
      JOIN public.artifact_bindings binding ON binding.id=s.artifact_binding_id
      JOIN public.artifact_contents content ON content.id=s.artifact_content_id
      JOIN public.contribution_policy_versions policy ON policy.id=NEW.contribution_policy_version_id
      JOIN public.contribution_rules rule ON rule.contribution_policy_version_id=policy.id
      WHERE s.id=NEW.submission_id AND s.task_id=NEW.task_id
        AND task.project_id=NEW.project_id
        AND assignment.project_id=NEW.project_id AND assignment.task_id=NEW.task_id
        AND assignment.contributor_id=s.contributor_id
        AND binding.content_id=content.id AND binding.project_id=NEW.project_id
        AND binding.resource_type='submission' AND binding.resource_id=s.id::text
        AND binding.logical_role='submission_bundle_original'
        AND NEW.artifact_hash=content.sha256
        AND policy.project_id=NEW.project_id AND policy.status IN ('published','retired')
        AND rule.project_id=NEW.project_id AND rule.contribution_type=NEW.contribution_type
    ) THEN
        RAISE EXCEPTION 'contribution canonical lineage mismatch' USING ERRCODE='23514';
    END IF;
    IF NEW.contribution_type='completed_review' THEN
        IF NOT EXISTS (
          SELECT 1 FROM public.reviews review
          JOIN public.review_leases lease ON lease.id=review.review_lease_id
          WHERE review.id=NEW.source_review_id AND review.project_id=NEW.project_id
            AND review.task_id=NEW.task_id AND review.submission_id=NEW.submission_id
            AND review.reviewer_id=NEW.contributor_id
            AND lease.id=NEW.source_review_lease_id AND lease.reviewer_id=NEW.contributor_id
            AND review.reviewer_contribution_policy_version_id=NEW.contribution_policy_version_id
            AND lease.reviewer_contribution_policy_version_id=NEW.contribution_policy_version_id
            AND review.artifact_hash=NEW.artifact_hash
        ) THEN
            RAISE EXCEPTION 'contribution reviewer source mismatch' USING ERRCODE='23514';
        END IF;
    ELSIF NEW.contribution_type='accepted_submission' THEN
        IF NOT EXISTS (
          SELECT 1 FROM public.final_acceptances acceptance
          JOIN public.submissions s ON s.id=acceptance.submission_id
          JOIN public.task_assignments assignment ON assignment.id=s.task_assignment_id
          WHERE acceptance.id=NEW.source_final_acceptance_id
            AND acceptance.project_id=NEW.project_id AND acceptance.task_id=NEW.task_id
            AND acceptance.submission_id=NEW.submission_id
            AND acceptance.accepted_submitter_id=NEW.contributor_id
            AND s.contributor_id=NEW.contributor_id AND assignment.contributor_id=NEW.contributor_id
            AND assignment.id=NEW.source_task_assignment_id
            AND assignment.submitter_contribution_policy_version_id=NEW.contribution_policy_version_id
            AND s.contribution_policy_version_id=NEW.contribution_policy_version_id
        ) THEN
            RAISE EXCEPTION 'contribution submitter source mismatch' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
""")
    op.execute("""
CREATE TRIGGER contribution_source BEFORE INSERT ON public.contribution_records
FOR EACH ROW EXECUTE FUNCTION public.guard_contribution_source();
""")
    op.execute("""
CREATE TRIGGER contribution_record_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
ON public.contribution_records FOR EACH STATEMENT
EXECUTE FUNCTION public.reject_artifact_fact_mutation();
""")
    op.execute("""
CREATE FUNCTION public.guard_compensation_award() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE mode text; source_type text; rule_uuid uuid;
BEGIN
    NEW.created_at := pg_catalog.clock_timestamp();
    SELECT rule.compensation_mode, record.contribution_type, rule.id
      INTO mode, source_type, rule_uuid
    FROM public.contribution_records record
    JOIN public.contribution_rules rule
      ON rule.contribution_policy_version_id=record.contribution_policy_version_id
      AND rule.project_id=record.project_id AND rule.contribution_type=record.contribution_type
    WHERE record.id=NEW.contribution_record_id AND record.project_id=NEW.project_id
      AND record.contributor_id=NEW.contributor_id
      AND record.contribution_policy_version_id=NEW.contribution_policy_version_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'award contribution lineage mismatch' USING ERRCODE='23514';
    END IF;
    IF mode IS DISTINCT FROM 'compensated' THEN
        RAISE EXCEPTION 'unpaid contribution cannot receive an award' USING ERRCODE='23514';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM public.contribution_award_definitions definition
      JOIN public.project_compensation_adapter_bindings binding ON binding.id=definition.adapter_binding_id
      WHERE definition.id=NEW.award_definition_id AND definition.contribution_rule_id=rule_uuid
        AND definition.contribution_policy_version_id=NEW.contribution_policy_version_id
        AND definition.project_id=NEW.project_id AND definition.contribution_type=source_type
        AND definition.instrument_type=NEW.instrument_type AND definition.unit_code=NEW.unit_code
        AND definition.quantity=NEW.quantity AND definition.adapter_binding_id=NEW.adapter_binding_id
        AND binding.project_id=NEW.project_id AND binding.instrument_type=NEW.instrument_type
    ) THEN
        RAISE EXCEPTION 'award frozen definition mismatch' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
""")
    op.execute("""
CREATE TRIGGER compensation_award_source BEFORE INSERT ON public.compensation_awards
FOR EACH ROW EXECUTE FUNCTION public.guard_compensation_award();
""")
    op.execute("""
CREATE TRIGGER compensation_award_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
ON public.compensation_awards FOR EACH STATEMENT
EXECUTE FUNCTION public.reject_artifact_fact_mutation();
""")


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
