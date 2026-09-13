"""Strict owner commitments replace the unused flat policy resource."""

from dataclasses import fields, replace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.authorization.api.post_policy import PostPolicyAuthorizationFacts
from app.modules.authorization.catalogue import (
    ACTION_BY_ID,
    POST_POLICY_MUTATION_ACTION_IDS,
    ActionAvailability,
    SERVICE_ACTIONS_BY_IDENTITY,
)
from app.modules.authorization.domain.post_policy import post_policy_resource
from app.modules.authorization.domain.resource_digest import authorization_resource_digest
from app.modules.actors.api import ServiceIdentity
from .support import post_facts, DERIVE, APPROVE, CORRECT, READ


def test_exact_action_activation_and_matrix():
    assert {str(a) for a in POST_POLICY_MUTATION_ACTION_IDS} == {DERIVE, APPROVE, CORRECT}
    assert all(
        ACTION_BY_ID[a].availability is ActionAvailability.ACTIVE
        for a in POST_POLICY_MUTATION_ACTION_IDS
    )
    assert {str(i) for i, actions in SERVICE_ACTIONS_BY_IDENTITY.items() if DERIVE in actions} == {
        ServiceIdentity.PROJECT_SETUP.value
    }
    assert all(
        APPROVE not in actions and CORRECT not in actions
        for actions in SERVICE_ACTIONS_BY_IDENTITY.values()
    )


@pytest.mark.parametrize("field", [f.name for f in fields(PostPolicyAuthorizationFacts)])
def test_each_commitment_is_required_and_strict(field):
    facts = post_facts()
    post_policy_resource(facts)
    with pytest.raises((TypeError, ValueError)):
        post_policy_resource(replace(facts, **{field: None}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("setup_generation", True),
        ("setup_generation", 0),
        ("guide_version", " "),
        ("policy_hash", "sha256:" + "A" * 64),
        ("finalization_id", "not-uuid"),
        ("lifecycle_status", "ready"),
    ],
)
def test_malformed_commitment_rejects(field, value):
    with pytest.raises((TypeError, ValueError)):
        post_policy_resource(replace(post_facts(), **{field: value}))


@pytest.mark.parametrize(
    "field,value",
    [
        ("resource_id", uuid4()),
        ("scope_project_id", uuid4()),
        ("resource_type", "project_setup_step"),
        ("execution_kind", "human"),
        ("setup_service_custody", {}),
    ],
)
def test_resource_rejects_crossed_identity_and_obsolete_step_fields(field, value):
    resource = post_policy_resource(post_facts())
    with pytest.raises(ValidationError):
        type(resource)(**(dict(resource) | {field: value}))


@pytest.mark.parametrize(
    "action,state,valid",
    [
        (DERIVE, "approved", False),
        (APPROVE, "superseded", False),
        (CORRECT, "approved", True),
        (CORRECT, "superseded", False),
        (READ, "superseded", True),
    ],
)
def test_action_restricts_policy_lifecycle(action, state, valid):
    facts = replace(post_facts(action), lifecycle_status=state)
    if valid:
        assert post_policy_resource(facts).facts == facts
    else:
        with pytest.raises(ValueError):
            post_policy_resource(facts)


def test_post_policy_digest_preserves_public_facts():
    facts = post_facts()
    assert authorization_resource_digest(post_policy_resource(facts)) == facts.digest
    assert replace(facts, locator=replace(facts.locator, request_id=uuid4())).digest == facts.digest
