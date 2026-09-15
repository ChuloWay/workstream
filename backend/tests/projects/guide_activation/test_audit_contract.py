"""Activation audit vocabulary is exact and allow evidence remains digest-bound."""

from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from app.modules.audit.schemas import (
    AuthorityAuditEventInput,
    AuthorityEventType,
    ActorReferenceKind,
)
from app.modules.authorization.catalogue import (
    ACTION_BY_ID,
    ActionAvailability,
    ActionId,
    PermissionId,
)
from app.modules.authorization.domain.audit import (
    AuthorizationDecisionResourceType,
    CONTEXT_DIGEST_RESOURCE_TYPES,
)
from app.modules.authorization.domain.audit_targets import project_authority_audit_target
from app.modules.authorization.domain.guide_activation import activation_resource
from tests.authorization.guide_activation.support import activation_facts


@pytest.mark.parametrize(
    "token,valid", [("project_guide_activation", True), ("project_guide_activation_extra", False)]
)
def test_activation_audit_python_vocabularies_are_closed(token, valid):
    identifier = uuid4()
    values = dict(
        event_id=identifier,
        event_type=AuthorityEventType.SENSITIVE_AUTHORIZATION_DENIED,
        entity_type="authorization_decision",
        entity_id=str(identifier),
        actor_ref_kind=ActorReferenceKind.ACTOR_PROFILE,
        actor_ref=str(uuid4()),
        request_id=uuid4(),
        correlation_id=uuid4(),
        permission_id=PermissionId.PROJECT_GUIDE_MANAGE,
        action_id=ActionId.PROJECT_GUIDE_ACTIVATE,
        project_id=str(uuid4()),
        resource_type=token,
        resource_id=str(uuid4()),
        reason="authorization_evaluation",
        denial_code="permission_not_granted",
        after_facts={"allowed": False},
    )
    if valid:
        assert AuthorityAuditEventInput(**values).resource_type == token
        assert TypeAdapter(AuthorizationDecisionResourceType).validate_python(token) == token
        assert token in CONTEXT_DIGEST_RESOURCE_TYPES
        values.update(
            event_type=AuthorityEventType.SENSITIVE_AUTHORIZATION_ALLOWED,
            denial_code=None,
            after_facts={"allowed": True},
        )
        values["after_facts"] = {"allowed": True, "resource_context_digest": "sha256:" + "a" * 64}
        assert AuthorityAuditEventInput(**values).after_facts == values["after_facts"]
        values["after_facts"] = {**values["after_facts"], "private_material": "forbidden"}
        with pytest.raises(TypeError, match="invalid authority audit input"):
            AuthorityAuditEventInput(**values)
    else:
        with pytest.raises(TypeError, match="invalid authority audit input"):
            AuthorityAuditEventInput(**values)
        with pytest.raises(ValidationError):
            TypeAdapter(AuthorizationDecisionResourceType).validate_python(token)
        assert token not in CONTEXT_DIGEST_RESOURCE_TYPES


def test_activation_audit_maps_exact_project_and_guide():
    facts = activation_facts()
    project, guide = facts.locator.project_id, facts.locator.guide_id
    context = activation_resource(facts)
    assert project_authority_audit_target(context, ActionId.PROJECT_GUIDE_ACTIVATE) == (
        str(project),
        "project_guide_activation",
        str(guide),
        "project",
        str(project),
    )
    assert ACTION_BY_ID[ActionId.PROJECT_GUIDE_ACTIVATE].availability is ActionAvailability.ACTIVE
