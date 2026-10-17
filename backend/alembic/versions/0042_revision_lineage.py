"""Keep completed attempt lineage while allowing a later Task context rebase.

The current Task stamp is checked when each attempt row is inserted. Retained
attempts then refer to immutable source rows rather than the mutable Task stamp.
"""

from alembic import op


revision = "0042_revision_lineage"
down_revision = "0041_checker_revision_cap"
branch_labels = None
depends_on = None


_MUTABLE_TASK_FKS = {
    "submissions": (
        "fk_submissions_task_locked_guide",
        "fk_submissions_task_locked_post_submit_policy_hash",
        "fk_submissions_task_locked_review_policy",
        "fk_submissions_task_locked_revision_policy",
        "fk_submissions_task_locked_source_snapshot_hash",
        "fk_submissions_task_locked_effective_policy_hash",
        "fk_submissions_task_locked_pre_submit_checker_hash",
    ),
    "checker_runs": (
        "fk_checker_runs_task_locked_guide",
        "fk_checker_runs_task_locked_review_policy",
        "fk_checker_runs_task_locked_revision_policy",
    ),
    "pre_submit_evidence_sets": (
        "fk_pre_submit_evidence_task_guide",
        "fk_pre_submit_evidence_task_source_snapshot",
        "fk_pre_submit_evidence_task_artifact_policy",
        "fk_pre_submit_evidence_task_checker_policy",
    ),
}


def upgrade() -> None:
    for table, names in _MUTABLE_TASK_FKS.items():
        for name in names:
            op.drop_constraint(name, table, schema="public", type_="foreignkey")

    op.create_foreign_key(
        "fk_submissions_review_policy_lineage",
        "submissions", "review_policies",
        ["locked_review_policy_id", "locked_review_policy_generation", "locked_review_policy_hash"],
        ["id", "policy_generation", "policy_hash"],
        source_schema="public", referent_schema="public",
    )
    op.create_foreign_key(
        "fk_submissions_revision_policy_lineage",
        "submissions", "revision_policies",
        ["locked_revision_policy_id", "locked_revision_policy_generation", "locked_revision_policy_hash"],
        ["id", "policy_generation", "policy_hash"],
        source_schema="public", referent_schema="public",
    )
    op.create_foreign_key(
        "fk_checker_runs_review_policy_lineage",
        "checker_runs", "review_policies",
        ["project_id", "locked_guide_version", "locked_review_policy_id",
         "locked_review_policy_generation", "locked_review_policy_hash"],
        ["project_id", "guide_version", "id", "policy_generation", "policy_hash"],
        source_schema="public", referent_schema="public",
    )
    op.create_foreign_key(
        "fk_checker_runs_revision_policy_lineage",
        "checker_runs", "revision_policies",
        ["project_id", "locked_guide_version", "locked_revision_policy_id",
         "locked_revision_policy_generation", "locked_revision_policy_hash"],
        ["project_id", "guide_version", "id", "policy_generation", "policy_hash"],
        source_schema="public", referent_schema="public",
    )
    op.create_foreign_key(
        "fk_pre_submit_evidence_source_snapshot_hash",
        "pre_submit_evidence_sets", "guide_source_snapshots",
        ["source_snapshot_id", "source_snapshot_sha256"], ["id", "bundle_hash"],
        source_schema="public", referent_schema="public",
    )
    op.create_foreign_key(
        "fk_pre_submit_evidence_effective_policy_hash",
        "pre_submit_evidence_sets", "effective_project_submission_artifact_policies",
        ["effective_policy_id", "locked_artifact_policy_sha256"],
        ["id", "effective_policy_hash"],
        source_schema="public", referent_schema="public",
    )
    op.create_foreign_key(
        "fk_pre_submit_evidence_checker_policy_hash",
        "pre_submit_evidence_sets", "pre_submit_checker_policies",
        ["pre_submit_policy_id", "locked_checker_policy_sha256"],
        ["id", "compiled_bundle_hash"],
        source_schema="public", referent_schema="public",
    )

    # A trigger name preceding existing INSERT triggers takes TASK custody first.
    # All three guards are INSERT-only: no historical row depends on the mutable
    # Task lock after insertion, and their existing immutability guards remain.
    op.execute("""
    CREATE FUNCTION public.require_new_submission_task_stamps() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
    DECLARE t public.workstream_tasks%ROWTYPE;
    BEGIN
      SELECT * INTO t FROM public.workstream_tasks WHERE id=NEW.task_id FOR UPDATE;
      IF NOT FOUND OR
        ROW(NEW.locked_guide_version, NEW.locked_post_submit_checker_policy_id,
            NEW.locked_post_submit_checker_policy_version,
            NEW.locked_post_submit_checker_policy_hash,
            NEW.locked_post_submit_checker_policy_body::jsonb,
            NEW.locked_review_policy_id, NEW.locked_review_policy_generation,
            NEW.locked_review_policy_hash, NEW.locked_revision_policy_id,
            NEW.locked_revision_policy_generation, NEW.locked_revision_policy_hash,
            NEW.locked_guide_source_snapshot_id, NEW.locked_guide_source_snapshot_hash,
            NEW.locked_effective_project_submission_artifact_policy_id,
            NEW.locked_effective_project_submission_artifact_policy_hash,
            NEW.locked_pre_submit_checker_policy_id, NEW.locked_pre_submit_checker_bundle_hash,
            NEW.contribution_policy_version_id)
        IS DISTINCT FROM
        ROW(t.locked_guide_version, t.locked_post_submit_checker_policy_id,
            t.locked_post_submit_checker_policy_version,
            t.locked_post_submit_checker_policy_hash,
            t.locked_post_submit_checker_policy_body::jsonb,
            t.locked_review_policy_id, t.locked_review_policy_generation,
            t.locked_review_policy_hash, t.locked_revision_policy_id,
            t.locked_revision_policy_generation, t.locked_revision_policy_hash,
            t.locked_guide_source_snapshot_id, t.locked_guide_source_snapshot_hash,
            t.locked_effective_project_submission_artifact_policy_id,
            t.locked_effective_project_submission_artifact_policy_hash,
            t.locked_pre_submit_checker_policy_id, t.locked_pre_submit_checker_bundle_hash,
            t.locked_contribution_policy_version_id)
      THEN RAISE EXCEPTION 'submission task context differs' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    """)
    op.execute("""
    CREATE TRIGGER a_revision_submission_task_stamps
      BEFORE INSERT ON public.submissions FOR EACH ROW
      EXECUTE FUNCTION public.require_new_submission_task_stamps();
    """)
    op.execute("""
    CREATE FUNCTION public.require_new_checker_task_stamps() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
    DECLARE t public.workstream_tasks%ROWTYPE; s public.submissions%ROWTYPE;
    BEGIN
      SELECT * INTO t FROM public.workstream_tasks
      WHERE id=NEW.task_id AND project_id=NEW.project_id FOR UPDATE;
      IF NOT FOUND THEN
        RAISE EXCEPTION 'checker task context differs' USING ERRCODE='23514';
      END IF;
      SELECT * INTO s FROM public.submissions
      WHERE id=NEW.submission_id AND task_id=NEW.task_id;
      IF NOT FOUND OR s.version IS DISTINCT FROM NEW.submission_version OR
        ROW(NEW.locked_guide_version, NEW.locked_post_submit_checker_policy_id,
            NEW.locked_post_submit_checker_policy_version,
            NEW.locked_post_submit_checker_policy_hash,
            NEW.locked_review_policy_id, NEW.locked_review_policy_generation,
            NEW.locked_review_policy_hash, NEW.locked_revision_policy_id,
            NEW.locked_revision_policy_generation, NEW.locked_revision_policy_hash)
        IS DISTINCT FROM
        ROW(s.locked_guide_version, s.locked_post_submit_checker_policy_id,
            s.locked_post_submit_checker_policy_version,
            s.locked_post_submit_checker_policy_hash,
            s.locked_review_policy_id, s.locked_review_policy_generation,
            s.locked_review_policy_hash, s.locked_revision_policy_id,
            s.locked_revision_policy_generation, s.locked_revision_policy_hash) OR
        ROW(NEW.locked_guide_version, NEW.locked_review_policy_id,
            NEW.locked_review_policy_generation, NEW.locked_review_policy_hash,
            NEW.locked_revision_policy_id, NEW.locked_revision_policy_generation,
            NEW.locked_revision_policy_hash)
        IS DISTINCT FROM
        ROW(t.locked_guide_version, t.locked_review_policy_id,
            t.locked_review_policy_generation, t.locked_review_policy_hash,
            t.locked_revision_policy_id, t.locked_revision_policy_generation,
            t.locked_revision_policy_hash)
      THEN RAISE EXCEPTION 'checker task context differs' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    """)
    op.execute("""
    CREATE TRIGGER a_revision_checker_task_stamps
      BEFORE INSERT ON public.checker_runs FOR EACH ROW
      EXECUTE FUNCTION public.require_new_checker_task_stamps();
    """)
    op.execute("""
    CREATE FUNCTION public.require_new_pre_submit_task_stamps() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
    DECLARE t public.workstream_tasks%ROWTYPE;
    BEGIN
      SELECT * INTO t FROM public.workstream_tasks
      WHERE id=NEW.task_id AND project_id=NEW.project_id FOR UPDATE;
      IF NOT FOUND OR
        ROW(NEW.guide_version, NEW.source_snapshot_id, NEW.source_snapshot_sha256,
            NEW.effective_policy_id, NEW.locked_artifact_policy_sha256,
            NEW.pre_submit_policy_id, NEW.locked_checker_policy_sha256)
        IS DISTINCT FROM
        ROW(t.locked_guide_version, t.locked_guide_source_snapshot_id,
            t.locked_guide_source_snapshot_hash,
            t.locked_effective_project_submission_artifact_policy_id,
            t.locked_effective_project_submission_artifact_policy_hash,
            t.locked_pre_submit_checker_policy_id, t.locked_pre_submit_checker_bundle_hash)
      THEN RAISE EXCEPTION 'pre-submit task context differs' USING ERRCODE='23514'; END IF;
      RETURN NEW;
    END $$;
    """)
    op.execute("""
    CREATE TRIGGER a_revision_pre_submit_task_stamps
      BEFORE INSERT ON public.pre_submit_evidence_sets FOR EACH ROW
      EXECUTE FUNCTION public.require_new_pre_submit_task_stamps();
    """)


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
