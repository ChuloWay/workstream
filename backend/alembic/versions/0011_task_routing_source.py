"""Install the immutable route-neutral TASK post-submit source foundation."""

from alembic import op
import sqlalchemy as sa


revision = "0011_task_routing_source"
down_revision = "0010_post_submit_authority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create detached source custody without installing a writer or reader."""
    op.execute("SET LOCAL search_path = pg_catalog, public, pg_temp")
    op.create_table(
        "task_post_submit_routing_manifests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("submission_version", sa.Integer(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("contributor_id", sa.Uuid(), nullable=False),
        sa.Column("contribution_policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("checker_run_id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_request_id", sa.Uuid(), nullable=False),
        sa.Column("request_digest", sa.String(length=71), nullable=False),
        sa.Column("evaluation_generation", sa.Integer(), nullable=False),
        sa.Column("result_id", sa.Uuid(), nullable=False),
        sa.Column("result_digest", sa.String(length=71), nullable=False),
        sa.Column("completion_event_id", sa.Uuid(), nullable=False),
        sa.Column("execute_evidence_id", sa.Uuid(), nullable=False),
        sa.Column("finalize_evidence_id", sa.Uuid(), nullable=False),
        sa.Column("human_review_required", sa.Boolean(), nullable=False),
        sa.Column("replica_id", sa.Uuid(), nullable=False),
        sa.Column("content_sha256", sa.String(length=71), nullable=False),
        sa.Column("byte_count", sa.BigInteger(), nullable=False),
        sa.Column("semantic_manifest_sha256", sa.String(length=71), nullable=False),
        sa.CheckConstraint(
            "(get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128",
            name="id_uuid7",
        ),
        sa.CheckConstraint("submission_version > 0", name="submission_version_positive"),
        sa.CheckConstraint("evaluation_generation > 0", name="evaluation_generation_positive"),
        sa.CheckConstraint("byte_count >= 0", name="byte_count_nonnegative"),
        sa.CheckConstraint(
            "request_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "result_digest ~ '^sha256:[0-9a-f]{64}$' and "
            "content_sha256 ~ '^sha256:[0-9a-f]{64}$' and "
            "semantic_manifest_sha256 ~ '^sha256:[0-9a-f]{64}$'",
            name="sha256_shapes",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "project_id"],
            ["public.workstream_tasks.id", "public.workstream_tasks.project_id"],
            name="fk_task_routing_manifest_task_project",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["submission_id", "task_id", "submission_version"],
            ["public.submissions.id", "public.submissions.task_id", "public.submissions.version"],
            name="fk_task_routing_manifest_submission_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id", "task_id", "contributor_id"],
            [
                "public.task_assignments.id",
                "public.task_assignments.task_id",
                "public.task_assignments.contributor_id",
            ],
            name="fk_task_routing_manifest_assignment_identity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["contribution_policy_version_id", "project_id"],
            [
                "public.contribution_policy_versions.id",
                "public.contribution_policy_versions.project_id",
            ],
            name="fk_task_routing_manifest_contribution_project",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["checker_run_id", "task_id", "submission_id"],
            [
                "public.checker_runs.id",
                "public.checker_runs.task_id",
                "public.checker_runs.submission_id",
            ],
            name="fk_task_routing_manifest_checker_source",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["completion_event_id"],
            ["public.outbox_events.event_id"],
            name="fk_task_routing_manifest_completion_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["execute_evidence_id"],
            ["public.audit_events.id"],
            name="fk_task_routing_manifest_execute_evidence",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["finalize_evidence_id"],
            ["public.audit_events.id"],
            name="fk_task_routing_manifest_finalize_evidence",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["replica_id"],
            ["public.artifact_replicas.id"],
            name="fk_task_routing_manifest_replica",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "submission_id",
            "checker_run_id",
            "result_digest",
            name="uq_task_routing_manifest_source",
        ),
        schema="public",
    )
    _install_source_guard()
    _install_immutability_guard()


def _install_source_guard() -> None:
    op.execute(
        """
CREATE FUNCTION public.guard_task_post_submit_routing_source() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    run public.checker_runs%ROWTYPE;
    expected_material jsonb;
BEGIN
    -- Preserve NOT NULL as the sole owner of missing-scalar rejection.
    IF NEW.id IS NULL OR NEW.created_at IS NULL OR NEW.project_id IS NULL
       OR NEW.task_id IS NULL OR NEW.submission_id IS NULL
       OR NEW.submission_version IS NULL OR NEW.assignment_id IS NULL
       OR NEW.contributor_id IS NULL OR NEW.contribution_policy_version_id IS NULL
       OR NEW.checker_run_id IS NULL OR NEW.evaluation_request_id IS NULL
       OR NEW.request_digest IS NULL OR NEW.evaluation_generation IS NULL
       OR NEW.result_id IS NULL OR NEW.result_digest IS NULL
       OR NEW.completion_event_id IS NULL OR NEW.execute_evidence_id IS NULL
       OR NEW.finalize_evidence_id IS NULL OR NEW.human_review_required IS NULL
       OR NEW.replica_id IS NULL OR NEW.content_sha256 IS NULL
       OR NEW.byte_count IS NULL OR NEW.semantic_manifest_sha256 IS NULL
    THEN
        RETURN NEW;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.submissions AS submission
        JOIN public.workstream_tasks AS task
          ON task.id = submission.task_id
        JOIN public.task_assignments AS assignment
          ON assignment.id = submission.task_assignment_id
         AND assignment.task_id = submission.task_id
         AND assignment.contributor_id = submission.contributor_id
        WHERE submission.id IS NOT DISTINCT FROM NEW.submission_id
          AND submission.version IS NOT DISTINCT FROM NEW.submission_version
          AND submission.task_id IS NOT DISTINCT FROM NEW.task_id
          AND task.project_id IS NOT DISTINCT FROM NEW.project_id
          AND submission.task_assignment_id IS NOT DISTINCT FROM NEW.assignment_id
          AND submission.contributor_id IS NOT DISTINCT FROM NEW.contributor_id
          AND assignment.submitter_contribution_policy_version_id
                IS NOT DISTINCT FROM NEW.contribution_policy_version_id
          AND submission.contribution_policy_version_id
                IS NOT DISTINCT FROM NEW.contribution_policy_version_id
          AND task.locked_contribution_policy_version_id
                IS NOT DISTINCT FROM NEW.contribution_policy_version_id
    ) THEN
        RAISE EXCEPTION 'task post-submit routing source lineage mismatch'
          USING ERRCODE = '23514';
    END IF;

    SELECT candidate.* INTO run
    FROM public.checker_runs AS candidate
    WHERE candidate.id IS NOT DISTINCT FROM NEW.checker_run_id
      AND candidate.project_id IS NOT DISTINCT FROM NEW.project_id
      AND candidate.task_id IS NOT DISTINCT FROM NEW.task_id
      AND candidate.submission_id IS NOT DISTINCT FROM NEW.submission_id
      AND candidate.submission_version IS NOT DISTINCT FROM NEW.submission_version
      AND candidate.evaluation_request_id IS NOT DISTINCT FROM NEW.evaluation_request_id
      AND candidate.request_digest IS NOT DISTINCT FROM NEW.request_digest
      AND candidate.evaluation_generation IS NOT DISTINCT FROM NEW.evaluation_generation
      AND candidate.result_id IS NOT DISTINCT FROM NEW.result_id
      AND candidate.result_digest IS NOT DISTINCT FROM NEW.result_digest
      AND candidate.completion_event_id IS NOT DISTINCT FROM NEW.completion_event_id
      AND candidate.execute_evidence_id IS NOT DISTINCT FROM NEW.execute_evidence_id
      AND candidate.finalize_evidence_id IS NOT DISTINCT FROM NEW.finalize_evidence_id
      AND candidate.execute_evidence_id IS DISTINCT FROM candidate.finalize_evidence_id
      AND candidate.status IS NOT DISTINCT FROM 'completed'
      AND candidate.routing_recommendation IS NOT DISTINCT FROM 'allow_review'
      AND candidate.outcome_source IS NOT DISTINCT FROM 'auto_checker'
      AND candidate.material_custody::jsonb IS NOT NULL
      AND public.checker_post_submit_receipt_valid(candidate, 'execute', false)
      AND public.checker_post_submit_receipt_valid(candidate, 'finalize', false);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task post-submit routing checker source mismatch'
          USING ERRCODE = '23514';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.submissions AS submission
        JOIN public.workstream_tasks AS task ON task.id = submission.task_id
        JOIN public.project_guides AS guide
          ON guide.project_id = task.project_id
         AND guide.version = submission.locked_guide_version
        JOIN public.guide_mutation_idempotency_records AS activation
          ON activation.operation_id = guide.activation_operation_id
         AND activation.project_id = guide.project_id
         AND activation.resource_id = guide.id
        WHERE submission.id IS NOT DISTINCT FROM NEW.submission_id
          AND submission.task_id IS NOT DISTINCT FROM NEW.task_id
          AND submission.version IS NOT DISTINCT FROM NEW.submission_version
          AND guide.status IN ('active', 'superseded')
          AND guide.activation_operation_id IS NOT NULL
          AND activation.action_id IS NOT DISTINCT FROM 'project.guide.activate'
          AND activation.status IS NOT DISTINCT FROM 'committed'
          AND activation.activation_facts_json IS NOT NULL
          AND activation.activation_authority_json IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'task post-submit routing guide activation mismatch'
          USING ERRCODE = '23514';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM public.submissions AS submission
        JOIN public.workstream_tasks AS task ON task.id = submission.task_id
        JOIN public.project_guides AS guide
          ON guide.project_id = task.project_id
         AND guide.version = submission.locked_guide_version
        JOIN public.review_policies AS review
          ON review.project_id = guide.project_id
         AND review.guide_version = guide.version
         AND review.id = guide.selected_review_policy_id
         AND review.policy_generation = guide.selected_review_policy_generation
         AND review.policy_hash = guide.selected_review_policy_hash
        WHERE submission.id IS NOT DISTINCT FROM NEW.submission_id
          AND submission.task_id IS NOT DISTINCT FROM NEW.task_id
          AND submission.version IS NOT DISTINCT FROM NEW.submission_version
          AND submission.locked_review_policy_id IS NOT DISTINCT FROM review.id
          AND submission.locked_review_policy_generation
                IS NOT DISTINCT FROM review.policy_generation
          AND submission.locked_review_policy_hash IS NOT DISTINCT FROM review.policy_hash
          AND task.locked_review_policy_id IS NOT DISTINCT FROM review.id
          AND task.locked_review_policy_generation IS NOT DISTINCT FROM review.policy_generation
          AND task.locked_review_policy_hash IS NOT DISTINCT FROM review.policy_hash
          AND run.locked_review_policy_id IS NOT DISTINCT FROM review.id
          AND run.locked_review_policy_generation IS NOT DISTINCT FROM review.policy_generation
          AND run.locked_review_policy_hash IS NOT DISTINCT FROM review.policy_hash
          AND review.human_review_required IS NOT DISTINCT FROM NEW.human_review_required
    ) THEN
        RAISE EXCEPTION 'task post-submit routing review policy mismatch'
          USING ERRCODE = '23514';
    END IF;

    expected_material := pg_catalog.jsonb_build_object(
        'submission_id', NEW.submission_id,
        'submission_version', NEW.submission_version,
        'admission_id', (run.material_custody::jsonb)->'admission_id',
        'binding_id', (run.material_custody::jsonb)->'binding_id',
        'content_id', (run.material_custody::jsonb)->'content_id',
        'replica_id', NEW.replica_id,
        'content_sha256', NEW.content_sha256,
        'byte_count', NEW.byte_count,
        'semantic_manifest_sha256', NEW.semantic_manifest_sha256
    );
    IF run.material_custody::jsonb IS DISTINCT FROM expected_material
       OR public.art_submission_material_matches(
            NEW.project_id,
            NEW.task_id,
            NEW.submission_id,
            NEW.submission_version,
            expected_material
       ) IS DISTINCT FROM true
    THEN
        RAISE EXCEPTION 'task post-submit routing material mismatch'
          USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;
"""
    )
    op.execute(
        """
CREATE TRIGGER task_routing_manifest_source_guard
BEFORE INSERT ON public.task_post_submit_routing_manifests
FOR EACH ROW EXECUTE FUNCTION public.guard_task_post_submit_routing_source();
"""
    )


def _install_immutability_guard() -> None:
    op.execute(
        """
CREATE FUNCTION public.protect_task_post_submit_routing_manifest() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp AS $$
BEGIN
    RAISE EXCEPTION 'task post-submit routing source is immutable'
      USING ERRCODE = '23514';
END
$$;
"""
    )
    op.execute(
        """
CREATE TRIGGER task_routing_manifest_immutable
BEFORE UPDATE OR DELETE ON public.task_post_submit_routing_manifests
FOR EACH ROW EXECUTE FUNCTION public.protect_task_post_submit_routing_manifest();
"""
    )
    op.execute(
        """
CREATE TRIGGER task_routing_manifest_no_truncate
BEFORE TRUNCATE ON public.task_post_submit_routing_manifests
FOR EACH STATEMENT EXECUTE FUNCTION public.protect_task_post_submit_routing_manifest();
"""
    )


def downgrade() -> None:
    """Reject destructive downgrade of retained immutable source evidence."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
