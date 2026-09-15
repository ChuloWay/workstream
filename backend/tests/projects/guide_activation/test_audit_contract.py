"""Activation audit vocabulary is exact while the action remains unavailable."""

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
from app.modules.authorization.runtime import ProjectGuideActivationResourceContext


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
        with pytest.raises(ValidationError, match="planned action cannot produce allowed evidence"):
            AuthorityAuditEventInput(**values)
    else:
        with pytest.raises(TypeError, match="invalid authority audit input"):
            AuthorityAuditEventInput(**values)
        with pytest.raises(ValidationError):
            TypeAdapter(AuthorizationDecisionResourceType).validate_python(token)
        assert token not in CONTEXT_DIGEST_RESOURCE_TYPES


def test_activation_audit_mapping_does_not_activate_authority():
    project, guide = uuid4(), uuid4()
    context = ProjectGuideActivationResourceContext(
        resource_type="project_guide_activation",
        resource_id=guide,
        scope_project_id=project,
        guide_id=guide,
        guide_version="guide-A",
        source_snapshot_id=uuid4(),
        sufficiency_report_id=uuid4(),
        submission_artifact_policy_id=uuid4(),
        pre_submit_checker_policy_id=uuid4(),
        post_submit_checker_policy_id=uuid4(),
        review_policy_id=uuid4(),
        revision_policy_id=uuid4(),
        active_bundle_digest="sha256:" + "a" * 64,
        activation_generation=1,
    )
    assert project_authority_audit_target(context, ActionId.PROJECT_GUIDE_ACTIVATE) == (
        str(project),
        "project_guide_activation",
        str(guide),
        "project",
        str(project),
    )
    assert ACTION_BY_ID[ActionId.PROJECT_GUIDE_ACTIVATE].availability is ActionAvailability.PLANNED
