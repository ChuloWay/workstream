"""Canonical actor identity at the bounded legacy authorization dependency."""

from app.api.deps.auth import get_registered_actor
from app.core.identifiers import new_record_id
from app.modules.actors.service import ActorService
from app.schemas.auth import (
    AuthVerificationResult,
    LegacyAuthorizationCompatibilityContext,
    actor_id_from_external_identity,
)

from tests.actors.support import ISSUER, resolved_actor, verified_token


async def test_registered_actor_uses_the_resolved_profile_identity(
    monkeypatch,
) -> None:
    subject = "canonical-registered-actor"
    canonical_actor_id = str(new_record_id())
    resolved = resolved_actor(subject=subject, actor_id=canonical_actor_id)
    result = AuthVerificationResult(
        token=verified_token(subject),
        legacy=LegacyAuthorizationCompatibilityContext(
            roles=("contributor",),
            auth_source="dev_mock",
            is_dev_auth=True,
        ),
    )
    refreshed = []

    async def capture_refresh(_service, actor):
        refreshed.append(actor)

    monkeypatch.setattr(ActorService, "refresh_legacy_identity", capture_refresh)

    actor = await get_registered_actor(result, resolved, object())

    assert actor.actor_id == canonical_actor_id
    assert actor.actor_id != actor_id_from_external_identity(ISSUER, subject)
    assert actor.external_issuer == ISSUER
    assert actor.external_subject == subject
    assert actor.roles == ("contributor",)
    assert refreshed == [actor]
