"""Real HTTP/SQL proposal owner with only verified identity admission supplied."""

from contextlib import asynccontextmanager
from time import time

from httpx import ASGITransport, AsyncClient

from app.api.deps.authorization import enforce_human_authorization_read, get_authorization_actor
from app.api.deps.auth import get_auth_verification_result
from app.db.session import get_db_session
from app.main import create_app
from app.modules.actors.models import ActorIdentityLink, ActorProfile
from app.modules.actors.service import ResolvedActor
from app.schemas.auth import AuthVerificationResult, VerifiedIssuerToken


@asynccontextmanager
async def proposal_client(factory, actor):
    async with factory() as session:
        resolved = ResolvedActor(
            await session.get(ActorProfile, str(actor.actor_profile_id)),
            await session.get(ActorIdentityLink, str(actor.identity_link_id)),
        )
    async def database():
        async with factory() as session:
            yield session
    async def identity():
        return resolved
    async def verified_identity():
        now = int(time())
        return AuthVerificationResult(token=VerifiedIssuerToken(
            issuer=resolved.identity_link.issuer,
            subject=resolved.identity_link.subject,
            subject_kind=resolved.profile.actor_kind,
            audience=("workstream",),
            issued_at=now,
            expires_at=now + 300,
            token_id="proposal-fixture",
            scopes=frozenset(),
        ))
    app = create_app()
    app.dependency_overrides[get_db_session] = database
    app.dependency_overrides[get_authorization_actor] = identity
    app.dependency_overrides[get_auth_verification_result] = verified_identity
    app.dependency_overrides[enforce_human_authorization_read] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        yield client


def proposal_path(command):
    return f"/api/v1/projects/{command.project_id}/guides/{command.guide_id}/compilations/{command.compilation_id}"
