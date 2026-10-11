"""Signed callers over actual hidden accepted source facts and exact read audits."""

from uuid import UUID, uuid4

from sqlalchemy import text

from tests.authentication.support import issue_asymmetric_token
from tests.authorization.admin_access.support import SignedActor


async def source_actor(signed, h):
    """Sign the actual identity link already used to create the canonical source."""
    actor_id = h.actor_context.actor_profile_id
    subject = f"human-{actor_id}"
    token = issue_asymmetric_token(signed.private_key, claims={"sub": subject, "jti": str(uuid4())})
    actor = SignedActor(actor_id, subject, token)
    response = await signed.client.get("/api/v1/actors/me", headers=actor.headers)
    assert response.status_code == 200 and response.json()["actor_profile_id"] == str(actor_id)
    return actor


def export_path(project_id):
    return f"/api/v1/projects/{project_id}/contributions/export"


async def export_audits(factory):
    async with factory() as session:
        result = (await session.execute(text("""
            SELECT action_id, permission_id, project_id, resource_type, resource_id,
                   target_ref_kind, target_ref_id, matched_grant_id, after_facts
            FROM public.audit_events WHERE action_id IN ('contribution.read_self','contribution.read_project')
            ORDER BY created_at,id
        """))).mappings()
        return [{key: str(value) if isinstance(value, UUID) else value for key, value in row.items()}
                for row in result]
