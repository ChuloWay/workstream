"""Real CON/AUTH composition with signed Finance grants and historical parents."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select, text

from app.adapters.auth import contribution_policy_authorization
from app.adapters.contributions import contribution_policy_service
from app.db import session as db_session
from app.modules.actors.models import ActorIdentityLink
from app.modules.authorization.runtime import (
    HumanAuthorizationContext,
    ActorKind,
    ActorStatus,
    IdentityLinkStatus,
)
from app.modules.contributions.api import (
    ContributionPolicyCreateDraftRequest,
    ContributionPolicyUpdateDraftRequest,
    ContributionPolicyPublishRequest,
    ContributionPolicyRetireRequest,
    ContributionPolicyReadRequest,
    PolicyRuleInput,
    PolicyDefinitionInput,
)
from app.modules.compensation.api import CompensationInstrumentType
from tests.test_contributions import _seed_project


@dataclass
class PolicyWorld:
    """A real signed human and policy project with compatible binding fixtures."""

    admin_access: object
    project: UUID
    binding: UUID
    context: HumanAuthorizationContext
    grant: str

    def service(self, session):
        """Explicitly inject authenticated AUTH; default composition remains denied."""
        auth = contribution_policy_authorization(session, self.context)
        return contribution_policy_service(
            session, read_authorization=auth, mutation_authorization=auth
        )

    def request(self, operation, prior=None, *, compensated=False):
        """Prepare a valid caller request from a previous immutable result."""
        common = dict(actor_profile_id=self.context.actor_profile_id, project_id=self.project)
        if operation == "create_draft":
            return ContributionPolicyCreateDraftRequest(
                **common, operation_id=uuid4(), name="Finance policy"
            )
        common.update(
            contribution_policy_id=prior.contribution_policy_id,
            contribution_policy_version_id=prior.contribution_policy_version_id,
        )
        if operation == "read":
            return ContributionPolicyReadRequest(**common)
        common["operation_id"] = uuid4()
        if operation == "update_draft":
            definitions = (
                (
                    PolicyDefinitionInput(
                        instrument_type=CompensationInstrumentType.MONEY,
                        unit_code="USD",
                        quantity="2",
                        adapter_binding_id=self.binding,
                    ),
                )
                if compensated
                else ()
            )
            return ContributionPolicyUpdateDraftRequest(
                **common,
                rules=(
                    PolicyRuleInput(
                        contribution_type="accepted_submission",
                        compensation_mode="compensated" if compensated else "unpaid",
                        definitions=definitions,
                    ),
                    PolicyRuleInput(
                        contribution_type="completed_review", compensation_mode="unpaid"
                    ),
                ),
            )
        if operation == "publish":
            return ContributionPolicyPublishRequest(**common)
        return ContributionPolicyRetireRequest(**common)

    async def execute(self, operation, request):
        """Let one caller transaction commit both product and AUTH effects."""
        async with db_session.get_session_factory()() as session, session.begin():
            return await getattr(self.service(session), operation)(request)


async def world(admin_access, scope="project", role="finance_authority"):
    """Provision a project fixture and grant authority through the production API."""
    project, _, _, binding, _ = await _seed_project()
    grant = await admin_access.signed.grant(
        admin_access.admin,
        admin_access.target,
        role=role,
        project_id=UUID(project) if scope == "project" else None,
    )
    async with db_session.get_session_factory()() as session:
        link = await session.scalar(
            select(ActorIdentityLink).where(
                ActorIdentityLink.actor_profile_id == str(admin_access.target.id)
            )
        )
        context = HumanAuthorizationContext(
            actor_profile_id=admin_access.target.id,
            actor_kind=ActorKind.HUMAN,
            actor_status=ActorStatus.ACTIVE,
            identity_link_id=UUID(link.id),
            identity_link_status=IdentityLinkStatus.ACTIVE,
            request_id=uuid4(),
            correlation_id=uuid4(),
        )
    return PolicyWorld(admin_access, UUID(project), binding, context, grant)


async def snapshot(project):
    """Inspect exact committed product rows and policy AUTH evidence in a fresh session."""
    async with db_session.get_session_factory()() as session:
        result = {}
        for table in (
            "contribution_policies",
            "contribution_policy_versions",
            "contribution_rules",
            "contribution_award_definitions",
            "contribution_policy_lifecycle_events",
            "contribution_policy_transition_custody",
        ):
            result[table] = (
                (
                    await session.execute(
                        text(
                            f"select row_to_json(t)::text from {table} t where project_id=:p order by row_to_json(t)::text"
                        ),
                        {"p": str(project)},
                    )
                )
                .scalars()
                .all()
            )
        result["authority"] = (
            (
                await session.execute(
                    text(
                        "select row_to_json(t)::text from audit_events t where project_id=:p and action_id like 'contribution.policy.%' order by id"
                    ),
                    {"p": str(project)},
                )
            )
            .scalars()
            .all()
        )
        return result
