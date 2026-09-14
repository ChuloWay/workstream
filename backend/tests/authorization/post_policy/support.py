"""Valid owner commitments with the real shared kernel and PREP."""

from dataclasses import fields
from types import SimpleNamespace
from uuid import uuid4

from app.modules.authorization import post_policy_authorization as adapters
from app.modules.authorization.api.post_policy import (
    PostPolicyAuthorizationFacts,
    PostPolicyAuthorizationLocator,
)
from app.modules.authorization.runtime import ServiceAuthorizationContext, ActorKind
from app.modules.actors.api import ServiceIdentity
from tests.authorization.guide_proposals.support import Case as ProposalCase

HASH = "sha256:" + "a" * 64
DERIVE = "project.post_submit_checker_policy.derive"
APPROVE = "project.post_submit_checker_policy.approve"
CORRECT = "project.post_submit_checker_policy.correction.request"
READ = "project.guide_compilation.review_package.read"


def post_facts(action=DERIVE, project_id=None):
    locator = PostPolicyAuthorizationLocator(
        **{
            f.name: action if f.name == "action_id" else uuid4()
            for f in fields(PostPolicyAuthorizationLocator)
        }
    )
    if project_id is not None:
        from dataclasses import replace

        locator = replace(locator, project_id=project_id)
    values = {
        f.name: uuid4() if f.name.endswith("_id") else HASH
        for f in fields(PostPolicyAuthorizationFacts)
    }
    values.update(
        locator=locator, setup_generation=1, guide_version="guide-one", lifecycle_status="compiled"
    )
    return PostPolicyAuthorizationFacts(**values)


class Case(ProposalCase):
    def __init__(self, monkeypatch, action=APPROVE):
        super().__init__(monkeypatch)
        self.facts = post_facts(action)
        self.context = self.context.model_copy(
            update=dict(
                actor_profile_id=self.facts.locator.actor_profile_id,
                identity_link_id=self.facts.locator.identity_link_id,
                request_id=self.facts.locator.request_id,
            )
        )
        self.grant.scope_project_id = str(self.facts.locator.project_id)
        if action == DERIVE:
            self.actor_kind = "service"
            self.context = ServiceAuthorizationContext(
                **self.context.model_dump(exclude={"actor_kind"}),
                actor_kind=ActorKind.SERVICE,
                service_identity=ServiceIdentity.PROJECT_SETUP,
            )
        self.service_identity = ServiceIdentity.PROJECT_SETUP.value
        monkeypatch.setattr(adapters, "AdminAuthorizationRepository", lambda session: self)
        original = adapters.AuthorizationService

        def kernel(session, context, **kwargs):
            result = original(session, context, **kwargs)
            result._audit = self
            return result

        monkeypatch.setattr(adapters, "AuthorizationService", kernel)

    async def lock_request_actor(self, link, actor):
        return (
            SimpleNamespace(id=str(link), actor_profile_id=str(actor), status=self.link_status),
            SimpleNamespace(
                id=str(actor),
                actor_kind=self.actor_kind,
                status=self.actor_status,
                service_identity=self.service_identity,
            ),
        )

    def prepare(self, *, facts=None, context=None):
        return adapters.PostPolicyAuthorizationAdapter(
            self.session, context or self.context
        ).prepare_post_policy_operation((facts or self.facts).locator)
