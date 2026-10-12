"""Public ART contracts for hidden contributor bundle preparation."""

from __future__ import annotations

from collections.abc import AsyncIterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.modules.authorization.api import ActorIdentityFacts
from app.modules.checkers.api.selected_pre_submit import SelectedPreSubmitExecutionFacts


class SubmissionBundlePreparationRejected(RuntimeError):
    """Reject preparation with one stable ART-owned failure code."""


class SubmissionBundlePreparationCheckFailed(SubmissionBundlePreparationRejected):
    """Carry the exact bounded CHECKERS facts for one blocked preparation."""

    def __init__(
        self,
        facts: SelectedPreSubmitExecutionFacts,
    ) -> None:
        if type(facts) is not SelectedPreSubmitExecutionFacts:
            raise TypeError("pre-submission feedback facts are invalid")
        if facts.eligible is not False:
            raise ValueError("blocked pre-submission facts require eligible false")
        super().__init__("pre_submission_checker_failed")
        self.facts = facts

    def public_results(self) -> list[dict[str, object]]:
        """Return sanitized ordered work findings without execution authority."""
        default = self.facts.workstream_default
        results: list[dict[str, object]] = [
            {
                "source": "workstream_default",
                "check_id": item.check_id,
                "status": item.status,
                "failure_code": item.failure_code,
                "finding_count": item.finding_count,
            }
            for item in default.checks
        ]
        results.extend(
            {
                "source": "workstream_default",
                "status": "warning",
                "warning_code": item.code,
            }
            for item in default.warnings
        )
        results.extend(
            {
                "source": "project_external_checker",
                "requirement_id": member.requirement_id,
                "registry_entry_id": str(member.registry_entry_id),
                "registry_entry_digest": member.registry_entry_digest,
                "status": member.result.verdict,
                "findings": [
                    finding.model_dump(mode="json")
                    for finding in member.result.findings
                ],
            }
            for member in self.facts.external_members
        )
        return results


class SubmissionBundlePreparationUnavailable(RuntimeError):
    """Conceal unavailable or denied preparation authority."""


class SubmissionBundlePreparationInfrastructureUnavailable(RuntimeError):
    """Authorized preparation cannot safely recover its execution or continuation."""


class SubmissionBundlePreparationStatus(StrEnum):
    """Closed public state vocabulary for one ART preparation operation."""

    PREPARED = "prepared"
    PUT_IN_FLIGHT = "put_in_flight"
    OBJECT_CONFIRMED = "object_confirmed"
    STORED_PENDING_VERIFICATION = "stored_pending_verification"
    OBSERVED_CONFIRMED = "observed_confirmed"
    ACKNOWLEDGEMENT_UNKNOWN = "acknowledgement_unknown"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    CONFLICT = "conflict"
    INTEGRITY_MISMATCH = "integrity_mismatch"
    MISSING = "missing"
    ABSENT_REPLAY_REQUIRED = "absent_replay_required"
    STALE = "stale"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class SubmissionBundlePreparationRequest:
    """One continuous contributor ZIP request with server-owned actor facts."""

    actor: ActorIdentityFacts
    request_id: UUID
    correlation_id: UUID
    task_id: UUID
    assignment_id: UUID
    predecessor_submission_id: UUID | None
    idempotency_key: UUID
    summary: str
    contributor_attestation: str
    media_type: str
    byte_source: AsyncIterable[bytes]


@dataclass(frozen=True, slots=True)
class SubmissionBundlePreparationResult:
    """Bounded preparation result without custody or provider coordinates."""

    put_attempt_id: UUID
    admission_id: UUID | None
    submission_bundle_preparation_status: SubmissionBundlePreparationStatus
    replayed: bool


class SubmissionBundlePreparationCommand(Protocol):
    """Prepare one hidden contributor bundle through the sole ART command."""

    async def prepare(
        self, request: SubmissionBundlePreparationRequest
    ) -> SubmissionBundlePreparationResult:
        """Run the continuous fail-closed preparation workflow."""
