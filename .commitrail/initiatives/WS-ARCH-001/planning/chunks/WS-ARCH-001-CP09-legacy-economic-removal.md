# Chunk Contract: WS-ARCH-001-CP09 — Economic Path Removal Coordination

Disposition: Superseded by the [completed bounded cleanup](../../../../changes/remove-obsolete-task-payment-policy.md).
Risk: L1.

The original coordination contract postponed physical removal until CHECKERS
and public Submission cutover. Current owner inspection found the payment
storage unused after the canonical ContributionPolicy replacements; public
intake activation is not a prerequisite for removing it.

Migration `0023_remove_task_payment_policy` removes the obsolete guide-keyed
policy table and TASK/Submission payment fields. The same change removes the
remaining repository, response and CLI consumers. It preserves historical
migration files rather than rewriting the baseline and introduces no alias,
fallback, dual read/write or guessed conversion.

The migration locks affected storage and refuses retained policy rows, populated
removed fields or obsolete immutable receipt keys before DDL. Such retained
facts require a separately bounded, human-owned preservation design; the cleanup
does not delete, backfill or rewrite them. The implementation and verification
are owned by the linked cleanup record, not another CP09 implementation.

Physical cleanup neither activates contribution recognition or fulfillment nor
blocks the remaining canonical `allow_review`/automated-acceptance integration.

## Durable outcome

Superseded. Use the cleanup record for delivered removal and the current
architecture plan for remaining runtime boundaries.
