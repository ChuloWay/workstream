"""Real finalization AUTH and production lifecycle composition in caller transactions."""

from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from app.adapters.auth import setup_finalization_authorization
from app.modules.authorization.api import PreparedSetupFinalization, AuthorizationUnavailable
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.kernel import AuthorizationService
from app.modules.authorization.lifecycle_service import (
    ActorLifecycleService,
    IdentityLinkLifecycleService,
)
from app.modules.authorization.repository import AdminAuthorizationRepository
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    IdentityLinkStatus,
    HumanAuthorizationContext,
    ActorProfileLifecycleResourceContext,
    ActorIdentityLinkLifecycleResourceContext,
)
from app.modules.authorization.schemas import (
    ActorProfileSuspendRequest,
    ActorProfileDeactivateRequest,
    ActorIdentityLinkRevokeRequest,
    AuthorityOperation,
    derive_reason_digest,
)
from app.modules.projects.guide_compilation.finalization import GuideCompilationFinalizationService


async def concrete_finalize(factory, command):
    """Exercise the actual composition root without a strict test authorization port."""
    async with factory() as session, session.begin():
        return await GuideCompilationFinalizationService(
            session, setup_finalization_authorization(session)
        ).finalize(command)


async def seed_lifecycle_admin(factory):
    """Seed eligible admin prerequisites only; decisions and mutations use production owners."""
    actor, link, grant = uuid4(), uuid4(), uuid4()
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "insert into actor_profiles(id,actor_kind,status,provisioning_method,created_by) "
                "values(:id,'human','active','automatic_first_access','test')"
            ),
            {"id": str(actor)},
        )
        await session.execute(
            text(
                "insert into actor_identity_links(id,actor_profile_id,issuer,subject,subject_kind,"
                "status,linked_by,last_verified_at) values(:id,:actor,'https://identity.flowresearch.tech',"
                ":subject,'human','active','test',:now)"
            ),
            {"id": str(link), "actor": str(actor), "subject": str(actor), "now": datetime.now(UTC)},
        )
        # The fixture supplies an existing admin grant, not an authorization decision.
        await session.execute(text("alter table admin_role_grants disable trigger user"))
        await session.execute(
            text(
                "insert into admin_role_grants(id,target_actor_profile_id,role,scope_type,"
                "status,version,granted_by_system_principal,grant_reason) values(:id,:actor,"
                "'access_administrator','system','active',1,'workstream:system:bootstrap','finalization revocation proof')"
            ),
            {"id": grant, "actor": str(actor)},
        )
        await session.execute(text("alter table admin_role_grants enable trigger user"))
    return actor, link


async def revoke(session, admin, values, kind):
    """Run the router's reserve -> real AUTH require -> lifecycle complete sequence."""
    actor, link = admin
    reason = "Revoke setup service for exact finalization authority proof"
    common = {"reason_digest": derive_reason_digest(reason)}
    if kind == "link":
        request = ActorIdentityLinkRevokeRequest(
            operation=AuthorityOperation.ACTOR_IDENTITY_LINK_REVOKE,
            identity_link_id=values["link"],
            **common,
        )
        action = ActionId.ACTOR_IDENTITY_LINK_REVOKE
        resource = ActorIdentityLinkLifecycleResourceContext(
            resource_type="actor_identity_link",
            resource_id=values["link"],
            transition="revoke",
        )
        lifecycle = IdentityLinkLifecycleService(session)
    else:
        deactivate = kind == "deactivate"
        request = (ActorProfileDeactivateRequest if deactivate else ActorProfileSuspendRequest)(
            operation=AuthorityOperation.ACTOR_PROFILE_DEACTIVATE
            if deactivate
            else AuthorityOperation.ACTOR_PROFILE_SUSPEND,
            actor_profile_id=values["actor"],
            **common,
        )
        action = ActionId.ACTOR_PROFILE_DEACTIVATE if deactivate else ActionId.ACTOR_PROFILE_SUSPEND
        resource = ActorProfileLifecycleResourceContext(
            resource_type="actor_profile",
            resource_id=values["actor"],
            transition="deactivate" if deactivate else "suspend",
        )
        lifecycle = ActorLifecycleService(session)
    context = HumanAuthorizationContext(
        actor_profile_id=actor,
        identity_link_id=link,
        actor_kind=ActorKind.HUMAN,
        actor_status=ActorStatus.ACTIVE,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        request_id=uuid4(),
        correlation_id=uuid4(),
    )
    repository = AdminAuthorizationRepository(session)
    authorization = AuthorizationService(session, context, admin_repository=repository)
    reservation = await lifecycle.reserve(
        idempotency_key=uuid4(), actor_profile_id=actor, request=request
    )
    assert reservation.outcome == "claimed"
    decision = await authorization.require(action, resource)
    assert decision.allowed and decision.matched_grant_id is not None
    response = await lifecycle.complete(
        claim=reservation.claim,
        request=request,
        decision=decision,
        actor_profile_id=actor,
        reason=reason,
    )
    assert response.http_status == 200
    return decision


class ObservedPrepared(PreparedSetupFinalization):
    """Retain real capability behavior while observing/faulting its returned receipt."""

    def __init__(self, delegate, owner):
        self.delegate, self.owner = delegate, owner

    async def consume_new(self, facts):
        self.owner.facts = facts
        self.owner.handle = self.delegate
        receipt = await self.delegate.consume_new(facts)
        self.owner.receipt = receipt
        if self.owner.fault == "receipt":
            return replace(receipt, identity_link_id=uuid4())
        return receipt

    async def validate_replay(self, facts, stored_decision_id):
        self.owner.facts = facts
        self.owner.handle = self.delegate
        return await self.delegate.validate_replay(facts, stored_decision_id)


class ObservedAuthorization:
    """Wrap the actual adapter; no fixture supplies an allowed decision."""

    def __init__(self, session, *, fault=None, after_prepare=None):
        self.delegate = setup_finalization_authorization(session)
        self.fault, self.after_prepare = fault, after_prepare
        self.facts = self.handle = self.receipt = None

    @asynccontextmanager
    async def prepare_setup_finalization(self, locator):
        async with self.delegate.prepare_setup_finalization(locator) as prepared:
            if self.after_prepare is not None:
                await self.after_prepare()
            yield ObservedPrepared(prepared, self)
        if self.fault == "close":
            raise AuthorizationUnavailable("injected closure failure after real allow evidence")
