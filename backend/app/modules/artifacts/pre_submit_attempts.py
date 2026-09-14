"""ART invocation custody; completed outcomes live only in canonical evidence."""

from __future__ import annotations

from typing import TYPE_CHECKING
from dataclasses import asdict, dataclass, replace
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import canonical_json_hash
from app.modules.artifacts.models import (
    PreSubmitEvidenceResult, PreSubmitEvidenceSet, PreSubmitExecutionAttempt,
)
from app.modules.artifacts.pre_submit_evidence import (
    PersistedPreSubmitEvidence, PreSubmitEvidenceConflict, PreSubmitEvidenceContext,
    PreSubmitEvidencePersistenceResult, PreSubmitExecutionCustody, PreSubmitExecutionResult,
    _PreSubmitEvidenceRepository, _validate_execution, pre_submit_failure_audit_payload,
)
from app.modules.checkers.api import (
    EffectivePreSubmissionExecutionPlan, SubmissionPacketView,
    PreSubmissionExecutionEntryFacts, PreSubmissionExecutionFacts,
)

if TYPE_CHECKING:
    from app.modules.artifacts.submission_materialization import PreparedBundleMaterializationRequest
    from app.modules.artifacts.pre_submit_evidence import PreSubmitEvidencePersistenceRequest


def logical_request(
    context: PreSubmitEvidenceContext,
    plan: EffectivePreSubmissionExecutionPlan,
    packet: SubmissionPacketView,
) -> dict[str, object]:
    """Hash logical input without substituting a retry generation for original custody."""
    if canonical_json_hash(plan.as_dict()) != plan.plan_sha256:
        raise PreSubmitEvidenceConflict("pre_submit_attempt_plan_invalid")
    values = {key: str(value) if isinstance(value, UUID) else value
              for key, value in asdict(context).items() if key != "prepared_generation_id"}
    return {
        **values, "effective_plan_sha256": plan.plan_sha256,
        "packet_sha256": canonical_json_hash(asdict(packet)),
    }


@dataclass(frozen=True, slots=True)
class _Reservation:
    attempt_id: UUID
    claim_nonce: UUID
    request_digest: str
    request: PreparedBundleMaterializationRequest


class PreSubmitAttemptClaim:
    """A single original invocation, minted only after its reservation commits."""

    __slots__ = ("attempt_id", "request_digest", "_nonce", "_request", "_started", "_execution", "_session")

    def __init__(self, *args: object, **kwargs: object) -> None:
        """Reject caller-created invocation authority."""
        raise TypeError("pre-submit claims are issued by ART")

    def __reduce__(self):
        """Keep the winning invocation bound to this process and session."""
        raise TypeError("pre-submit claims cannot be serialized")

    async def _reserved(
        self, session: AsyncSession, *, lock: bool = False,
    ) -> PreSubmitExecutionAttempt:
        """Check committed invocation facts in the issuing root session."""
        if session is not self._session or not session.in_transaction() or session.in_nested_transaction():
            raise PreSubmitEvidenceConflict("pre_submit_attempt_claim_invalid")
        statement = select(PreSubmitExecutionAttempt).where(
            PreSubmitExecutionAttempt.id == str(self.attempt_id),
        ).execution_options(populate_existing=True)
        if lock:
            statement = statement.with_for_update()
        row = await session.scalar(statement)
        if (row is None or row.status != "reserved" or row.evidence_set_id is not None
                or row.claim_nonce != str(self._nonce) or row.request_digest != self.request_digest
                or row.prepared_generation_id != str(self._request.prepared_artifact.generation_id)):
            raise PreSubmitEvidenceConflict("pre_submit_attempt_claim_invalid")
        return row

    async def consume(
        self, session: AsyncSession, request: PreparedBundleMaterializationRequest,
    ) -> None:
        """Fence direct materializer calls before constructing the CHECKER processor."""
        if self._started or replace(request, prepared_authorization=None) != self._request:
            raise PreSubmitEvidenceConflict("pre_submit_attempt_claim_invalid")
        self._started = True
        await self._reserved(session)

    def finish(self, execution: PreSubmitExecutionResult) -> None:
        """Retain the exact owner-issued result object for final persistence."""
        if not self._started or self._execution is not None:
            raise PreSubmitEvidenceConflict("pre_submit_attempt_claim_invalid")
        self._execution = execution

    async def validate_completion(
        self, session: AsyncSession, request: PreSubmitEvidencePersistenceRequest,
    ) -> None:
        """A UUID or copied result cannot stand in for the winning invocation."""
        if not self._started or self._execution is not request.execution:
            raise PreSubmitEvidenceConflict("pre_submit_attempt_execution_invalid")
        await self._reserved(session, lock=True)

    async def complete(self, session: AsyncSession, evidence_id: UUID) -> None:
        """Link evidence atomically; deferred database guards verify both directions."""
        result = await session.execute(update(PreSubmitExecutionAttempt).where(
            PreSubmitExecutionAttempt.id == str(self.attempt_id),
            PreSubmitExecutionAttempt.claim_nonce == str(self._nonce),
            PreSubmitExecutionAttempt.status == "reserved",
        ).values(status="completed", evidence_set_id=str(evidence_id)))
        if result.rowcount != 1:
            raise PreSubmitEvidenceConflict("pre_submit_attempt_completion_conflict")


class PreSubmitAttemptStore:
    """Own reservation issuance and verified reads of canonical ART results."""

    def __init__(self, session: AsyncSession) -> None:
        """Bind issuance to one transaction-owning ART request."""
        self._session = session
        self._pending: _Reservation | None = None

    async def reserve(
        self, *, context: PreSubmitEvidenceContext, plan: EffectivePreSubmissionExecutionPlan,
        packet: SubmissionPacketView, idempotency_key: UUID,
        request: PreparedBundleMaterializationRequest,
    ) -> _Reservation | PreSubmitExecutionAttempt:
        """Reserve after authorization; an existing unresolved attempt cannot execute."""
        if not self._session.in_transaction() or self._session.in_nested_transaction():
            raise RuntimeError("pre-submit reservation requires one root transaction")
        body = logical_request(context, plan, packet)
        digest = canonical_json_hash(body)
        attempt_id = uuid5(context.actor_profile_id, f"pre-submit:{idempotency_key}")
        nonce = uuid4()
        inserted = await self._session.scalar(insert(PreSubmitExecutionAttempt).values(
            id=str(attempt_id), idempotency_key=str(idempotency_key),
            actor_profile_id=str(context.actor_profile_id), identity_link_id=str(context.identity_link_id),
            task_id=str(context.task_id), assignment_id=str(context.assignment_id),
            prepared_generation_id=str(context.prepared_generation_id), claim_nonce=str(nonce),
            request_json=body, request_digest=digest, status="reserved",
        ).on_conflict_do_nothing(index_elements=["actor_profile_id", "idempotency_key"])
          .returning(PreSubmitExecutionAttempt.id))
        if inserted is not None:
            self._pending = _Reservation(attempt_id, nonce, digest,
                                         replace(request, prepared_authorization=None))
            return self._pending
        row = await self._session.scalar(select(PreSubmitExecutionAttempt).where(
            PreSubmitExecutionAttempt.actor_profile_id == str(context.actor_profile_id),
            PreSubmitExecutionAttempt.idempotency_key == str(idempotency_key),
        ).execution_options(populate_existing=True))
        if row is None or row.request_digest != digest or row.request_json != body:
            raise PreSubmitEvidenceConflict("pre_submit_attempt_request_conflict")
        if row.status != "completed":
            raise PreSubmitEvidenceConflict("pre_submit_attempt_outcome_unresolved")
        return row

    async def committed_claim(self, reservation: object) -> PreSubmitAttemptClaim:
        """Mint only after a successful commit, with a new transaction visibility check."""
        if (self._session.in_transaction() or type(reservation) is not _Reservation
                or reservation is not self._pending):
            raise PreSubmitEvidenceConflict("pre_submit_attempt_not_committed")
        self._pending = None
        async with self._session.begin():
            row = await self._session.get(PreSubmitExecutionAttempt, str(reservation.attempt_id),
                                          populate_existing=True)
            if (row is None or row.claim_nonce != str(reservation.claim_nonce)
                    or row.request_digest != reservation.request_digest or row.status != "reserved"):
                raise PreSubmitEvidenceConflict("pre_submit_attempt_not_committed")
        claim = object.__new__(PreSubmitAttemptClaim)
        claim.attempt_id = reservation.attempt_id
        claim.request_digest = reservation.request_digest
        claim._nonce = reservation.claim_nonce
        claim._request = reservation.request
        claim._started = False
        claim._execution = None
        claim._session = self._session
        return claim

    async def read_completed(
        self, *, row: PreSubmitExecutionAttempt, context: PreSubmitEvidenceContext,
        plan: EffectivePreSubmissionExecutionPlan,
    ) -> PreSubmitEvidencePersistenceResult:
        """Return original evidence after caller revalidates original fixed-service facts."""
        evidence = await self._session.get(PreSubmitEvidenceSet, row.evidence_set_id,
                                           populate_existing=True)
        if (evidence is None or row.status != "completed" or evidence.attempt_id != row.id
                or evidence.attempt_request_digest != row.request_digest):
            raise PreSubmitEvidenceConflict("pre_submit_attempt_evidence_invalid")
        rows = tuple((await self._session.scalars(select(PreSubmitEvidenceResult).where(
            PreSubmitEvidenceResult.evidence_set_id == evidence.id,
        ).order_by(PreSubmitEvidenceResult.result_order))).all())
        if (len(rows) != len(plan.entries)
                or any(r.metadata_json is None or r.checker_order is None for r in rows)):
            raise PreSubmitEvidenceConflict("pre_submit_attempt_result_unavailable")
        execution = PreSubmitExecutionResult(
            custody=PreSubmitExecutionCustody(
                prepared_generation_id=UUID(row.prepared_generation_id),
                archive_sha256=evidence.archive_sha256, archive_byte_count=evidence.archive_byte_count,
                semantic_manifest_sha256=evidence.semantic_manifest_sha256,
                storage_scheme=evidence.storage_scheme,
            ),
            checker_facts=PreSubmissionExecutionFacts(
                plan_sha256=evidence.effective_plan_sha256, eligible=evidence.eligible,
                entries=tuple(PreSubmissionExecutionEntryFacts(
                    dispatch_authority=r.dispatch_authority, definition_id=r.definition_id,
                    definition_version=r.definition_version, public_name=r.public_name,
                    policy_source=r.source, effective_plan_sha256=r.effective_plan_sha256,
                    rule_instance_id=r.rule_instance_id, locked_policy_sha256=r.locked_policy_sha256,
                    phase=r.phase, order=r.checker_order, classification=r.classification,
                    severity=r.severity, checker_execution_status=r.status, failure_code=r.failure_code,
                    message_code=r.message_code, metadata=tuple(tuple(item) for item in r.metadata_json),
                ) for r in rows),
            ),
        )
        _validate_execution(plan, execution)
        original = replace(context, prepared_generation_id=UUID(row.prepared_generation_id))
        identity = original.operation_identity(effective_plan_sha256=plan.plan_sha256,
                                              attempt_id=UUID(row.id),
                                              attempt_request_digest=row.request_digest)
        expected = _PreSubmitEvidenceRepository._set_values(original, plan, execution, identity)
        if any(getattr(evidence, name) != value for name, value in expected.items()):
            raise PreSubmitEvidenceConflict("pre_submit_attempt_result_digest_invalid")
        for ordinal, (member, entry) in enumerate(zip(rows, execution.entries, strict=True)):
            values = _PreSubmitEvidenceRepository._result_values(ordinal, entry,
                                                                 plan.entries[ordinal].result_schema)
            if any(getattr(member, name) != value for name, value in values.items()):
                raise PreSubmitEvidenceConflict("pre_submit_attempt_member_invalid")
        reference = PersistedPreSubmitEvidence(UUID(evidence.id), identity, True)
        failure_audit = None if execution.eligible else pre_submit_failure_audit_payload(
            actor_profile_id=original.actor_profile_id, project_id=original.project_id,
            task_id=original.task_id, prepared_generation_id=original.prepared_generation_id,
            evidence=reference, execution=execution, catalogue_id=plan.catalogue_id,
            catalogue_version=plan.catalogue_version,
        )
        return PreSubmitEvidencePersistenceResult(reference, None, failure_audit, execution)
