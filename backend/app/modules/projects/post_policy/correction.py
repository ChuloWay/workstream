"""Compose post-policy correction with the existing unified successor operation."""

from datetime import UTC, datetime

from app.core.identifiers import new_record_id

from app.modules.projects.api.guide_proposals import GuideProposalCorrection, GuideProposalError
from app.modules.projects.api.post_policy import PostPolicyReceipt
from app.modules.projects.guide_compilation.proposal_correction import (
    correction_locator, persist_staged_correction, stage_proposal_correction,
)

from .custody import operation_receipt, require_post_authority


async def request_post_policy_correction(service, command, actor, request_id, guide_authorization):
    """Acquire both authorities before guide locks; close both before product writes."""
    target = command.target
    selector_id = service._human_operation_id(actor, command.idempotency_key, "correction")
    post_locator = service._locator(target.proposal, actor, request_id, selector_id, "correction")
    guide_command = GuideProposalCorrection(
        target=target.proposal, idempotency_key=command.idempotency_key, reason=command.reason,
    )
    guide_locator = correction_locator(guide_command, actor, request_id)
    async with service.authorization.prepare_post_policy_operation(post_locator) as prepared:
        service._require_prepared(prepared)
        async with guide_authorization.prepare_proposal_operation(guide_locator) as guide_prepared:
            locked, policy, custody = await service.repository.lock_policy(service._selection(target))
            if custody.target != target:
                raise GuideProposalError("proposal_stale")
            existing = await service.repository.human_operation(
                actor.actor_profile_id, "correction", command.idempotency_key
            )
            if existing is None:
                await service.repository.require_current_upstream(locked)
                if policy.lifecycle_status not in {"compiled", "approved"}:
                    raise GuideProposalError("proposal_stale")
            staged = await stage_proposal_correction(
                service.session, guide_command, actor, guide_locator, guide_prepared, locked=locked,
            )
            operation_id = existing.operation_id if existing else new_record_id()
            receipt = PostPolicyReceipt(
                operation_id=operation_id, kind="correction", target=target, correction=staged.receipt,
            )
            if existing:
                if staged.authority is not None or operation_receipt(existing) != receipt:
                    raise GuideProposalError("operation_conflict")
                return await service._replay(existing, command, actor, post_locator, prepared)
            facts = service._facts(post_locator, command, receipt, lifecycle_status=policy.lifecycle_status)
            authority = await prepared.consume_new(facts)
            require_post_authority(authority, facts, actor)
    await persist_staged_correction(service.session, guide_command, actor, staged)
    service._supersede(policy, operation_id, datetime.now(UTC), "correction_requested")
    await service._persist(command, actor, receipt, facts, authority, command.idempotency_key)
    return receipt
