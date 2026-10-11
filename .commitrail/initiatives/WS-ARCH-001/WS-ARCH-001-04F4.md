# ARCH-04F4 — Operator recovery of terminal checker infrastructure failure

- Initiative: `WS-ARCH-001`
- Durable disposition: `Planned`
- Intended merge outcome: an exact, reason-bound Operator request can reserve and dispatch one new CHECKERS generation after the current run has terminal `infrastructure_failed` evidence, while the failed run remains immutable.

## Intent and current boundary

The first contributor journey must recover when the platform cannot finish a post-submit check. Today an expired unfinished lease is reclaimed on the same run, but `PostSubmissionExecutor` replays a terminal `infrastructure_failed` result without executing again. `EvaluationCoordinator` already owns the per-Submission generation/fence transaction. Initial `SubmissionDispatch` and `EvaluationRequestHandler` carry only generation one; `operations.checker.retry` is an Operator permission with a planned, unavailable action. No public recovery command exists. `task_setup_blocked` is a different completed result: CHECKERS shows its details only in management history, TASK does not route it to contributor remediation, and this change does not treat it as infrastructure failure.

This is one hidden recovery command and its exact delivery through the existing worker, not a second checker runner, retry job subsystem, or public API. Setup-fault manager repair is the next separate boundary after its locked-policy correction rules are specified.

## Bounded change

### Allowed

- `backend/app/modules/checkers/api/execution.py`, `execution_coordination.py`, `execution_repository.py`, and `models.py`: exact retry facts and one new generation through the existing currentness owner; preserve original terminal result and same-identity unfinished lease recovery.
- `backend/app/modules/tasks/evaluation_delivery.py`, `submission_dispatch.py`, and a focused `backend/app/modules/tasks/checker_retry.py`: the existing request event/handler accepts a distinct, explicit retry receipt and recovers its stored request; no invented outbox worker. Initial dispatch remains exact and immutable.
- `backend/app/modules/authorization/catalogue.py`, `policy.py`, `kernel.py`, `domain/checker_retry.py`, `checker_retry_authorization.py`, and `backend/app/adapters/auth/__init__.py`: activate the existing Operator action with one exact system-scope resource/actor/decision binding. The lead coordinates the shared catalogue edit with the intake branch.
- `backend/app/modules/audit/schemas.py`, `backend/alembic/versions/0034_checker_retry.py`: append-only initiation evidence and a retry receipt tied to source run, successor run, AUTH decision and request event; 0034 follows the intake branch's 0033, subject to final linear migration reconciliation. No retained evidence is deleted or rewritten.
- Focused tests under `backend/tests/checkers/execution/`, `backend/tests/tasks/evaluation_delivery/`, `backend/tests/authorization/`, and `backend/tests/migrations/`; affected current docs and this record. `docs/roadmap_status.md` is assessed against the intended merged hidden capability.

### Not allowed

No public route or production handler registration, replacement ZIP writer, contributor remediation from infrastructure/setup failures, setup policy mutation, Review, FinalAcceptance, contribution, award, payment, generic retry framework, compatibility dispatch path, or broad alteration of coordinator generation semantics. No direct retry of a `completed` result. No mutation of a terminal run or its result/member/receipt evidence.

## Design and decisions for plan review

The hidden command takes the Operator's request key, reason, and exact source run. It first identifies immutable owner facts for authority, then takes fresh system Operator AUTH custody and locks TASK -> active Assignment -> latest submitted Submission -> per-Submission CHECKERS advisory key -> fence -> current run. It revalidates the exact source under those locks and allows only `infrastructure_failed`, with no newer Submission, routed outcome, or successor. Its new request copies the stored bounded content and locked lineage; only request ID, digest and generation change. The existing coordinator reserves the successor and advances the fence in the caller transaction. One durable retry receipt closes actor/key/digest, reason, source/successor IDs, actual AUTH decision, initiation audit and request event in the same commit. The receipt provides the retry event reader with exact source provenance. Duplicate requests first select that retained receipt and, under fresh authority, validate its exact committed closure without reapplying new-request eligibility: the source has necessarily ceased to be current. A different key for an already-owned source conflicts. The existing request handler invokes the same executor after selecting either the exact initial dispatch or exact retry receipt by committed event facts. Neither branch accepts a source selected merely by event payload.

The current generic coordinator permits later generations for its own currentness/race consumers. This change does not silently narrow it: the Operator command enforces terminal eligibility, while deferred SQL requires a matching authorized retry receipt whenever a fence supersedes an `infrastructure_failed` run. The receipt/SQL closure proves that trigger's authority at commit without changing valid queued/completed-success successor controls. Plan review must confirm that predicate against existing generation-two fixtures and all current application callers before implementation. If another reachable path requires terminal-failure supersession, revise this record with a discriminating valid control rather than adding a bypass.

## Acceptance criteria and verification

- Real PostgreSQL + local/MinIO fixture: a terminal infrastructure failure has no completion route; one authorized Operator retry creates generation `n+1`, exact supersedes/current fence, new request event and audit/decision evidence atomically. The old result remains byte-for-byte unchanged. The existing handler executes the new request and subsequent completion uses the current result only.
- Duplicate and response-loss replay return identical IDs without another event or run, after fresh authority and exact original-decision validation; concurrent same/different-key requests produce one successor. Revoked, foreign, non-Operator, stale, completed-success, queued/running and setup-blocked sources deny with no mutation or artifact read. Unfinished transport redelivery keeps its original request/run identity.
- Rollback and actual audit/outbox insertion failure leave no successor/fence advancement, receipt or authority evidence. Direct SQL rejects a forged or crossed retry receipt, substituted source/successor/event/decision, and incomplete committed custody. A stale worker from the failed or displaced run cannot publish current completion.
- Run focused owner tests, real PostgreSQL migration upgrade/preservation and concurrent-session tests, local/MinIO execution proof where byte I/O is claimed, then repository required checks. Include a valid preexisting generation-two currentness fixture when testing any guard change; a denial test alone is insufficient. Run stale wording/link checks and reconcile roadmap claims.

## Risk and review routing

- Risk class: `L1` (Operator authority, immutable evidence, schema and concurrency).
- Required reviewers: architecture, security, QA, test delta, product/operations, reuse/dedup, documentation; CI integrity if gate or workflow files change. Internal plan review precedes implementation.
- Human review focus: exact Operator authority and replay; terminal-only source; lock order and rollback; no contributor blame for setup/platform fault; initial-event preservation and no premature production activation.

## Evidence and next boundary

Planning inspection at merged base `735cf2659`: `PostSubmissionExecutor._claim` replays both terminal statuses; `EvaluationCoordinator.reserve_current_evaluation` already serializes TASK/advisory/fence/run custody and records supersession; `SubmissionDispatch`/`EvaluationDeliveryRequestReader` prove only generation one; the Operator action is planned in AUTH; CHECKERS history hides setup details from contributors. This is contract feasibility, not executed retry proof. `0032_checker_remediation` is the present migration head; intake owns 0033 and this change is reserved for linear 0034 after integration.

Next boundary after this hidden retry: authorized project/setup-fault disposition and correction, followed by 04E3 production registration/readiness and 02I public intake. No setup recovery or complete first journey is claimed by this record.
