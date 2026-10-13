"""Admit exact covered false-review guides through canonical activation custody."""

from alembic import op
import sqlalchemy as sa


revision = "0039_false_guide_activation"
down_revision = "0038_task_batch_transitions"
branch_labels = None
depends_on = None


_SIGNATURE = "public.require_guide_activation_custody(uuid, boolean)"
_LIFECYCLE_SIGNATURE = "public.joint_lifecycle_transition_valid(public.joint_lifecycle_transitions)"
_OLD_MANIFEST = "sha256:f7385c3930e0a3fc60a55e4a35c67b00c1bd3056ffa89a1e09ecae4b736c3ab4"
_NEW_MANIFEST = "sha256:3a6704c3c79c243f5a032f2db9c4f47080716dfef86928f53e0f20b4d6047273"
_OLD = """OR NOT EXISTS(SELECT 1 FROM review_policies p WHERE p.id=g.selected_review_policy_id
                  AND p.semantics_status='complete' AND p.human_review_required=true)"""
_NEW = """OR NOT EXISTS(SELECT 1 FROM review_policies p WHERE p.id=g.selected_review_policy_id
                  AND p.semantics_status='complete'
                  AND (p.human_review_required=true OR (
                    p.human_review_required=false AND p.semantics_format='v2'
                    AND EXISTS(SELECT 1 FROM public.project_guide_compilations c
                      WHERE c.id=(target->'proposal'->>'compilation_id')::uuid
                        AND c.project_id=g.project_id AND c.guide_id=g.id
                        AND c.guide_version=g.version
                        AND c.result_hash=target->'proposal'->>'result_hash'
                        AND c.component_hashes::jsonb=target->'proposal'->'component_hashes'
                        AND CASE
                          WHEN jsonb_typeof(c.canonical_result::jsonb->'requirements')='array'
                          THEN NOT EXISTS(
                            SELECT 1 FROM jsonb_array_elements(
                              c.canonical_result::jsonb->'requirements'
                            ) AS requirement(value)
                            WHERE jsonb_typeof(requirement.value) IS DISTINCT FROM 'object'
                               OR jsonb_typeof(requirement.value->'disposition') IS DISTINCT FROM 'string'
                               OR requirement.value->>'disposition'='human_review'
                          )
                          ELSE false
                        END
                    )
                  )))"""


def upgrade() -> None:
    op.execute("SET LOCAL search_path=pg_catalog,public,pg_temp")
    body = op.get_bind().execute(sa.text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": _SIGNATURE}).scalar_one()
    if body.count(_OLD) != 1 or _NEW in body:
        raise RuntimeError("guide activation custody predecessor changed")
    op.execute(body.replace(_OLD, _NEW))
    op.execute(
        "ALTER FUNCTION public.require_guide_activation_custody(uuid, boolean) "
        "SET search_path=pg_catalog,public,pg_temp"
    )
    lifecycle = op.get_bind().execute(sa.text(
        "SELECT pg_catalog.pg_get_functiondef(CAST(:signature AS regprocedure))"
    ), {"signature": _LIFECYCLE_SIGNATURE}).scalar_one()
    if lifecycle.count(_OLD_MANIFEST) != 2 or _NEW_MANIFEST in lifecycle:
        raise RuntimeError("review lifecycle manifest predecessor changed")
    op.execute(lifecycle.replace(_OLD_MANIFEST, _NEW_MANIFEST))


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
