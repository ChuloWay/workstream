# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false, reportOptionalOperand=false
from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from pydantic import ValidationError
import pytest

from app.modules.actors.models import (
    ActorIdentityLink,
    ActorProfile,
)
from app.modules.actors.repository import ActorRepository
from app.modules.actors.schemas import (
    ActorProfileAdminResponse,
)
from app.modules.actors.service import (
    ActorService,
)
from app.modules.actors.api import ServiceIdentity


@pytest.fixture
def admin_response_fields():
    now = datetime.now(UTC)
    return {
        "actor_profile_id": uuid4(),
        "status": "active",
        "display_name": None,
        "created_at": now,
        "updated_at": now,
        "last_seen_at": None,
        "suspended_at": None,
        "reactivated_at": None,
        "deactivated_at": None,
    }


@pytest.mark.parametrize("kind", ["human", "service"])
def test_actor_admin_response_accepts_exact_service_identity_pair(admin_response_fields, kind):
    identity = ServiceIdentity.ARTIFACT_VERIFIER if kind == "service" else None
    response = ActorProfileAdminResponse(
        **admin_response_fields,
        actor_kind=kind,
        provisioning_method="manual_service_provisioning"
        if kind == "service"
        else "automatic_first_access",
        service_identity=identity,
    )
    assert response.service_identity is identity


@pytest.mark.parametrize(
    ("actor_kind", "provisioning_method", "service_identity"),
    [
        ("human", "automatic_first_access", ServiceIdentity.ARTIFACT_VERIFIER),
        ("service", "manual_service_provisioning", None),
    ],
)
def test_actor_admin_response_rejects_mismatched_service_identity_pair(
    admin_response_fields, actor_kind, provisioning_method, service_identity
):
    with pytest.raises(ValidationError, match="service identity"):
        ActorProfileAdminResponse(
            **admin_response_fields,
            actor_kind=actor_kind,
            provisioning_method=provisioning_method,
            service_identity=service_identity,
        )


@pytest.fixture
def admin_read_case():
    now = datetime.now(UTC)
    actor_id, link_id = uuid4(), uuid4()
    profile = ActorProfile(
        id=str(actor_id),
        actor_kind="service",
        status="active",
        provisioning_method="manual_service_provisioning",
        service_identity=ServiceIdentity.ARTIFACT_VERIFIER.value,
        display_name=None,
        contact_email="must-not-escape@example.test",
        created_by=str(uuid4()),
        created_at=now,
        updated_at=now,
        last_seen_at=None,
    )
    link = ActorIdentityLink(
        id=str(link_id),
        actor_profile_id=str(actor_id),
        issuer="private-issuer",
        subject="private-subject",
        subject_kind="service",
        status="active",
        linked_by=str(uuid4()),
        linked_at=now,
        last_verified_at=None,
    )

    class Repository:
        calls: list[tuple[str, str]] = []

        async def get_actor_profile(self, requested_id):
            assert requested_id == str(actor_id)
            self.calls.append(("profile", requested_id))
            return profile

        async def get_identity_link_for_actor(self, requested_id):
            assert requested_id == str(actor_id)
            self.calls.append(("link", requested_id))
            return link

    repository = Repository()
    service = ActorService.__new__(ActorService)
    service._repo = cast(ActorRepository, repository)
    return service, repository, actor_id, link_id


async def test_actor_admin_profile_read_is_bounded_and_exact(admin_read_case):
    service, repository, actor_id, _link_id = admin_read_case
    profile_response = await service.read_admin_profile(actor_id)

    assert profile_response is not None
    assert profile_response.actor_profile_id == actor_id
    assert repository.calls == [("profile", str(actor_id))]
    assert set(profile_response.model_dump()) == {
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
    assert "must-not-escape@example.test" not in repr(profile_response.model_dump())


async def test_actor_admin_identity_read_is_bounded_and_exact(admin_read_case):
    service, repository, actor_id, link_id = admin_read_case
    link_response = await service.read_admin_identity_link(actor_id)

    assert link_response is not None
    assert link_response.actor_profile_id == actor_id
    assert link_response.identity_link_id == link_id
    assert repository.calls == [("link", str(actor_id))]
    assert set(link_response.model_dump()) == {
        "identity_link_id",
        "actor_profile_id",
        "subject_kind",
        "status",
        "linked_at",
        "last_verified_at",
        "revoked_at",
        "reactivated_at",
    }
    serialized = repr(link_response.model_dump())
    assert "private-issuer" not in serialized
    assert "private-subject" not in serialized
