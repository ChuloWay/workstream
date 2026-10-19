"""Bound new AWS activation proof sequences using authoritative database time."""

from alembic import op

revision = "0054_artifact_proof_timing"
down_revision = "0053_project_reads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Replace the existing insert guard without rewriting retained proof rows."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    op.execute(_ACTIVATION_GUARD)


def downgrade() -> None:
    """Refuse removal of the live activation-custody guarantee."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")


_ACTIVATION_GUARD = r"""
CREATE OR REPLACE FUNCTION public.guard_artifact_provider_activation() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE readiness public.artifact_provider_probe_results%ROWTYPE;
 runtime public.artifact_provider_probe_results%ROWTYPE;
 negative public.artifact_provider_probe_results%ROWTYPE;
 predecessor public.artifact_provider_activations%ROWTYPE;
BEGIN
 IF TG_OP<>'INSERT' THEN
  RAISE EXCEPTION 'artifact provider activations are immutable' USING ERRCODE='55000';
 END IF;
 SELECT * INTO readiness FROM public.artifact_provider_probe_results
  WHERE id=NEW.readiness_result_id FOR SHARE;
 SELECT * INTO runtime FROM public.artifact_provider_probe_results
  WHERE id=NEW.runtime_result_id FOR SHARE;
 SELECT * INTO negative FROM public.artifact_provider_probe_results
  WHERE id=NEW.negative_result_id FOR SHARE;
 IF NEW.supersedes_activation_id IS NOT NULL THEN
  SELECT * INTO predecessor FROM public.artifact_provider_activations
   WHERE id=NEW.supersedes_activation_id FOR SHARE;
 END IF;
 IF readiness.id IS NULL OR runtime.id IS NULL OR negative.id IS NULL
  OR readiness.probe_type<>'readiness'
  OR runtime.probe_type<>'runtime_immutability'
  OR negative.probe_type<>'negative_access'
  OR readiness.result<>'pass' OR runtime.result<>'pass' OR negative.result<>'pass'
  OR readiness.expected_principal_arn<>readiness.observed_principal_arn
  OR runtime.expected_principal_arn<>runtime.observed_principal_arn
  OR negative.expected_principal_arn<>negative.observed_principal_arn
  OR runtime.completed_at>readiness.started_at
  OR runtime.completed_at>negative.started_at
  OR ROW(readiness.proof_version,readiness.release_id,readiness.namespace_fingerprint,
         readiness.aws_partition,readiness.aws_account_id,readiness.region,
         readiness.runtime_role_arn,readiness.runtime_trust_policy_sha256,
         readiness.runtime_policy_arn,
         readiness.readiness_role_arn,readiness.readiness_trust_policy_sha256,
         readiness.readiness_policy_arn,
         readiness.negative_role_arn,readiness.negative_trust_policy_sha256,
         readiness.bootstrap_principal_arn,
         readiness.bucket_policy_sha256,readiness.group_nonce)
     IS DISTINCT FROM
     ROW(runtime.proof_version,runtime.release_id,runtime.namespace_fingerprint,
         runtime.aws_partition,runtime.aws_account_id,runtime.region,
         runtime.runtime_role_arn,runtime.runtime_trust_policy_sha256,
         runtime.runtime_policy_arn,
         runtime.readiness_role_arn,runtime.readiness_trust_policy_sha256,
         runtime.readiness_policy_arn,
         runtime.negative_role_arn,runtime.negative_trust_policy_sha256,
         runtime.bootstrap_principal_arn,
         runtime.bucket_policy_sha256,runtime.group_nonce)
  OR ROW(readiness.proof_version,readiness.release_id,readiness.namespace_fingerprint,
         readiness.aws_partition,readiness.aws_account_id,readiness.region,
         readiness.runtime_role_arn,readiness.runtime_trust_policy_sha256,
         readiness.runtime_policy_arn,
         readiness.readiness_role_arn,readiness.readiness_trust_policy_sha256,
         readiness.readiness_policy_arn,
         readiness.negative_role_arn,readiness.negative_trust_policy_sha256,
         readiness.bootstrap_principal_arn,
         readiness.bucket_policy_sha256,readiness.group_nonce)
     IS DISTINCT FROM
     ROW(negative.proof_version,negative.release_id,negative.namespace_fingerprint,
         negative.aws_partition,negative.aws_account_id,negative.region,
         negative.runtime_role_arn,negative.runtime_trust_policy_sha256,
         negative.runtime_policy_arn,
         negative.readiness_role_arn,negative.readiness_trust_policy_sha256,
         negative.readiness_policy_arn,
         negative.negative_role_arn,negative.negative_trust_policy_sha256,
         negative.bootstrap_principal_arn,
         negative.bucket_policy_sha256,negative.group_nonce)
  OR ROW(NEW.proof_version,NEW.release_id,NEW.namespace_fingerprint,
         NEW.aws_partition,NEW.aws_account_id,NEW.region,
         NEW.runtime_role_arn,NEW.runtime_trust_policy_sha256,NEW.runtime_policy_arn,
         NEW.readiness_role_arn,NEW.readiness_trust_policy_sha256,
         NEW.readiness_policy_arn,
         NEW.negative_role_arn,NEW.negative_trust_policy_sha256,
         NEW.bootstrap_principal_arn,
         NEW.bucket_policy_sha256,NEW.group_nonce)
     IS DISTINCT FROM
     ROW(readiness.proof_version,readiness.release_id,readiness.namespace_fingerprint,
         readiness.aws_partition,readiness.aws_account_id,readiness.region,
         readiness.runtime_role_arn,readiness.runtime_trust_policy_sha256,
         readiness.runtime_policy_arn,
         readiness.readiness_role_arn,readiness.readiness_trust_policy_sha256,
         readiness.readiness_policy_arn,
         readiness.negative_role_arn,readiness.negative_trust_policy_sha256,
         readiness.bootstrap_principal_arn,
         readiness.bucket_policy_sha256,readiness.group_nonce)
  OR NEW.activated_at>clock_timestamp()
  OR NEW.expires_at<>least(readiness.expires_at,runtime.expires_at,negative.expires_at)
  OR NEW.expires_at<=clock_timestamp()
  OR (NEW.supersedes_activation_id IS NOT NULL AND (
      predecessor.id IS NULL
      OR predecessor.activated_at>=NEW.activated_at
      OR ROW(predecessor.proof_version,predecessor.release_id,
             predecessor.namespace_fingerprint,predecessor.aws_partition,
             predecessor.aws_account_id,predecessor.region,
             predecessor.runtime_role_arn,predecessor.runtime_trust_policy_sha256,
             predecessor.runtime_policy_arn,
             predecessor.readiness_role_arn,predecessor.readiness_trust_policy_sha256,
             predecessor.readiness_policy_arn,
             predecessor.negative_role_arn,predecessor.negative_trust_policy_sha256,
             predecessor.bootstrap_principal_arn,
             predecessor.bucket_policy_sha256)
         IS DISTINCT FROM
         ROW(NEW.proof_version,NEW.release_id,
             NEW.namespace_fingerprint,NEW.aws_partition,
             NEW.aws_account_id,NEW.region,
             NEW.runtime_role_arn,NEW.runtime_trust_policy_sha256,
             NEW.runtime_policy_arn,
             NEW.readiness_role_arn,NEW.readiness_trust_policy_sha256,
             NEW.readiness_policy_arn,
             NEW.negative_role_arn,NEW.negative_trust_policy_sha256,
             NEW.bootstrap_principal_arn,
             NEW.bucket_policy_sha256)))
 THEN
  RAISE EXCEPTION 'artifact provider activation proof group is invalid' USING ERRCODE='23514';
 END IF;
 IF clock_timestamp()-runtime.started_at>interval '120 seconds' THEN
  RAISE EXCEPTION 'artifact provider proof sequence exceeded fixed allowance'
   USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
"""
