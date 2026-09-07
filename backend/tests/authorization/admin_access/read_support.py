"""Fresh stored targets and explicit public projections for administrative reads."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.api import ServiceIdentity
from tests.authorization.admin_access.support import AdminAccess

PROFILE_FIELDS = {
    "actor_profile_id",
    "actor_kind",
    "status",
    "provisioning_method",
    "service_identity",
    "display_name",
    "created_at",
    "updated_at",
    "last_seen_at",
    "suspended_at",
    "reactivated_at",
    "deactivated_at",
}
LINK_FIELDS = {
    "identity_link_id",
    "actor_profile_id",
    "subject_kind",
    "status",
    "linked_at",
    "last_verified_at",
    "revoked_at",
    "reactivated_at",
}
READ_ACTIONS = {
    "profile": ("actor.profile.read", "actor.profile.read_any"),
    "link": ("actor.identity_link.read", "actor.identity_link.read"),
}


def read_path(actor_id: UUID, surface: str) -> str:
    assert surface in READ_ACTIONS
    return f"/api/v1/actors/{actor_id}" + ("/identity-links" if surface == "link" else "")


@dataclass(frozen=True)
class ReadTarget:
    id: UUID
    private_values: tuple[str, ...]


async def seed_read_target(access: AdminAccess, kind: str) -> ReadTarget:
    """Create valid fresh rows; no lifecycle trigger is disabled or state reset."""
    assert kind in {"human", "service", "suspended", "revoked_link"}
    email = "private-contact@example.test"
    if kind == "human":
        async with db_session.get_session_factory()() as session:
            profile = await session.get(ActorProfile, str(access.target.id))
            assert profile is not None
            profile.contact_email = email
            await session.commit()
        return ReadTarget(
            access.target.id,
            (
                email,
                access.target.subject,
                access.target.token,
                access.admin.token,
                access.bootstrap_grant_id,
                "https://identity.test",
            ),
        )
    actor_id = uuid4()
    subject = f"private-{kind}-{uuid4()}"
    provenance = str(uuid4())
    reason = "Private lifecycle reason"
    now = datetime.now(UTC)
    actor_kind = "service" if kind == "service" else "human"
    profile = ActorProfile(
        id=str(actor_id),
        actor_kind=actor_kind,
        status="suspended" if kind == "suspended" else "active",
        provisioning_method=(
            "manual_service_provisioning" if kind == "service" else "automatic_first_access"
        ),
        service_identity=ServiceIdentity.ARTIFACT_VERIFIER.value if kind == "service" else None,
        created_by=provenance,
    )
    if kind == "suspended":
        profile.suspended_by = provenance
        profile.suspended_at = now
        profile.suspension_reason = reason
    link = ActorIdentityLink(
        id=str(uuid4()),
        actor_profile_id=str(actor_id),
        issuer="https://identity.test",
        subject=subject,
        subject_kind=actor_kind,
        status="revoked" if kind == "revoked_link" else "active",
        linked_by=provenance,
        last_verified_at=None if kind == "service" else now,
    )
    if kind == "revoked_link":
        link.revoked_by = provenance
        link.revoked_at = now
        link.revoked_reason = reason
    async with db_session.get_session_factory()() as session:
        session.add(profile)
        await session.flush()
        session.add(link)
        await session.commit()
    return ReadTarget(
        actor_id,
        (
            subject,
            provenance,
            reason,
            "https://identity.test",
            access.admin.token,
            access.target.token,
            access.bootstrap_grant_id,
        ),
    )
