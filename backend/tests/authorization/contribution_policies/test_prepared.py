"""Prepared policy authority rejects one-field substitutions and direct bypass."""

from dataclasses import replace
from uuid import uuid4

import pytest

from app.modules.authorization.api import (
    AuthorizationDenied,
    ContributionPolicyReadFacts,
    PreparedAuthorizationInvalid,
)
from app.modules.authorization.catalogue import ServiceIdentity
from app.modules.authorization.runtime import (
    ActorKind,
    ActorStatus,
    IdentityLinkStatus,
    ServiceAuthorizationContext,
    PreparedAuthorizationInput,
    PreparedAuthorizationHandleInvalid,
    AuthorizationDenied as KernelDenied,
)
from .fixtures import ACTIONS, DIGEST, adapter, mutation


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ACTIONS)
@pytest.mark.parametrize(
    "field",
    (
        "operation_id",
        "request_digest",
        "resource_id",
        "scope_project_id",
        "contribution_policy_version_id",
        "resource_facts_digest",
    ),
)
async def test_policy_prepared_handle_binds_every_fact(operation, field):
    project = uuid4()
    auth, context, _, _ = adapter(project)
    facts = mutation(context.actor_profile_id, project, operation)
    action, resource = auth._mutation_context(facts)
    handle = await auth.prepare_mutation(facts)
    changed = resource.model_copy(
        update={field: "sha256:" + "b" * 64 if "digest" in field else uuid4()}
    )
    with pytest.raises(
        PreparedAuthorizationHandleInvalid, match="invalid prepared authorization handle"
    ):
        await auth._prepared.consume(
            handle,
            action,
            PreparedAuthorizationInput(
                idempotency_key=facts.operation_id, request_value=resource.model_dump(mode="json")
            ),
            changed,
        )
    assert await auth.consume_mutation(handle, facts) == context.actor_profile_id
    auth.close_mutation(handle)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    (
        "rules_and_definitions_digest",
        "adapter_binding_ids",
        "expected_policy_status",
        "expected_version_status",
    ),
)
async def test_publication_handle_binds_graph_bindings_and_state(field):
    project = uuid4()
    auth, context, _, _ = adapter(project)
    facts = mutation(context.actor_profile_id, project, "publish")
    action, resource = auth._mutation_context(facts)
    handle = await auth.prepare_mutation(facts)
    value = (
        (uuid4(),)
        if field == "adapter_binding_ids"
        else DIGEST.replace("a", "b")
        if "digest" in field
        else "draft"
        if field == "expected_policy_status"
        else "retired"
    )
    changed = resource.model_copy(update={field: value})
    with pytest.raises(
        PreparedAuthorizationHandleInvalid, match="invalid prepared authorization handle"
    ):
        await auth._prepared.consume(
            handle,
            action,
            PreparedAuthorizationInput(
                idempotency_key=facts.operation_id, request_value=resource.model_dump(mode="json")
            ),
            changed,
        )
    assert await auth.consume_mutation(handle, facts) == context.actor_profile_id
    auth.close_mutation(handle)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ACTIONS)
async def test_policy_mutation_cannot_bypass_prep(operation):
    project = uuid4()
    auth, context, _, _ = adapter(project)
    action, resource = auth._mutation_context(
        mutation(context.actor_profile_id, project, operation)
    )
    with pytest.raises(KernelDenied):
        await auth._authorization.require(action, resource)


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", list(ServiceIdentity))
@pytest.mark.parametrize("operation", (*ACTIONS, "read"))
async def test_policy_actions_deny_every_service(identity, operation):
    project = uuid4()
    auth, context, _, _ = adapter(project)
    auth._authorization._context = ServiceAuthorizationContext(
        actor_profile_id=context.actor_profile_id,
        actor_kind=ActorKind.SERVICE,
        actor_status=ActorStatus.ACTIVE,
        identity_link_id=context.identity_link_id,
        identity_link_status=IdentityLinkStatus.ACTIVE,
        service_identity=identity,
        request_id=context.request_id,
        correlation_id=context.correlation_id,
    )
    with pytest.raises(AuthorizationDenied):
        if operation == "read":
            await auth.authorize_read(
                actor_profile_id=context.actor_profile_id,
                facts=ContributionPolicyReadFacts(
                    project_id=project, contribution_policy_id=uuid4()
                ),
            )
        else:
            await auth.prepare_mutation(mutation(context.actor_profile_id, project, operation))


@pytest.mark.asyncio
async def test_policy_handle_rejects_changed_actor_input_and_transaction():
    project = uuid4()
    auth, context, session, _ = adapter(project)
    facts = mutation(context.actor_profile_id, project)
    handle = await auth.prepare_mutation(facts)
    with pytest.raises(AuthorizationDenied):
        await auth.consume_mutation(handle, replace(facts, actor_profile_id=uuid4()))
    with pytest.raises(PreparedAuthorizationInvalid):
        await auth.consume_mutation(handle, replace(facts, operation_id=uuid4()))
    original = session.root
    session.root = type(original)(is_active=True)
    with pytest.raises(PreparedAuthorizationInvalid):
        await auth.consume_mutation(handle, facts)
    session.root = original
    with pytest.raises(PreparedAuthorizationInvalid):
        await auth.consume_mutation(handle, facts)
    fresh = await auth.prepare_mutation(facts)
    assert await auth.consume_mutation(fresh, facts) == context.actor_profile_id
    auth.close_mutation(fresh)


@pytest.mark.asyncio
async def test_policy_handle_rejects_identity_link_context_substitution():
    project = uuid4()
    auth, context, _, _ = adapter(project)
    facts = mutation(context.actor_profile_id, project)
    handle = await auth.prepare_mutation(facts)
    auth._authorization._context = context.model_copy(update={"identity_link_id": uuid4()})
    with pytest.raises(AuthorizationDenied):
        await auth.consume_mutation(handle, facts)
    auth._authorization._context = context
    assert await auth.consume_mutation(handle, facts) == context.actor_profile_id
    auth.close_mutation(handle)
