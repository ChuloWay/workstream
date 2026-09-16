"""Bind initial work to exact activated contribution policy custody."""

from alembic import op
import sqlalchemy as sa

revision = "0024_task_policy_lineage"
down_revision = "0023_guide_activation_custody"
branch_labels = None
depends_on = None


_TASK_GUARD = """
CREATE FUNCTION protect_task_contribution_stamp() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'draft' OR NEW.locked_contribution_policy_version_id IS NOT NULL THEN
            RAISE EXCEPTION 'task contribution stamp requires initial screening';
        END IF;
    ELSIF NEW.locked_contribution_policy_version_id IS DISTINCT FROM
          OLD.locked_contribution_policy_version_id THEN
        IF OLD.locked_contribution_policy_version_id IS NOT NULL OR
           OLD.status <> 'draft' OR NEW.status <> 'screening' OR
           NEW.locked_contribution_policy_version_id IS NULL THEN
            RAISE EXCEPTION 'task contribution stamp is immutable';
        END IF;
    END IF;
    RETURN NEW;
END $$
"""
_ASSIGNMENT_GUARD = """
CREATE FUNCTION protect_assignment_contribution_stamp() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE task_stamp uuid;
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT locked_contribution_policy_version_id INTO task_stamp FROM workstream_tasks
        WHERE id=NEW.task_id AND project_id=NEW.project_id FOR SHARE;
        IF task_stamp IS NULL OR task_stamp IS DISTINCT FROM
           NEW.submitter_contribution_policy_version_id THEN
            RAISE EXCEPTION 'assignment contribution stamp differs from task';
        END IF;
    ELSIF ROW(NEW.id, NEW.task_id, NEW.project_id, NEW.contributor_id,
              NEW.submitter_contribution_policy_version_id) IS DISTINCT FROM
              ROW(OLD.id, OLD.task_id, OLD.project_id, OLD.contributor_id,
                  OLD.submitter_contribution_policy_version_id) THEN
        RAISE EXCEPTION 'assignment contribution identity is immutable';
    END IF;
    RETURN NEW;
END $$
"""
_SUBMISSION_GUARD = """
CREATE FUNCTION require_submission_contribution_stamp() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE assignment_stamp uuid;
BEGIN
    SELECT submitter_contribution_policy_version_id INTO assignment_stamp
    FROM task_assignments WHERE id=NEW.task_assignment_id AND task_id=NEW.task_id
        AND contributor_id=NEW.contributor_id FOR SHARE;
    IF assignment_stamp IS NULL OR assignment_stamp IS DISTINCT FROM
       NEW.contribution_policy_version_id THEN
        RAISE EXCEPTION 'submission contribution stamp differs from assignment';
    END IF;
    RETURN NEW;
END $$
"""
_SUBMISSION_UPDATE_GUARD = """
CREATE FUNCTION protect_submission_contribution_stamp() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.id, NEW.task_id, NEW.task_assignment_id, NEW.contributor_id, NEW.contribution_policy_version_id)
       IS DISTINCT FROM ROW(OLD.id, OLD.task_id, OLD.task_assignment_id, OLD.contributor_id, OLD.contribution_policy_version_id)
       OR (OLD.submission_bundle_admission_id IS NOT NULL AND
           ROW(NEW.task_assignment_id, NEW.submission_bundle_admission_id,
               NEW.artifact_binding_id, NEW.artifact_content_id) IS DISTINCT FROM
           ROW(OLD.task_assignment_id, OLD.submission_bundle_admission_id,
               OLD.artifact_binding_id, OLD.artifact_content_id)) THEN
        RAISE EXCEPTION 'submission contribution identity is immutable';
    END IF;
    RETURN NEW;
END $$
"""


def _lock_work() -> None:
    op.execute(
        "LOCK TABLE workstream_tasks, task_assignments, submissions, checker_runs "
        "IN ACCESS EXCLUSIVE MODE"
    )


def _exists(predicate: str) -> bool:
    return bool(op.get_bind().scalar(sa.text("SELECT " + predicate)))


def upgrade() -> None:
    """Refuse unprovable retained attempts before adding any schema or row data."""
    _lock_work()
    if _exists(
        "EXISTS(SELECT 1 FROM workstream_tasks WHERE status <> 'draft') OR "
        "EXISTS(SELECT 1 FROM task_assignments) OR EXISTS(SELECT 1 FROM submissions)"
    ):
        raise RuntimeError("CP08 cannot infer retained attempt contribution policy lineage")
    op.add_column("workstream_tasks", sa.Column("locked_contribution_policy_version_id", sa.Uuid()))
    op.add_column("task_assignments", sa.Column("project_id", sa.String(36), nullable=False))
    op.add_column(
        "task_assignments",
        sa.Column("submitter_contribution_policy_version_id", sa.Uuid(), nullable=False),
    )
    op.add_column(
        "submissions", sa.Column("contribution_policy_version_id", sa.Uuid(), nullable=False)
    )
    op.alter_column(
        "submissions", "task_assignment_id", existing_type=sa.String(36), nullable=False
    )
    op.drop_constraint(op.f("ck_submissions_artifact_lineage_shape"), "submissions")
    op.create_check_constraint(
        op.f("ck_submissions_artifact_lineage_shape"),
        "submissions",
        "(submission_bundle_admission_id is null and artifact_binding_id is null and artifact_content_id is null) or "
        "(submission_bundle_admission_id is not null and artifact_binding_id is not null and artifact_content_id is not null)",
    )
    for table in ("submissions", "checker_runs"):
        op.alter_column(
            table, "locked_payment_policy_version", existing_type=sa.String(50), nullable=True
        )
    op.create_unique_constraint(
        "uq_guides_project_version_contribution",
        "project_guides",
        ["project_id", "version", "contribution_policy_version_id"],
    )
    op.create_check_constraint(
        op.f("ck_workstream_tasks_contribution_policy_required"),
        "workstream_tasks",
        "status = 'draft' or locked_contribution_policy_version_id is not null",
    )
    op.create_check_constraint(
        op.f("ck_workstream_tasks_contribution_policy_guide_required"),
        "workstream_tasks",
        "locked_contribution_policy_version_id is null or locked_guide_version is not null",
    )
    op.create_foreign_key(
        "fk_tasks_guide_contribution_policy",
        "workstream_tasks",
        "project_guides",
        ["project_id", "locked_guide_version", "locked_contribution_policy_version_id"],
        ["project_id", "version", "contribution_policy_version_id"],
    )
    op.create_foreign_key(
        "fk_assignments_task_project",
        "task_assignments",
        "workstream_tasks",
        ["task_id", "project_id"],
        ["id", "project_id"],
    )
    op.create_foreign_key(
        "fk_assignments_contribution_project",
        "task_assignments",
        "contribution_policy_versions",
        ["submitter_contribution_policy_version_id", "project_id"],
        ["id", "project_id"],
    )
    op.create_foreign_key(
        "fk_submissions_assignment_identity",
        "submissions",
        "task_assignments",
        ["task_assignment_id", "task_id", "contributor_id"],
        ["id", "task_id", "contributor_id"],
    )
    for statement in (_TASK_GUARD, _ASSIGNMENT_GUARD, _SUBMISSION_GUARD, _SUBMISSION_UPDATE_GUARD):
        op.execute(statement)
    op.execute(
        "CREATE TRIGGER task_contribution_stamp BEFORE INSERT OR UPDATE ON workstream_tasks "
        "FOR EACH ROW EXECUTE FUNCTION protect_task_contribution_stamp()"
    )
    op.execute(
        "CREATE TRIGGER assignment_contribution_stamp BEFORE INSERT OR UPDATE ON task_assignments "
        "FOR EACH ROW EXECUTE FUNCTION protect_assignment_contribution_stamp()"
    )
    op.execute(
        "CREATE TRIGGER submission_contribution_immutable BEFORE UPDATE ON submissions "
        "FOR EACH ROW EXECUTE FUNCTION protect_submission_contribution_stamp()"
    )
    op.execute(
        "CREATE TRIGGER submission_contribution_stamp BEFORE INSERT ON submissions "
        "FOR EACH ROW "
        "EXECUTE FUNCTION require_submission_contribution_stamp()"
    )


def downgrade() -> None:
    """Never discard contribution stamps or invalidate retained payment evidence."""
    _lock_work()
    if _exists(
        "EXISTS(SELECT 1 FROM workstream_tasks WHERE locked_contribution_policy_version_id IS NOT NULL) OR "
        "EXISTS(SELECT 1 FROM task_assignments) OR EXISTS(SELECT 1 FROM submissions) OR "
        "EXISTS(SELECT 1 FROM checker_runs WHERE locked_payment_policy_version IS NULL)"
    ):
        raise RuntimeError("CP08 contribution or payment evidence prevents downgrade")
    for table, trigger, function in (
        ("submissions", "submission_contribution_stamp", "require_submission_contribution_stamp"),
        (
            "submissions",
            "submission_contribution_immutable",
            "protect_submission_contribution_stamp",
        ),
        (
            "task_assignments",
            "assignment_contribution_stamp",
            "protect_assignment_contribution_stamp",
        ),
        ("workstream_tasks", "task_contribution_stamp", "protect_task_contribution_stamp"),
    ):
        op.execute(f"DROP TRIGGER {trigger} ON {table}")
        op.execute(f"DROP FUNCTION {function}()")
    for table, constraint in (
        ("submissions", "fk_submissions_assignment_identity"),
        ("task_assignments", "fk_assignments_contribution_project"),
        ("task_assignments", "fk_assignments_task_project"),
        ("workstream_tasks", "fk_tasks_guide_contribution_policy"),
        ("workstream_tasks", "ck_workstream_tasks_contribution_policy_required"),
        ("workstream_tasks", "ck_workstream_tasks_contribution_policy_guide_required"),
        ("project_guides", "uq_guides_project_version_contribution"),
    ):
        op.drop_constraint(op.f(constraint), table)
    for table, column in (
        ("submissions", "contribution_policy_version_id"),
        ("task_assignments", "submitter_contribution_policy_version_id"),
        ("task_assignments", "project_id"),
        ("workstream_tasks", "locked_contribution_policy_version_id"),
    ):
        op.drop_column(table, column)
    op.alter_column("submissions", "task_assignment_id", existing_type=sa.String(36), nullable=True)
    op.drop_constraint(op.f("ck_submissions_artifact_lineage_shape"), "submissions")
    op.create_check_constraint(
        op.f("ck_submissions_artifact_lineage_shape"),
        "submissions",
        "(task_assignment_id is null and submission_bundle_admission_id is null and artifact_binding_id is null and artifact_content_id is null) or "
        "(task_assignment_id is not null and submission_bundle_admission_id is not null and artifact_binding_id is not null and artifact_content_id is not null)",
    )
    for table in ("submissions", "checker_runs"):
        op.alter_column(
            table, "locked_payment_policy_version", existing_type=sa.String(50), nullable=False
        )
