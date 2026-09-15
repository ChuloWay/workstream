"""Complete CP07 values with real AUTH kernel/PREP and in-memory persistence."""

from uuid import uuid4

from app.core.hashing import canonical_json_hash
from app.modules.authorization import guide_activation_authorization as adapters
from app.modules.projects.api.guide_activation import (
    GuideActivationFacts, GuideActivationLocator, GuideActivationReceipt,
)
from tests.authorization.guide_proposals.support import Case as ProposalCase
from tests.projects.guide_activation.test_contracts import receipt_values


def activation_facts(project_id=None):
    values = receipt_values()
    if project_id is not None:
        command = values["command"]
        proposal = command.target.proposal.model_copy(update={"project_id": project_id})
        upstream = command.target.upstream.model_copy(update={"target_digest": proposal.digest})
        target = command.target.model_copy(update={
            "proposal": proposal, "upstream": upstream,
            "upstream_output_digest": canonical_json_hash(upstream.model_dump(mode="json")),
        })
        values["command"] = command.model_copy(update={"target": target})
        values["contribution"] = values["contribution"].model_copy(update={"project_id": project_id})
    receipt = GuideActivationReceipt(**values)
    return GuideActivationFacts(
        locator=GuideActivationLocator(
            project_id=receipt.command.target.proposal.project_id,
            guide_id=receipt.command.target.proposal.guide_id,
            operation_id=receipt.operation_id, actor_profile_id=uuid4(),
            identity_link_id=uuid4(), request_id=uuid4(),
        ),
        receipt=receipt,
    )


class Case(ProposalCase):
    def __init__(self, monkeypatch):
        super().__init__(monkeypatch)
        self.facts = activation_facts()
        self.locks = []
        self.context = self.context.model_copy(update=dict(
            actor_profile_id=self.facts.locator.actor_profile_id,
            identity_link_id=self.facts.locator.identity_link_id,
            request_id=self.facts.locator.request_id,
        ))
        self.grant.scope_project_id = str(self.facts.locator.project_id)
        monkeypatch.setattr(adapters, "AdminAuthorizationRepository", lambda session: self)
        original = adapters.AuthorizationService

        def kernel(session, context, **kwargs):
            result = original(session, context, **kwargs)
            result._audit = self
            return result

        monkeypatch.setattr(adapters, "AuthorizationService", kernel)

    async def lock_control(self):
        self.locks.append("control")

    async def lock_request_actor(self, link, actor):
        self.locks.append("principal")
        return await super().lock_request_actor(link, actor)

    async def find_effective_grant(self, actor, permission, **filters):
        # Model the real repository's system-scope alternative: this must not
        # silently reject system grants when the caller forgot exact scope.
        self.locks.append("grant")
        self.last_filters = filters
        if self.role not in filters["allowed_roles"] or self.grant.status != "active":
            return None
        if self.grant.scope_type == "system":
            return None if filters.get("exact_project_scope") else self.grant
        return self.grant if self.grant.scope_project_id == str(filters["scope_project_id"]) else None

    def prepare(self, *, facts=None, context=None):
        return adapters.GuideActivationAuthorizationAdapter(
            self.session, context or self.context,
        ).lock_activation_scope((facts or self.facts).locator)
