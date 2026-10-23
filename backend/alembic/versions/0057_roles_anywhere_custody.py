"""Bind AWS proof and activation evidence to mutable Roles Anywhere state."""

from alembic import op

revision = "0057_roles_anywhere_custody"
down_revision = "0056_manager_authored_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable custody without rewriting retained evidence, then close new inserts."""
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    for statement in _COLUMNS_AND_CONSTRAINTS.split(";"):
        if statement.strip():
            op.get_bind().exec_driver_sql(statement)
    op.execute(_PROBE_GUARD)
    op.execute(_ACTIVATION_GUARD)


def downgrade() -> None:
    """Refuse removal of immutable Roles Anywhere custody."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")


_COLUMNS_AND_CONSTRAINTS = r"""
ALTER TABLE public.artifact_provider_probe_results
 ADD COLUMN roles_anywhere_trust_anchor_arn varchar(700),
 ADD COLUMN roles_anywhere_trust_anchor_sha256 varchar(71),
 ADD COLUMN roles_anywhere_profile_arn varchar(700),
 ADD COLUMN roles_anywhere_profile_sha256 varchar(71);
ALTER TABLE public.artifact_provider_activations
 ADD COLUMN roles_anywhere_trust_anchor_arn varchar(700),
 ADD COLUMN roles_anywhere_trust_anchor_sha256 varchar(71),
 ADD COLUMN roles_anywhere_profile_arn varchar(700),
 ADD COLUMN roles_anywhere_profile_sha256 varchar(71);

ALTER TABLE public.artifact_provider_probe_results
 ADD CONSTRAINT ck_artifact_provider_probe_results_roles_anywhere_custody CHECK (
  (roles_anywhere_trust_anchor_arn IS NULL AND
   roles_anywhere_trust_anchor_sha256 IS NULL AND
   roles_anywhere_profile_arn IS NULL AND roles_anywhere_profile_sha256 IS NULL)
  OR
  (roles_anywhere_trust_anchor_arn IS NOT NULL AND
   roles_anywhere_trust_anchor_sha256 IS NOT NULL AND
   roles_anywhere_trust_anchor_sha256 ~ '^sha256:[0-9a-f]{64}$' AND
   roles_anywhere_profile_arn IS NOT NULL AND
   roles_anywhere_profile_sha256 IS NOT NULL AND
   roles_anywhere_profile_sha256 ~ '^sha256:[0-9a-f]{64}$' AND
   roles_anywhere_trust_anchor_arn ~ ('^arn:' || aws_partition ||
    ':rolesanywhere:' || region || ':' || aws_account_id ||
    ':trust-anchor/[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$') AND
   roles_anywhere_profile_arn ~ ('^arn:' || aws_partition ||
    ':rolesanywhere:' || region || ':' || aws_account_id ||
    ':profile/[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$')));
ALTER TABLE public.artifact_provider_activations
 ADD CONSTRAINT ck_artifact_provider_activations_roles_anywhere_custody CHECK (
  (roles_anywhere_trust_anchor_arn IS NULL AND
   roles_anywhere_trust_anchor_sha256 IS NULL AND
   roles_anywhere_profile_arn IS NULL AND roles_anywhere_profile_sha256 IS NULL)
  OR
  (roles_anywhere_trust_anchor_arn IS NOT NULL AND
   roles_anywhere_trust_anchor_sha256 IS NOT NULL AND
   roles_anywhere_trust_anchor_sha256 ~ '^sha256:[0-9a-f]{64}$' AND
   roles_anywhere_profile_arn IS NOT NULL AND
   roles_anywhere_profile_sha256 IS NOT NULL AND
   roles_anywhere_profile_sha256 ~ '^sha256:[0-9a-f]{64}$' AND
   roles_anywhere_trust_anchor_arn ~ ('^arn:' || aws_partition ||
    ':rolesanywhere:' || region || ':' || aws_account_id ||
    ':trust-anchor/[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$') AND
   roles_anywhere_profile_arn ~ ('^arn:' || aws_partition ||
    ':rolesanywhere:' || region || ':' || aws_account_id ||
    ':profile/[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$')));
"""


_PROBE_GUARD = r"""
CREATE OR REPLACE FUNCTION public.guard_artifact_provider_probe_result() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
 IF TG_OP<>'INSERT' THEN
  RAISE EXCEPTION 'artifact provider probe results are immutable' USING ERRCODE='55000';
 END IF;
 IF NEW.proof_version<>'aws-s3-identity-custody'
  OR NEW.started_at>clock_timestamp()
  OR NEW.completed_at>clock_timestamp()
  OR NEW.expires_at<>NEW.started_at+interval '15 minutes'
  OR octet_length(NEW.expected_principal_arn) NOT BETWEEN 20 AND 700
  OR (NEW.observed_principal_arn IS NOT NULL AND
      octet_length(NEW.observed_principal_arn) NOT BETWEEN 20 AND 700)
  OR NEW.expected_principal_arn<>(CASE NEW.probe_type
      WHEN 'readiness' THEN NEW.readiness_role_arn
      WHEN 'runtime_immutability' THEN NEW.runtime_role_arn
      WHEN 'negative_access' THEN NEW.negative_role_arn
      ELSE NULL
     END)
 THEN
  RAISE EXCEPTION 'artifact provider probe result is invalid' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
"""


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
         readiness.roles_anywhere_trust_anchor_arn,
         readiness.roles_anywhere_trust_anchor_sha256,
         readiness.roles_anywhere_profile_arn,readiness.roles_anywhere_profile_sha256,
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
         runtime.roles_anywhere_trust_anchor_arn,runtime.roles_anywhere_trust_anchor_sha256,
         runtime.roles_anywhere_profile_arn,runtime.roles_anywhere_profile_sha256,
         runtime.bootstrap_principal_arn,
         runtime.bucket_policy_sha256,runtime.group_nonce)
  OR ROW(readiness.proof_version,readiness.release_id,readiness.namespace_fingerprint,
         readiness.aws_partition,readiness.aws_account_id,readiness.region,
         readiness.runtime_role_arn,readiness.runtime_trust_policy_sha256,
         readiness.runtime_policy_arn,
         readiness.readiness_role_arn,readiness.readiness_trust_policy_sha256,
         readiness.readiness_policy_arn,
         readiness.negative_role_arn,readiness.negative_trust_policy_sha256,
         readiness.roles_anywhere_trust_anchor_arn,
         readiness.roles_anywhere_trust_anchor_sha256,
         readiness.roles_anywhere_profile_arn,readiness.roles_anywhere_profile_sha256,
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
         negative.roles_anywhere_trust_anchor_arn,negative.roles_anywhere_trust_anchor_sha256,
         negative.roles_anywhere_profile_arn,negative.roles_anywhere_profile_sha256,
         negative.bootstrap_principal_arn,
         negative.bucket_policy_sha256,negative.group_nonce)
  OR ROW(NEW.proof_version,NEW.release_id,NEW.namespace_fingerprint,
         NEW.aws_partition,NEW.aws_account_id,NEW.region,
         NEW.runtime_role_arn,NEW.runtime_trust_policy_sha256,NEW.runtime_policy_arn,
         NEW.readiness_role_arn,NEW.readiness_trust_policy_sha256,
         NEW.readiness_policy_arn,
         NEW.negative_role_arn,NEW.negative_trust_policy_sha256,
         NEW.roles_anywhere_trust_anchor_arn,NEW.roles_anywhere_trust_anchor_sha256,
         NEW.roles_anywhere_profile_arn,NEW.roles_anywhere_profile_sha256,
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
         readiness.roles_anywhere_trust_anchor_arn,
         readiness.roles_anywhere_trust_anchor_sha256,
         readiness.roles_anywhere_profile_arn,readiness.roles_anywhere_profile_sha256,
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
             predecessor.roles_anywhere_trust_anchor_arn,
             predecessor.roles_anywhere_trust_anchor_sha256,
             predecessor.roles_anywhere_profile_arn,
             predecessor.roles_anywhere_profile_sha256,
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
             NEW.roles_anywhere_trust_anchor_arn,NEW.roles_anywhere_trust_anchor_sha256,
             NEW.roles_anywhere_profile_arn,NEW.roles_anywhere_profile_sha256,
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
