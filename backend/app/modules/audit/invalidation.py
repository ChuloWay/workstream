"""Project only supported exact AUTH cause chains for hidden TASK reconciliation."""

import json
from uuid import UUID

from app.modules.audit.api import AssignmentInvalidationCause, AuthorityInvalidationFacts
from app.modules.audit.repository import AuditRepository
from app.modules.audit.schemas import AuthorityAuditEventInput, AuthorityEventType


def _validated(row):
    if (row.event_domain, row.auth_source, row.event_version, row.is_dev_auth) != (
        "authority",
        "local_authority",
        1,
        False,
    ):
        raise ValueError("invalid authority source")
    fields = {
        key: getattr(row, {"event_id": "id", "actor_ref": "actor_id"}.get(key, key))
        for key in AuthorityAuditEventInput.model_fields
    }
    return AuthorityAuditEventInput.model_validate_json(json.dumps(fields, default=str))


def _project(invalidation_row, cause_row):
    invalidation, cause = _validated(invalidation_row), _validated(cause_row)
    if (
        invalidation.event_type is not AuthorityEventType.AUTHORITY_INVALIDATION_REQUESTED
        or invalidation.entity_type != "authority_invalidation"
        or invalidation.entity_id != str(invalidation.event_id)
        or invalidation.invalidation_cause_event_id != cause.event_id
        or invalidation.before_facts.get("effective") is not True
        or invalidation.after_facts.get("effective") is not False
        or invalidation.idempotency_reference is None
        or any(
            getattr(invalidation, key) != getattr(cause, key)
            for key in (
                "request_id",
                "correlation_id",
                "actor_ref_kind",
                "actor_ref",
                "permission_id",
                "idempotency_reference",
                "project_id",
            )
        )
        or cause.target_actor_ref_kind is None
        or cause.target_actor_ref_kind.value != "actor_profile"
        or cause.target_actor_ref is None
        or cause.entity_id != cause.resource_id
        or cause.target_ref_id != cause.resource_id
        or cause.target_ref_kind != cause.resource_type
    ):
        return None
    actor_id = UUID(cause.target_actor_ref)
    project_id = None
    if cause.event_type is AuthorityEventType.PROJECT_ROLE_GRANT_REVOKED:
        kind = AssignmentInvalidationCause.SUBMITTER_GRANT_REVOKED
        project_id = UUID(cause.project_id)
        projection = {
            "role": "submitter",
            "scope_type": "project",
            "scope_id": str(project_id),
            "future_obligation": "auth13_assignment",
        }
        if (
            cause.entity_type != "project_role_grant"
            or cause.resource_type != "project_role_grant"
            or cause.before_facts.get("role") != "submitter"
            or cause.after_facts.get("role") != "submitter"
            or cause.after_facts.get("scope_id") != str(project_id)
            or invalidation.before_facts != {"effective": True, **projection}
            or invalidation.after_facts != {"effective": False, **projection}
            or invalidation.target_actor_ref != str(actor_id)
            or invalidation.target_actor_ref_kind != cause.target_actor_ref_kind
            or invalidation.target_ref_kind != "project_role_grant"
            or invalidation.target_ref_id != cause.resource_id
            or invalidation.invalidation_target_kind != "project_role_grant"
            or invalidation.invalidation_target_ref != cause.resource_id
            or invalidation.resource_type != "project_role_grant"
            or invalidation.resource_id != cause.resource_id
        ):
            return None
    else:
        kind = {
            AuthorityEventType.ACTOR_PROFILE_SUSPENDED: AssignmentInvalidationCause.ACTOR_SUSPENDED,
            AuthorityEventType.ACTOR_PROFILE_DEACTIVATED: AssignmentInvalidationCause.ACTOR_DEACTIVATED,
            AuthorityEventType.ACTOR_IDENTITY_LINK_REVOKED: AssignmentInvalidationCause.IDENTITY_LINK_REVOKED,
        }.get(cause.event_type)
        if kind is None:
            return None
        target_type = (
            "actor_identity_link"
            if kind is AssignmentInvalidationCause.IDENTITY_LINK_REVOKED
            else "actor_profile"
        )
        if (
            cause.project_id is not None
            or cause.entity_type != target_type
            or cause.resource_type != target_type
            or (target_type == "actor_profile" and cause.resource_id != str(actor_id))
            or invalidation.before_facts != {"effective": True}
            or invalidation.after_facts != {"effective": False}
            or invalidation.invalidation_target_kind != "actor_profile"
            or invalidation.invalidation_target_ref != str(actor_id)
            or invalidation.resource_type != "actor_profile"
            or invalidation.resource_id != str(actor_id)
            or invalidation.target_actor_ref is not None
            or invalidation.target_ref_id is not None
        ):
            return None
    return AuthorityInvalidationFacts(
        invalidation_event_id=invalidation.event_id,
        cause_event_id=cause.event_id,
        contributor_id=actor_id,
        cause=kind,
        target_id=UUID(cause.resource_id),
        project_id=project_id,
    )


class CommittedAuthorityInvalidationReader:
    """Independent sessions prevent uncommitted caller evidence from self-validating."""

    def __init__(self, session_factory):
        self._sessions = session_factory

    async def read_invalidation(self, event_id: UUID) -> AuthorityInvalidationFacts | None:
        if type(event_id) is not UUID:
            return None
        async with self._sessions() as session:
            rows = await AuditRepository(session).invalidation_chain(event_id)
            if rows is None:
                return None
            try:
                return _project(*rows)
            except (AttributeError, TypeError, ValueError):
                return None
