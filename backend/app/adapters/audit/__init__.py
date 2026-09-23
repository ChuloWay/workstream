"""Shared audit owner composition for typed product transition ports."""

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.schemas import (
    LifecycleAuditEntityType, LifecycleAuditEventInput, LifecycleAuditEventType,
    LifecycleAuditReason, LifecycleAuditReferenceKind,
)
from app.modules.audit.service import LifecycleAuditParticipant
from app.modules.audit.invalidation import CommittedAuthorityInvalidationReader
from app.modules.audit.api import AuthorityInvalidationPort
from app.modules.audit.repository import AuditRepository, LIFECYCLE_AUTH_SOURCE
from app.modules.tasks.api.assignment_invalidation import (
    AssignmentInvalidationAuditPort, AssignmentInvalidationEvidence,
    AssignmentInvalidationAuthority, AssignmentInvalidationUnavailable,
    assignment_invalidation_evidence_id,
)
from app.modules.tasks.api import TaskAuthorityOperation, TaskTransitionAuditPort, TaskTransitionFacts


class _TaskTransitionAudit:
    def __init__(self, session: AsyncSession) -> None:
        self._participant = LifecycleAuditParticipant(session)

    async def record(self, facts: TaskTransitionFacts) -> None:
        event_type = {
            TaskAuthorityOperation.CLAIM: LifecycleAuditEventType.TASK_CLAIMED,
            TaskAuthorityOperation.START: LifecycleAuditEventType.TASK_STARTED,
            TaskAuthorityOperation.START_OVERRIDE: LifecycleAuditEventType.TASK_START_OVERRIDDEN,
        }[facts.operation]
        await self._participant.add_event(LifecycleAuditEventInput(
            event_id=uuid4(), entity_type=LifecycleAuditEntityType.TASK, entity_id=facts.task_id,
            event_type=event_type, from_status=facts.from_status, to_status=facts.to_status,
            actor_id=facts.actor_profile_id, reason=LifecycleAuditReason.STATE_CHANGED,
            task_reason=facts.reason if facts.reason and facts.reason.strip() else None,
            references={
                LifecycleAuditReferenceKind.PROJECT: facts.project_id,
                LifecycleAuditReferenceKind.TASK: facts.task_id,
                LifecycleAuditReferenceKind.ASSIGNMENT: facts.assignment_id,
                LifecycleAuditReferenceKind.AUTHORIZATION_DECISION: facts.authorization_decision_id,
            },
        ))


def task_transition_audit(session: AsyncSession) -> TaskTransitionAuditPort:
    """Use the existing participant in the same caller-owned transaction."""
    return _TaskTransitionAudit(session)


def committed_authority_invalidation(session_factory) -> AuthorityInvalidationPort:
    """Keep cause validation and independent committed reads in AUDIT."""
    return CommittedAuthorityInvalidationReader(session_factory)


class _AssignmentInvalidationAudit:
    def __init__(self, session):
        self._repo = AuditRepository(session)
        self._participant = LifecycleAuditParticipant(session)

    @staticmethod
    def _references(target, decision_id):
        return {
            LifecycleAuditReferenceKind.PROJECT: target.project_id,
            LifecycleAuditReferenceKind.TASK: target.task_id,
            LifecycleAuditReferenceKind.ASSIGNMENT: target.assignment_id,
            LifecycleAuditReferenceKind.AUTHORITY_INVALIDATION: target.authority_invalidation_event_id,
            LifecycleAuditReferenceKind.AUTHORIZATION_DECISION: decision_id,
        }

    async def read_release(self, target):
        row = await self._repo.lifecycle_event(assignment_invalidation_evidence_id(target))
        if row is None:
            return None
        try:
            refs = row.event_payload["references"]
            decision = UUID(refs["authorization_decision_id"])
            expected = {key.value: str(value) for key, value in self._references(target, decision).items()}
            if (
                row.event_domain != "legacy_lifecycle" or row.auth_source != LIFECYCLE_AUTH_SOURCE
                or row.entity_type != "task" or row.entity_id != str(target.task_id)
                or row.event_type != LifecycleAuditEventType.TASK_ASSIGNMENT_AUTHORITY_REVOKED.value
                or row.from_status not in {"claimed", "in_progress"} or row.to_status != "ready"
                or row.event_payload != {"references": expected}
                or row.reason != LifecycleAuditReason.STATE_CHANGED.value or row.is_dev_auth
            ):
                raise ValueError("invalid release receipt")
            return AssignmentInvalidationEvidence(target, AssignmentInvalidationAuthority(
                actor_profile_id=UUID(row.actor_id), decision_id=decision,
            ), row.from_status)
        except (AttributeError, KeyError, TypeError, ValueError):
            raise AssignmentInvalidationUnavailable("assignment reconciliation unavailable") from None

    async def record_release(self, evidence):
        target = evidence.target
        await self._participant.add_event(LifecycleAuditEventInput(
            event_id=assignment_invalidation_evidence_id(target),
            entity_type=LifecycleAuditEntityType.TASK, entity_id=target.task_id,
            event_type=LifecycleAuditEventType.TASK_ASSIGNMENT_AUTHORITY_REVOKED,
            actor_id=evidence.authority.actor_profile_id,
            reason=LifecycleAuditReason.STATE_CHANGED,
            from_status=evidence.from_status, to_status="ready",
            references=self._references(target, evidence.authority.decision_id),
        ))


def assignment_invalidation_audit(session: AsyncSession) -> AssignmentInvalidationAuditPort:
    """The existing typed lifecycle participant is the atomic release receipt."""
    return _AssignmentInvalidationAudit(session)
