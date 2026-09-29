"""Bind checker output intent and publication to exact verified ART custody."""

from alembic import op
import sqlalchemy as sa


revision = "0007_checker_output_custody"
down_revision = "0006_history_read_authority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Install fail-closed checker output intent and binding custody."""
    op.execute(
        "lock table artifact_bindings, artifact_contents, artifact_operation_receipts, "
        "artifact_put_attempts, artifact_put_observation_receipts, artifact_replicas, "
        "artifact_verification_jobs, artifact_verification_receipts, checker_runs, "
        "submissions, workstream_tasks in access exclusive mode"
    )

    op.add_column(
        "artifact_put_attempts",
        sa.Column("submission_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "artifact_put_attempts",
        sa.Column("submission_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "artifact_put_attempts",
        sa.Column("checker_request_digest", sa.String(length=71), nullable=True),
    )
    op.add_column(
        "artifact_put_attempts",
        sa.Column(
            "checker_output_custody_sealed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "artifact_verification_jobs",
        sa.Column(
            "checker_output_custody_sealed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "artifact_replicas",
        sa.Column(
            "checker_output_custody_sealed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "artifact_bindings",
        sa.Column("put_attempt_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "artifact_bindings",
        sa.Column("verification_receipt_id", sa.Uuid(), nullable=True),
    )

    _refuse_unprovable_retained_checker_output()

    op.execute(
        "alter table artifact_put_attempts drop constraint "
        "ck_artifact_put_attempts_producer_reference"
    )
    op.execute(
        "alter table artifact_put_attempts add constraint "
        "ck_artifact_put_attempts_producer_reference check ("
        "(producer_request_type = 'guide' and guide_source_item_id is not null "
        "and checker_run_id is null and task_id is null and submission_id is null "
        "and submission_version is null and logical_role is null) or "
        "(producer_request_type = 'checker_output' and guide_source_item_id is null "
        "and checker_run_id is not null and task_id is not null "
        "and submission_id is not null and submission_version is not null "
        "and octet_length(logical_role) between 1 and 100) or "
        "(producer_request_type = 'submission_bundle' and guide_source_item_id is null "
        "and checker_run_id is null and task_id is not null and submission_id is null "
        "and submission_version is null and logical_role is null))"
    )
    op.execute(
        "alter table artifact_put_attempts add constraint "
        "ck_artifact_put_attempts_checker_request_digest check ("
        "(producer_request_type = 'checker_output' and checker_request_digest is not null "
        "and checker_request_digest ~ '^sha256:[0-9a-f]{64}$') or "
        "(producer_request_type <> 'checker_output' and checker_request_digest is null))"
    )
    op.create_foreign_key(
        "fk_artifact_put_attempts_task_project",
        "artifact_put_attempts",
        "workstream_tasks",
        ["task_id", "project_id"],
        ["id", "project_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_artifact_put_attempts_checker_run_ownership",
        "artifact_put_attempts",
        "checker_runs",
        ["checker_run_id", "task_id", "submission_id"],
        ["id", "task_id", "submission_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_artifact_put_attempts_submission_version",
        "artifact_put_attempts",
        "submissions",
        ["submission_id", "task_id", "submission_version"],
        ["id", "task_id", "version"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_artifact_put_attempts_submission_id",
        "artifact_put_attempts",
        ["submission_id"],
    )

    op.create_foreign_key(
        "fk_artifact_bindings_checker_put_attempt",
        "artifact_bindings",
        "artifact_put_attempts",
        ["put_attempt_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_artifact_bindings_checker_verification_receipt",
        "artifact_bindings",
        "artifact_verification_receipts",
        ["verification_receipt_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        "alter table artifact_bindings add constraint "
        "ck_artifact_bindings_checker_output_lineage check ("
        "(resource_type = 'checker_run' and scope_version = 1 "
        "and put_attempt_id is not null and verification_receipt_id is not null) or "
        "(resource_type <> 'checker_run' and put_attempt_id is null "
        "and verification_receipt_id is null))"
    )
    op.create_index(
        "ix_artifact_bindings_put_attempt_id",
        "artifact_bindings",
        ["put_attempt_id"],
    )
    op.create_index(
        "ix_artifact_bindings_verification_receipt_id",
        "artifact_bindings",
        ["verification_receipt_id"],
    )

    _install_checker_output_attempt_custody()
    _install_checker_output_ancestor_custody()
    _install_checker_output_binding_guard()


def downgrade() -> None:
    """Reject destructive downgrade of immutable checker output evidence."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")


def _refuse_unprovable_retained_checker_output() -> None:
    """Never invent the absent evaluation/slot digest for retained checker output."""
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1
            FROM artifact_put_attempts attempt
            LEFT JOIN checker_runs run
              ON run.id=attempt.checker_run_id AND run.task_id=attempt.task_id
            LEFT JOIN submissions submission
              ON submission.id=run.submission_id
             AND submission.task_id=run.task_id
             AND submission.version=run.submission_version
            LEFT JOIN workstream_tasks task
              ON task.id=run.task_id AND task.project_id=attempt.project_id
            WHERE attempt.producer_request_type='checker_output'
              AND (run.id IS NULL OR submission.id IS NULL OR task.id IS NULL)
          ) THEN
            RAISE EXCEPTION 'retained checker output attempt ownership is inconsistent'
              USING ERRCODE='23514';
          END IF;
          IF EXISTS (
            SELECT 1 FROM artifact_put_attempts
            WHERE producer_request_type='checker_output'
          ) THEN
            RAISE EXCEPTION
              'retained checker output request custody is unprovable; evaluation and slot digest was not persisted'
              USING ERRCODE='23514';
          END IF;
          IF EXISTS (
            SELECT 1 FROM artifact_bindings WHERE resource_type='checker_run'
          ) THEN
            RAISE EXCEPTION
              'retained checker output binding ancestry is unprovable'
              USING ERRCODE='23514';
          END IF;
        END $$
        """
    )


def _install_checker_output_attempt_custody() -> None:
    op.execute(
        """
        CREATE FUNCTION guard_checker_output_put_attempt_custody() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' THEN
            IF OLD.producer_request_type='checker_output'
               OR OLD.checker_output_custody_sealed THEN
              RAISE EXCEPTION 'checker output put attempt custody is immutable'
                USING ERRCODE='55000';
            END IF;
            RETURN OLD;
          END IF;
          IF OLD.checker_output_custody_sealed THEN
            IF NOT NEW.checker_output_custody_sealed
               OR (to_jsonb(NEW) - 'checker_output_custody_sealed')
                  IS DISTINCT FROM
                  (to_jsonb(OLD) - 'checker_output_custody_sealed') THEN
              RAISE EXCEPTION 'checker output put attempt custody is immutable'
                USING ERRCODE='55000';
            END IF;
            RETURN NEW;
          END IF;
          IF NEW.checker_output_custody_sealed THEN
            IF (to_jsonb(NEW) - 'checker_output_custody_sealed')
                 IS DISTINCT FROM
                 (to_jsonb(OLD) - 'checker_output_custody_sealed')
               OR NOT EXISTS (
                 SELECT 1 FROM artifact_bindings binding
                 WHERE binding.resource_type='checker_run'
                   AND binding.put_attempt_id=OLD.id
               ) THEN
              RAISE EXCEPTION 'checker output put attempt seal requires binding'
                USING ERRCODE='55000';
            END IF;
            RETURN NEW;
          END IF;
          IF OLD.producer_request_type='checker_output'
             OR NEW.producer_request_type='checker_output' THEN
            IF ROW(
                 NEW.id, NEW.producer_request_type, NEW.producer_type, NEW.producer_ref,
                 NEW.project_id, NEW.task_id, NEW.guide_source_item_id, NEW.checker_run_id,
                 NEW.submission_id, NEW.submission_version, NEW.logical_role,
                 NEW.sha256, NEW.byte_count, NEW.media_type, NEW.storage_namespace_id,
                 NEW.namespace_fingerprint, NEW.canonical_target, NEW.operation_identity,
                 NEW.request_digest, NEW.checker_request_digest, NEW.maximum_observations,
                 NEW.prepared_at, NEW.created_at
               ) IS DISTINCT FROM ROW(
                 OLD.id, OLD.producer_request_type, OLD.producer_type, OLD.producer_ref,
                 OLD.project_id, OLD.task_id, OLD.guide_source_item_id, OLD.checker_run_id,
                 OLD.submission_id, OLD.submission_version, OLD.logical_role,
                 OLD.sha256, OLD.byte_count, OLD.media_type, OLD.storage_namespace_id,
                 OLD.namespace_fingerprint, OLD.canonical_target, OLD.operation_identity,
                 OLD.request_digest, OLD.checker_request_digest, OLD.maximum_observations,
                 OLD.prepared_at, OLD.created_at
               ) THEN
              RAISE EXCEPTION 'checker output put attempt custody is immutable'
                USING ERRCODE='55000';
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER checker_output_put_attempt_custody "
        "BEFORE DELETE OR UPDATE ON artifact_put_attempts FOR EACH ROW "
        "EXECUTE FUNCTION guard_checker_output_put_attempt_custody()"
    )
    op.execute(
        """
        CREATE FUNCTION guard_checker_output_put_attempt_truncate() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM artifact_put_attempts
            WHERE producer_request_type='checker_output'
          ) THEN
            RAISE EXCEPTION 'checker output put attempt custody is immutable'
              USING ERRCODE='55000';
          END IF;
          RETURN NULL;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER checker_output_put_attempt_no_truncate BEFORE TRUNCATE "
        "ON artifact_put_attempts FOR EACH STATEMENT "
        "EXECUTE FUNCTION guard_checker_output_put_attempt_truncate()"
    )


def _install_checker_output_ancestor_custody() -> None:
    op.execute(
        """
        CREATE FUNCTION guard_checker_output_verification_job_custody() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' THEN
            IF OLD.checker_output_custody_sealed THEN
              RAISE EXCEPTION 'checker output verification job custody is immutable'
                USING ERRCODE='55000';
            END IF;
            RETURN OLD;
          END IF;
          IF OLD.checker_output_custody_sealed THEN
            IF NOT NEW.checker_output_custody_sealed
               OR (to_jsonb(NEW) - 'checker_output_custody_sealed')
                  IS DISTINCT FROM
                  (to_jsonb(OLD) - 'checker_output_custody_sealed') THEN
              RAISE EXCEPTION 'checker output verification job custody is immutable'
                USING ERRCODE='55000';
            END IF;
            RETURN NEW;
          END IF;
          IF NEW.checker_output_custody_sealed THEN
            IF (to_jsonb(NEW) - 'checker_output_custody_sealed')
                 IS DISTINCT FROM
                 (to_jsonb(OLD) - 'checker_output_custody_sealed')
               OR NOT EXISTS (
                 SELECT 1
                 FROM artifact_bindings binding
                 JOIN artifact_verification_receipts receipt
                   ON receipt.id=binding.verification_receipt_id
                 WHERE binding.resource_type='checker_run'
                   AND receipt.verification_job_id=OLD.id
               ) THEN
              RAISE EXCEPTION 'checker output verification job seal requires binding'
                USING ERRCODE='55000';
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER checker_output_verification_job_custody "
        "BEFORE DELETE OR UPDATE ON artifact_verification_jobs FOR EACH ROW "
        "EXECUTE FUNCTION guard_checker_output_verification_job_custody()"
    )
    op.execute(
        """
        CREATE FUNCTION guard_checker_output_replica_custody() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' THEN
            IF OLD.checker_output_custody_sealed THEN
              RAISE EXCEPTION 'checker output replica custody is immutable'
                USING ERRCODE='55000';
            END IF;
            RETURN OLD;
          END IF;
          IF OLD.checker_output_custody_sealed THEN
            IF NOT NEW.checker_output_custody_sealed
               OR ROW(
                    NEW.id, NEW.content_id, NEW.storage_namespace_id,
                    NEW.namespace_fingerprint, NEW.adapter,
                    NEW.provider_profile, NEW.provider_object_ref
                  ) IS DISTINCT FROM ROW(
                    OLD.id, OLD.content_id, OLD.storage_namespace_id,
                    OLD.namespace_fingerprint, OLD.adapter,
                    OLD.provider_profile, OLD.provider_object_ref
                  ) THEN
              RAISE EXCEPTION 'checker output replica custody is immutable'
                USING ERRCODE='55000';
            END IF;
            RETURN NEW;
          END IF;
          IF NEW.checker_output_custody_sealed THEN
            IF (to_jsonb(NEW) - 'checker_output_custody_sealed')
                 IS DISTINCT FROM
                 (to_jsonb(OLD) - 'checker_output_custody_sealed')
               OR NOT EXISTS (
                 SELECT 1
                 FROM artifact_bindings binding
                 JOIN artifact_verification_receipts receipt
                   ON receipt.id=binding.verification_receipt_id
                 JOIN artifact_verification_jobs job
                   ON job.id=receipt.verification_job_id
                 WHERE binding.resource_type='checker_run'
                   AND job.replica_id=OLD.id
               ) THEN
              RAISE EXCEPTION 'checker output replica seal requires binding'
                USING ERRCODE='55000';
            END IF;
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER checker_output_replica_custody "
        "BEFORE DELETE OR UPDATE ON artifact_replicas FOR EACH ROW "
        "EXECUTE FUNCTION guard_checker_output_replica_custody()"
    )


def _install_checker_output_binding_guard() -> None:
    op.execute(
        """
        CREATE FUNCTION guard_checker_output_binding_insert() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          verification artifact_verification_receipts%ROWTYPE;
          job artifact_verification_jobs%ROWTYPE;
          replica artifact_replicas%ROWTYPE;
          attempt artifact_put_attempts%ROWTYPE;
          content artifact_contents%ROWTYPE;
          write_receipt_matches integer;
        BEGIN
          IF NEW.resource_type <> 'checker_run' THEN
            RETURN NEW;
          END IF;

          SELECT receipt.* INTO verification
          FROM artifact_verification_receipts receipt
          WHERE receipt.id=NEW.verification_receipt_id;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'checker output binding verified ancestry mismatch'
              USING ERRCODE='23514';
          END IF;

          SELECT value.* INTO job
          FROM artifact_verification_jobs value
          WHERE value.id=verification.verification_job_id
          FOR UPDATE;
          SELECT value.* INTO replica
          FROM artifact_replicas value
          WHERE value.id=job.replica_id
          FOR UPDATE;
          SELECT value.* INTO attempt
          FROM artifact_put_attempts value
          WHERE value.id=job.originating_put_attempt_id
          FOR UPDATE;
          SELECT value.* INTO content
          FROM artifact_contents value
          WHERE value.id=replica.content_id
          FOR SHARE;

          SELECT count(*) INTO write_receipt_matches
          FROM (
            SELECT receipt.id
            FROM artifact_operation_receipts receipt
            WHERE attempt.receipt_id IS NOT NULL
              AND receipt.id=attempt.receipt_id
              AND receipt.put_attempt_id=attempt.id
              AND receipt.replica_id=replica.id
              AND receipt.checker_run_id=attempt.checker_run_id
              AND receipt.logical_role=attempt.logical_role
              AND receipt.request_digest=attempt.request_digest
              AND receipt.provider_object_ref=replica.provider_object_ref
              AND receipt.outcome='stored_pending_verification'
            UNION ALL
            SELECT receipt.id
            FROM artifact_put_observation_receipts receipt
            WHERE attempt.receipt_id IS NULL
              AND receipt.put_attempt_id=attempt.id
              AND receipt.execution_generation=attempt.execution_generation
              AND receipt.outcome='observed_confirmed'
              AND receipt.expected_sha256=attempt.sha256
              AND receipt.observed_sha256=attempt.sha256
              AND receipt.expected_byte_count=attempt.byte_count
              AND receipt.observed_byte_count=attempt.byte_count
          ) successful_write;

          IF job.id IS NULL OR replica.id IS NULL OR attempt.id IS NULL OR content.id IS NULL
             OR NEW.put_attempt_id IS DISTINCT FROM attempt.id
             OR NEW.content_id IS DISTINCT FROM content.id
             OR NEW.project_id IS DISTINCT FROM attempt.project_id
             OR NEW.resource_id IS DISTINCT FROM attempt.checker_run_id::text
             OR NEW.logical_role IS DISTINCT FROM attempt.logical_role
             OR NEW.actor_id IS DISTINCT FROM attempt.producer_ref
             OR NEW.attribution_type IS DISTINCT FROM 'service_identity'
             OR NEW.scope_version <> 1
             OR NEW.supersedes_binding_id IS NOT NULL
             OR attempt.producer_request_type <> 'checker_output'
             OR attempt.producer_type <> 'service_identity'
             OR attempt.submission_id IS NULL OR attempt.submission_version IS NULL
             OR attempt.checker_request_digest IS NULL
             OR attempt.status <> 'object_confirmed'
             OR attempt.replica_id IS DISTINCT FROM replica.id
             OR attempt.storage_namespace_id IS DISTINCT FROM replica.storage_namespace_id
             OR attempt.namespace_fingerprint IS DISTINCT FROM replica.namespace_fingerprint
             OR attempt.canonical_target IS DISTINCT FROM replica.provider_object_ref
             OR attempt.sha256 IS DISTINCT FROM content.sha256
             OR attempt.byte_count IS DISTINCT FROM content.byte_count
             OR attempt.media_type IS DISTINCT FROM content.media_type
             OR job.originating_put_attempt_id IS DISTINCT FROM attempt.id
             OR job.replica_id IS DISTINCT FROM replica.id
             OR job.status <> 'verified'
             OR job.terminal_result_code IS DISTINCT FROM 'verified'
             OR job.terminal_at IS NULL
             OR verification.outcome <> 'verified'
             OR verification.execution_generation IS DISTINCT FROM job.execution_generation
             OR verification.observed_sha256 IS DISTINCT FROM attempt.sha256
             OR verification.observed_byte_count IS DISTINCT FROM attempt.byte_count
             OR replica.verification_state <> 'verified'
             OR replica.availability_state <> 'available'
             OR replica.integrity_state <> 'valid'
             OR write_receipt_matches <> 1 THEN
            RAISE EXCEPTION 'checker output binding verified ancestry mismatch'
              USING ERRCODE='23514';
          END IF;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER checker_output_binding_insert BEFORE INSERT ON artifact_bindings "
        "FOR EACH ROW EXECUTE FUNCTION guard_checker_output_binding_insert()"
    )
    op.execute(
        """
        CREATE FUNCTION seal_checker_output_binding_ancestry() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          verification artifact_verification_receipts%ROWTYPE;
          job artifact_verification_jobs%ROWTYPE;
        BEGIN
          IF NEW.resource_type <> 'checker_run' THEN
            RETURN NEW;
          END IF;
          SELECT receipt.* INTO STRICT verification
          FROM artifact_verification_receipts receipt
          WHERE receipt.id=NEW.verification_receipt_id;
          SELECT value.* INTO STRICT job
          FROM artifact_verification_jobs value
          WHERE value.id=verification.verification_job_id;

          UPDATE artifact_verification_jobs
          SET checker_output_custody_sealed=true
          WHERE id=job.id AND NOT checker_output_custody_sealed;
          UPDATE artifact_replicas
          SET checker_output_custody_sealed=true
          WHERE id=job.replica_id AND NOT checker_output_custody_sealed;
          UPDATE artifact_put_attempts
          SET checker_output_custody_sealed=true
          WHERE id=NEW.put_attempt_id AND NOT checker_output_custody_sealed;
          RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER checker_output_binding_seal AFTER INSERT ON artifact_bindings "
        "FOR EACH ROW EXECUTE FUNCTION seal_checker_output_binding_ancestry()"
    )
    op.execute(
        "CREATE TRIGGER trg_artifact_bindings_no_truncate BEFORE TRUNCATE "
        "ON artifact_bindings FOR EACH STATEMENT "
        "EXECUTE FUNCTION reject_artifact_fact_mutation()"
    )
