# Chunk Contract: WS-ARCH-001-04C — Durable post-submit execution

Disposition: Planned. Dependencies: delivered 04A, 04B,
[ARCH-04B2 output custody](../../WS-ARCH-001-04B2.md) and POL-07. Risk: L1.

The current implementation contract is
[ARCH-04C durable execution and current results](../../WS-ARCH-001-04C.md).
It owns allowed files, prohibited changes, schema replacement, exact request and
worker-lease custody, acceptance criteria and verification.

CHECKERS extends its existing run/result aggregate and reserves each exact request
with one per-Submission currentness fence. It uses the existing phase facade and
registry, consumes its public materialization port, and atomically persists
complete member results and a bounded outbox event. Production authority remains
deny-only until ARCH-04D. The current structural catalogue has no generated output
slots or provider calls; no separate checker Celery task is added. ARCH-04E owns
canonical request production and registration in the shared outbox delivery path.

The previous skeleton is superseded by that current-main contract. In particular,
hypothetical nonempty output/provider proof is not current execution scope.
Retained checker history is preserved by migration refusal, not deleted or
backfilled with invented custody. CHECKERS never accepts a contribution or
mutates TASK state.
