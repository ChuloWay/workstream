"""Exact ACTORS owner-port selectors, ordering and returned-row validation."""

from uuid import uuid4

import pytest

from app.modules.actors.service import (
    ActorService,
    ActiveHumanWriteActorRequired,
    CanonicalWriteActorUnavailable,
)
from tests.actors.support import ISSUER, legacy_actor, resolved_actor


class LockedRows:
    """Strict selectors with separately replaceable returned rows."""

    def __init__(self, original):
        self.expected_profile_id = original.profile.id
        self.expected_link_id = original.identity_link.id
        self.expected_subject = original.identity_link.subject
        self.profile = resolved_actor(
            actor_id=original.profile.id, subject=self.expected_subject
        ).profile
        self.link = resolved_actor(
            actor_id=original.profile.id, subject=self.expected_subject
        ).identity_link
        self.link.id = original.identity_link.id
        self.calls = []

    async def get_actor_profile(self, actor_id, *, for_update=False):
        self.calls.append(("profile", actor_id, for_update))
        assert (actor_id, for_update) == (self.expected_profile_id, True)
        return self.profile

    async def get_identity_link_by_id(self, link_id, *, for_update=False):
        self.calls.append(("link", link_id, for_update))
        assert (link_id, for_update) == (self.expected_link_id, True)
        return self.link

    async def get_identity_link(self, issuer, subject, *, for_update=False):
        self.calls.append(("identity", issuer, subject, for_update))
        assert (issuer, subject, for_update) == (ISSUER, self.expected_subject, True)
        return self.link


def controlled_service(original):
    repository = LockedRows(original)
    service = ActorService(object())
    service._repo = repository
    return service, repository


@pytest.mark.parametrize("missing", ["profile", "link"])
async def test_actor_authorization_lock_rejects_disappeared_rows(missing):
    original = resolved_actor()
    service, repository = controlled_service(original)
    setattr(repository, missing, None)

    with pytest.raises(RuntimeError, match=f"{missing} disappeared"):
        await service.lock_actor_self_for_authorization(original)

    expected = [("profile", original.profile.id, True)]
    if missing == "link":
        expected.append(("link", original.identity_link.id, True))
    assert repository.calls == expected


@pytest.mark.parametrize(
    ("row", "field", "value"),
    [
        ("profile", "id", None),
        ("link", "actor_profile_id", None),
        ("link", "issuer", "https://other.example.test"),
        ("link", "subject", "different-subject"),
        ("link", "subject_kind", "service"),
    ],
    ids=["profile-id", "link-owner", "issuer", "subject", "subject-kind"],
)
async def test_actor_authorization_lock_rejects_one_identity_substitution(row, field, value):
    original = resolved_actor()
    service, repository = controlled_service(original)
    if field in {"id", "actor_profile_id"}:
        value = str(uuid4())
    setattr(getattr(repository, row), field, value)

    with pytest.raises(RuntimeError, match="identity changed"):
        await service.lock_actor_self_for_authorization(original)

    assert repository.calls == [
        ("profile", original.profile.id, True),
        ("link", original.identity_link.id, True),
    ]


async def test_actor_authorization_lock_returns_exact_locked_rows():
    original = resolved_actor()
    service, repository = controlled_service(original)

    locked = await service.lock_actor_self_for_authorization(original)

    assert locked.profile is repository.profile
    assert locked.identity_link is repository.link
    assert repository.calls == [
        ("profile", original.profile.id, True),
        ("link", original.identity_link.id, True),
    ]


async def test_active_human_write_actor_revalidates_exact_profile_then_link():
    actor = legacy_actor("contributor-write")
    original = resolved_actor(actor_id=actor.actor_id, subject=actor.external_subject)
    service, repository = controlled_service(original)

    assert await service.require_active_human_write_actor(actor) is None

    assert repository.calls == [
        ("profile", actor.actor_id, True),
        ("identity", actor.external_issuer, actor.external_subject, True),
    ]


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("missing-profile", "profile is missing"),
        ("missing-link", "link is missing"),
        ("wrong-owner", "link is inconsistent"),
        ("nonhuman-link", "link is inconsistent"),
    ],
)
async def test_active_human_write_actor_rejects_unavailable_rows(failure, message):
    actor = legacy_actor("contributor-write")
    service, repository = controlled_service(
        resolved_actor(actor_id=actor.actor_id, subject=actor.external_subject)
    )
    if failure == "missing-profile":
        repository.profile = None
    elif failure == "missing-link":
        repository.link = None
    elif failure == "nonhuman-link":
        repository.link.subject_kind = "service"
    else:
        repository.link.actor_profile_id = str(uuid4())

    with pytest.raises(CanonicalWriteActorUnavailable, match=message):
        await service.require_active_human_write_actor(actor)

    expected = [("profile", actor.actor_id, True)]
    if failure != "missing-profile":
        expected.append(("identity", actor.external_issuer, actor.external_subject, True))
    assert repository.calls == expected


@pytest.mark.parametrize(
    ("row", "field", "value"),
    [
        ("profile", "actor_kind", "service"),
        ("profile", "status", "suspended"),
        ("profile", "status", "deactivated"),
        ("link", "status", "revoked"),
    ],
    ids=["service-profile", "suspended", "deactivated", "revoked-link"],
)
async def test_active_human_write_actor_rejects_ineligible_identity(row, field, value):
    actor = legacy_actor("contributor-write")
    service, repository = controlled_service(
        resolved_actor(actor_id=actor.actor_id, subject=actor.external_subject)
    )
    setattr(getattr(repository, row), field, value)

    with pytest.raises(ActiveHumanWriteActorRequired, match="active contributor identity required"):
        await service.require_active_human_write_actor(actor)

    expected = [("profile", actor.actor_id, True)]
    if row == "link":
        expected.append(("identity", actor.external_issuer, actor.external_subject, True))
    assert repository.calls == expected
