"""Immutable shared acceptance source foundation without runtime authority."""

from alembic import op

revision = "0014_final_acceptance"
down_revision = "0013_review_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE public.final_acceptances (
	id UUID NOT NULL,
	project_id UUID NOT NULL,
	task_id UUID NOT NULL,
	submission_id UUID NOT NULL,
	acceptance_source VARCHAR(32) NOT NULL,
	source_review_id UUID,
	source_routing_manifest_id UUID,
	accepted_submitter_id UUID NOT NULL,
	recorded_by UUID NOT NULL,
	policy_context_ref UUID NOT NULL,
	accepted_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	CONSTRAINT pk_final_acceptances PRIMARY KEY (id),
	CONSTRAINT ck_final_acceptances_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128),
	CONSTRAINT ck_final_acceptances_source_shape CHECK ((acceptance_source='human_review' and source_review_id is not null and source_routing_manifest_id is null) or (acceptance_source='task_post_submit_route' and source_review_id is null and source_routing_manifest_id is not null)),
	CONSTRAINT uq_final_acceptances_task_id UNIQUE (task_id),
	CONSTRAINT uq_final_acceptances_submission_id UNIQUE (submission_id),
	CONSTRAINT uq_final_acceptances_source_review_id UNIQUE (source_review_id),
	CONSTRAINT uq_final_acceptances_source_routing_manifest_id UNIQUE (source_routing_manifest_id),
	CONSTRAINT fk_final_acceptances_project_id_projects FOREIGN KEY(project_id) REFERENCES public.projects (id) ON DELETE RESTRICT,
	CONSTRAINT fk_final_acceptances_task_id_workstream_tasks FOREIGN KEY(task_id) REFERENCES public.workstream_tasks (id) ON DELETE RESTRICT,
	CONSTRAINT fk_final_acceptances_submission_id_submissions FOREIGN KEY(submission_id) REFERENCES public.submissions (id) ON DELETE RESTRICT,
	CONSTRAINT fk_final_acceptances_source_review_id_reviews FOREIGN KEY(source_review_id) REFERENCES public.reviews (id) ON DELETE RESTRICT,
	CONSTRAINT fk_final_acceptances_source_routing_manifest_id_task_po_e9c0 FOREIGN KEY(source_routing_manifest_id) REFERENCES public.task_post_submit_routing_manifests (id) ON DELETE RESTRICT,
	CONSTRAINT fk_final_acceptances_accepted_submitter_id_actor_profiles FOREIGN KEY(accepted_submitter_id) REFERENCES public.actor_profiles (id) ON DELETE RESTRICT,
	CONSTRAINT fk_final_acceptances_recorded_by_actor_profiles FOREIGN KEY(recorded_by) REFERENCES public.actor_profiles (id) ON DELETE RESTRICT,
	CONSTRAINT fk_final_acceptances_policy_context_ref_review_policies FOREIGN KEY(policy_context_ref) REFERENCES public.review_policies (id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE FUNCTION public.guard_final_acceptance_source() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE policy_required boolean;
BEGIN
    NEW.accepted_at := pg_catalog.clock_timestamp();
    -- Let NOT NULL and the closed shape constraint own incomplete scalars.
    IF NEW.id IS NULL OR NEW.project_id IS NULL OR NEW.task_id IS NULL
       OR NEW.submission_id IS NULL OR NEW.accepted_submitter_id IS NULL
       OR NEW.recorded_by IS NULL OR NEW.policy_context_ref IS NULL
       OR NEW.acceptance_source IS NULL
       OR NOT ((NEW.acceptance_source='human_review' AND NEW.source_review_id IS NOT NULL
                AND NEW.source_routing_manifest_id IS NULL)
            OR (NEW.acceptance_source='task_post_submit_route' AND NEW.source_review_id IS NULL
                AND NEW.source_routing_manifest_id IS NOT NULL)) THEN
        RETURN NEW;
    END IF;
    SELECT policy.human_review_required INTO policy_required
    FROM public.submissions s
    JOIN public.workstream_tasks task ON task.id=s.task_id
    JOIN public.task_assignments assignment ON assignment.id=s.task_assignment_id
    JOIN public.actor_profiles contributor ON contributor.id=s.contributor_id
    JOIN public.project_guides guide ON guide.project_id=task.project_id
      AND guide.version=s.locked_guide_version
    JOIN public.guide_mutation_idempotency_records activation
      ON activation.operation_id=guide.activation_operation_id
      AND activation.project_id=guide.project_id AND activation.resource_id=guide.id
    JOIN public.review_policies policy ON policy.id=s.locked_review_policy_id
    WHERE s.id=NEW.submission_id AND s.task_id=NEW.task_id
      AND task.project_id=NEW.project_id
      AND assignment.project_id=NEW.project_id AND assignment.task_id=NEW.task_id
      AND assignment.contributor_id=s.contributor_id
      AND s.contributor_id=NEW.accepted_submitter_id AND contributor.actor_kind='human'
      AND policy.id=NEW.policy_context_ref AND policy.project_id=NEW.project_id
      AND policy.guide_version=s.locked_guide_version AND policy.semantics_status='complete'
      AND policy.policy_generation=s.locked_review_policy_generation
      AND policy.policy_hash=s.locked_review_policy_hash
      AND guide.selected_review_policy_id=policy.id
      AND guide.selected_review_policy_generation=policy.policy_generation
      AND guide.selected_review_policy_hash=policy.policy_hash
      AND guide.status IN ('active','superseded')
      AND activation.action_id='project.guide.activate' AND activation.status='committed'
      AND activation.activation_facts_json IS NOT NULL
      AND activation.activation_authority_json IS NOT NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'final acceptance canonical lineage mismatch' USING ERRCODE='23514';
    END IF;
    IF NEW.acceptance_source='human_review' THEN
        IF NOT EXISTS (
          SELECT 1 FROM public.reviews r
          WHERE r.id=NEW.source_review_id AND r.project_id=NEW.project_id
            AND r.task_id=NEW.task_id AND r.submission_id=NEW.submission_id
            AND r.reviewer_id=NEW.recorded_by AND r.locked_review_policy_id=NEW.policy_context_ref
            AND r.decision='accept' AND policy_required IS TRUE
        ) THEN
            RAISE EXCEPTION 'final acceptance human source mismatch' USING ERRCODE='23514';
        END IF;
    ELSE
        IF NOT EXISTS (
          SELECT 1 FROM public.task_post_submit_routing_manifests manifest
          JOIN public.submissions s ON s.id=manifest.submission_id
          JOIN public.actor_profiles recorder ON recorder.id=NEW.recorded_by
          WHERE manifest.id=NEW.source_routing_manifest_id
            AND manifest.project_id=NEW.project_id AND manifest.task_id=NEW.task_id
            AND manifest.submission_id=NEW.submission_id AND manifest.submission_version=s.version
            AND manifest.assignment_id=s.task_assignment_id
            AND manifest.contributor_id=NEW.accepted_submitter_id
            AND recorder.actor_kind='service'
            AND ROW(manifest.human_review_required,policy_required)=ROW(false,false)
        ) THEN
            RAISE EXCEPTION 'final acceptance routing source mismatch' USING ERRCODE='23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;
""")
    op.execute("""
CREATE TRIGGER final_acceptance_source BEFORE INSERT ON public.final_acceptances
FOR EACH ROW EXECUTE FUNCTION public.guard_final_acceptance_source();
""")
    op.execute("""
CREATE TRIGGER final_acceptance_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON public.final_acceptances
FOR EACH STATEMENT EXECUTE FUNCTION public.reject_artifact_fact_mutation();
""")


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
