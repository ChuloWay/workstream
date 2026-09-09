"""Real kernel/PREP action, scope, audit and resource-discriminator proof."""

from dataclasses import replace
from uuid import uuid4

import pytest

from app.modules.authorization.api import (
    ContributionPolicyReadFacts,
    AuthorizationDenied,
    PreparedAuthorizationInvalid,
)
from app.modules.authorization.catalogue import ActionId
from app.modules.authorization.runtime import ActorStatus, IdentityLinkStatus
from .fixtures import ACTIONS, adapter, mutation


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("read", *ACTIONS))
@pytest.mark.parametrize("scope", ("system", "project"))
async def test_each_policy_action_allows_exact_finance_scope_and_audit(operation, scope):
    project = uuid4()
    auth, context, _, evidence = adapter(None if scope == "system" else project)
    facts = mutation(
        context.actor_profile_id, project, operation if operation != "read" else "create_draft"
    )
    if operation == "read":
        await auth.authorize_read(
            actor_profile_id=context.actor_profile_id,
            facts=ContributionPolicyReadFacts(
                project_id=project, contribution_policy_id=facts.contribution_policy_id
            ),
        )
    else:
        handle = await auth.prepare_mutation(facts)
        assert await auth.consume_mutation(handle, facts) == context.actor_profile_id
        auth.close_mutation(handle)
    assert len(evidence.events) == 1
    event = evidence.events[0]
    assert event.action_id == "contribution.policy." + operation
    assert event.project_id == str(project)
    assert event.resource_type == "contribution_policy"
    assert event.resource_id == str(facts.contribution_policy_id)
    assert event.after_facts["allowed"] is True
    assert event.after_facts["resource_context_digest"].startswith("sha256:")


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ("read", *ACTIONS))
@pytest.mark.parametrize("denial", ("foreign", "no_grant", "actor", "link"))
async def test_each_policy_action_denies_foreign_or_unprivileged_principal(operation, denial):
    project = uuid4()
    auth, context, _, _ = adapter(
        uuid4() if denial == "foreign" else project,
        grant_available=denial != "no_grant",
        actor_status=ActorStatus.SUSPENDED if denial == "actor" else ActorStatus.ACTIVE,
        link_status=IdentityLinkStatus.REVOKED if denial == "link" else IdentityLinkStatus.ACTIVE,
    )
    facts = mutation(
        context.actor_profile_id, project, operation if operation != "read" else "create_draft"
    )
    with pytest.raises(AuthorizationDenied):
        if operation == "read":
            await auth.authorize_read(
                actor_profile_id=context.actor_profile_id,
                facts=ContributionPolicyReadFacts(
                    project_id=project, contribution_policy_id=facts.contribution_policy_id
                ),
            )
        else:
            await auth.prepare_mutation(facts)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ACTIONS)
async def test_policy_prepared_handle_rejects_reuse_and_foreign_composition(operation):
    project = uuid4()
    auth, context, _, _ = adapter(project)
    facts = mutation(context.actor_profile_id, project, operation)
    handle = await auth.prepare_mutation(facts)
    other, _, _, _ = adapter(project)
    with pytest.raises((AuthorizationDenied, PreparedAuthorizationInvalid)):
        await other.consume_mutation(handle, facts)
    assert await auth.consume_mutation(handle, facts) == context.actor_profile_id
    with pytest.raises(PreparedAuthorizationInvalid):
        await auth.consume_mutation(handle, facts)
    auth.close_mutation(handle)


@pytest.mark.parametrize("operation", ACTIONS)
def test_policy_actions_reject_sibling_resource_classes(operation):
    project = uuid4()
    auth, context, _, _ = adapter(project)
    action, resource = auth._mutation_context(
        mutation(context.actor_profile_id, project, operation)
    )
    assert auth._authorization._admin_resource_matches(action, resource)
    for sibling in ACTIONS:
        if sibling != operation:
            assert not auth._authorization._admin_resource_matches(
                ActionId("contribution.policy." + sibling), resource
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("exact_version", (False, True))
async def test_policy_read_binds_optional_version(exact_version):
    project = uuid4()
    auth, context, _, evidence = adapter(project)
    facts = ContributionPolicyReadFacts(
        project_id=project,
        contribution_policy_id=uuid4(),
        contribution_policy_version_id=uuid4() if exact_version else None,
    )
    await auth.authorize_read(actor_profile_id=context.actor_profile_id, facts=facts)
    await auth.authorize_read(
        actor_profile_id=context.actor_profile_id,
        facts=replace(facts, contribution_policy_version_id=uuid4()),
    )
    assert (
        evidence.events[0].after_facts["resource_context_digest"]
        != evidence.events[1].after_facts["resource_context_digest"]
    )


@pytest.mark.parametrize("operation", ACTIONS)
def test_policy_resource_subclasses_cannot_replace_exact_action_resource(operation):
    project = uuid4()
    auth, context, _, _ = adapter(project)
    action, resource = auth._mutation_context(
        mutation(context.actor_profile_id, project, operation)
    )
    subclass = type("SubstitutedPolicyResource", (type(resource),), {})
    substituted = subclass.model_validate(resource.model_dump())
    assert isinstance(substituted, type(resource))
    assert auth._authorization._admin_resource_matches(action, resource)
    assert not auth._authorization._admin_resource_matches(action, substituted)
