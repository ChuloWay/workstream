# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalOperand=false
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db import session as db_session
from app.modules.actors.models import (
    ActorIdentityLink,
    ActorProfile,
)
from app.modules.actors.schemas import (
    ActorProfileUpdateRequest,
)
from app.modules.actors.service import (
    ActorDeactivated,
    ActorService,
    IdentityLinkRevoked,
    ServiceActorNotProvisioned,
    UnsupportedSubjectKind,
)
from app.modules.actors.api import ServiceIdentity
from app.schemas.auth import (
    actor_id_from_external_identity,
)

from tests.actors.support import ISSUER, verified_token, resolved_actor
from app.modules.tasks.models import AuditEvent


class ResolutionRows:
    """Exact read selectors; a returned row can still be adversarial."""

    def __init__(self, token, resolved):
        self.token = token
        self.profile_id = resolved.profile.id
        self.profile, self.link = resolved.profile, resolved.identity_link
        self.calls = []

    async def get_identity_link(self, issuer, subject, *, for_update=False):
        self.calls.append(("link", issuer, subject, for_update))
        assert (issuer, subject, for_update) == (self.token.issuer, self.token.subject, False)
        return self.link

    async def get_actor_profile(self, profile_id, *, for_update=False):
        self.calls.append(("profile", profile_id, for_update))
        assert (profile_id, for_update) == (self.profile_id, False)
        return self.profile


def resolution_case(token):
    repository = ResolutionRows(token, resolved_actor(subject=token.subject))
    service = ActorService(object())
    service._repo = repository
    return service, repository


async def test_service_admission_rejects_malformed_stored_identity_without_writes():
    token = verified_token("malformed-service", kind="service")
    service, repository = resolution_case(token)
    repository.profile.actor_kind = "service"
    repository.profile.provisioning_method = "manual_service_provisioning"
    repository.profile.service_identity = "private-invalid-service-identity"
    repository.link.subject_kind = "service"

    with pytest.raises(ServiceActorNotProvisioned, match="not provisioned"):
        await service.resolve_service_for_authorization(token)

    assert repository.calls == [
        ("link", token.issuer, token.subject, False),
        ("profile", repository.profile_id, False),
    ]


async def test_actor_resolution_rejects_missing_profile():
    token = verified_token("actor-drift")
    service, repository = resolution_case(token)
    repository.profile = None

    with pytest.raises(RuntimeError, match="missing actor profile"):
        await service.find_actor_for_authorization(token)

    assert repository.calls == [
        ("link", token.issuer, token.subject, False),
        ("profile", repository.profile_id, False),
    ]


@pytest.mark.parametrize("row", ["profile", "link"])
async def test_actor_resolution_rejects_subject_kind_drift(row):
    token = verified_token("actor-drift")
    service, repository = resolution_case(token)
    if row == "profile":
        repository.profile.actor_kind = "service"
        repository.profile.provisioning_method = "manual_service_provisioning"
        repository.profile.service_identity = "workstream.artifact.verifier"
    else:
        repository.link.subject_kind = "service"

    with pytest.raises(UnsupportedSubjectKind, match="does not match actor"):
        await service.find_actor_for_authorization(token)

    assert repository.calls == [
        ("link", token.issuer, token.subject, False),
        ("profile", repository.profile_id, False),
    ]


@pytest.mark.parametrize("kind", ["agent", "space"])
async def test_unsupported_subject_kinds_create_nothing(
    actor_database_env: str,
    kind: str,
) -> None:
    async with db_session.get_session_factory()() as session:
        with pytest.raises(UnsupportedSubjectKind):
            await ActorService(session).resolve_verified_actor(
                verified_token(f"unsupported-{kind}", kind=kind),
                request_id=uuid4(),
                correlation_id=uuid4(),
            )
        assert await session.scalar(select(func.count()).select_from(ActorProfile)) == 0
        assert await session.scalar(select(func.count()).select_from(ActorIdentityLink)) == 0
        assert await session.scalar(select(func.count()).select_from(AuditEvent)) == 0
        await session.rollback()
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(ActorProfile)) == 0
        assert await session.scalar(select(func.count()).select_from(ActorIdentityLink)) == 0


@pytest.mark.parametrize("entry", ["resolve_verified_actor", "resolve_service_for_authorization"])
async def test_unknown_service_creates_nothing(actor_database_env, entry):
    async with db_session.get_session_factory()() as session:
        service = ActorService(session)
        options = (
            {"request_id": uuid4(), "correlation_id": uuid4()}
            if entry == "resolve_verified_actor"
            else {}
        )
        with pytest.raises(ServiceActorNotProvisioned):
            await getattr(service, entry)(
                verified_token("unknown-service", kind="service"), **options
            )
        assert await session.scalar(select(func.count()).select_from(ActorProfile)) == 0
        assert await session.scalar(select(func.count()).select_from(ActorIdentityLink)) == 0
        assert await session.scalar(select(func.count()).select_from(AuditEvent)) == 0
        await session.rollback()
    async with db_session.get_session_factory()() as session:
        assert await session.scalar(select(func.count()).select_from(ActorProfile)) == 0
        assert await session.scalar(select(func.count()).select_from(ActorIdentityLink)) == 0
        assert await session.scalar(select(func.count()).select_from(AuditEvent)) == 0


async def test_revoked_identity_denies_verified_actor_lookup(actor_database_env: str) -> None:
    human_token = verified_token("revoked-human")
    async with db_session.get_session_factory()() as session:
        resolved = await ActorService(session).resolve_verified_actor(
            human_token,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        resolved.identity_link.status = "revoked"
        resolved.identity_link.revoked_by = resolved.profile.id
        resolved.identity_link.revoked_at = func.now()
        resolved.identity_link.revoked_reason = "security response"
        await session.commit()
    async with db_session.get_session_factory()() as session:
        with pytest.raises(IdentityLinkRevoked):
            await ActorService(session).find_verified_actor(human_token)


async def test_deactivated_actor_denies_direct_self_update(actor_database_env: str) -> None:
    deactivated_token = verified_token("deactivated-human")
    async with db_session.get_session_factory()() as session:
        deactivated = await ActorService(session).resolve_verified_actor(
            deactivated_token,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
        deactivated.profile.status = "deactivated"
        deactivated.profile.deactivated_by = deactivated.profile.id
        deactivated.profile.deactivated_at = func.now()
        deactivated.profile.deactivation_reason = "operator decision"
        await session.commit()
        with pytest.raises(ActorDeactivated):
            await ActorService(session).update_self(
                deactivated,
                ActorProfileUpdateRequest(display_name="Blocked"),
            )


@pytest.fixture
async def known_service(actor_database_env):
    service_token = verified_token("known-service", kind="service")
    service_actor_id = actor_id_from_external_identity(ISSUER, service_token.subject)
    async with db_session.get_session_factory()() as session:
        session.add_all(
            [
                ActorProfile(
                    id=service_actor_id,
                    actor_kind="service",
                    status="active",
                    provisioning_method="manual_service_provisioning",
                    service_identity="workstream.artifact.verifier",
                    created_by="workstream:system:test",
                    last_seen_at=None,
                ),
                ActorIdentityLink(
                    id=str(uuid4()),
                    actor_profile_id=service_actor_id,
                    issuer=ISSUER,
                    subject=service_token.subject,
                    subject_kind="service",
                    status="active",
                    linked_by="workstream:system:test",
                    last_verified_at=None,
                ),
            ]
        )
        await session.commit()
    return service_token, service_actor_id


async def test_known_service_cannot_use_human_authorization_entry(known_service):
    service_token, _actor_id = known_service
    async with db_session.get_session_factory()() as session:
        service = ActorService(session)
        with pytest.raises(ServiceActorNotProvisioned):
            await service.resolve_actor_for_authorization(
                service_token,
                request_id=uuid4(),
                correlation_id=uuid4(),
            )
        assert await session.scalar(select(func.count()).select_from(AuditEvent)) == 0


async def test_known_service_admission_preserves_verification_timestamps(known_service):
    service_token, service_actor_id = known_service
    async with db_session.get_session_factory()() as session:
        service = ActorService(session)
        persisted = await service.find_actor_for_authorization(service_token)
        assert persisted is not None
        admitted = await service.resolve_service_for_authorization(service_token)
        assert admitted.profile.id == service_actor_id
        locked = await service.lock_actor_for_authorization(admitted)
        assert locked is not None
        assert locked.profile.service_identity == ServiceIdentity.ARTIFACT_VERIFIER
        assert persisted.profile.last_seen_at is None
        assert persisted.identity_link.last_verified_at is None
