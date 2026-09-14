# WS-POL-003-06B — Public post-submission policy review

- Initiative: `WS-POL-003`
- Durable disposition: `Complete`
- Intended merge outcome: Pre-submission approval automatically schedules deterministic post-submission policy derivation; project managers can discover, inspect, separately approve, or request correction of that policy through public APIs.

## Intent

Complete the policy-review part of unified guide setup without another inference
step. The manager approves the pre-submission proposal first, then inspects and
separately approves its derived post-submission policy. Both correction origins
use the existing unified correction and explicit manual dispatch operation.

## Starting behavior

At the start of this change, POL-06A owned immutable derivation, approval and correction in
`backend/app/modules/projects/post_policy/`. AUTH-12G supplied the exact fixed
service and project-manager adapters. Neither was connected to a public route or
automatic continuation. `guide_proposals.py` exposes the upstream approval and
canonical correction dispatch; its authorized proposal read does not yet identify
the downstream policy. These existing operations and receipts remain the owners.

## Bounded change

### Allowed

- `backend/app/api/routes/guide_proposals.py`, a focused post-policy router,
  corresponding `api/deps/` composition and shared HTTP guards, and `api/router.py`.
- `backend/app/modules/projects/api/post_policy.py`,
  `api/guide_proposal_package.py`, `guide_compilation/proposal_repository.py`, and
  `post_policy/` for transport values, discovery and durable delivery selection.
- `backend/app/adapters/auth/__init__.py` and `adapters/projects/` for explicit
  composition of existing ports; no new authorization policy or adapter semantics.
- A focused `backend/app/workers/post_policy.py`, Celery task registration and
  beat scheduling, and PROJECTS queue publication using existing worker utilities.
- Focused public/worker/PostgreSQL tests and affected fixtures; exact test-lane
  registration and required structural inventories for those files.
- Current README, API/checker/operating documentation, roadmap, POL/AUTH navigation,
  adopted chunk contract and this change record.

### Not allowed

New inference, document access, checker execution, caller-selected checks,
authorization permissions, migrations, policy compiler replacements, guide
activation, task/contribution changes, a second correction/dispatch operation,
or reopening finalized setup. No compatibility route or old/new implementation.

## Design and decisions

1. Expose project-manager GET, approval and correction beneath the exact
   project/guide/compilation/post-submission-policy identity. Reuse nominal
   operation ports, fresh AUTH preparation and existing root transaction owners.
   Share the UUID idempotency-header guard, including duplicate rejection before
   identity/database access. Service and unauthorized human HTTP access conceal
   resources. Path and body targets must agree.
2. After upstream approval commits, enqueue derivation under the fixed
   `workstream.project.setup` service. Keep its immutable approval receipt
   unchanged. Derivation gets a separate fresh root transaction and consumes its
   own authority before product writes. A public GET never derives a policy.
3. The existing committed upstream approval is the durable intent. The existing
   unique derivation operation is its completion marker. A periodic recovery
   scan pages bounded batches of approval IDs missing a derivation; it does not
   add a workflow table. Keyset traversal prevents a bad early candidate from
   starving later candidates. Selection excludes superseded policies and stale
   setup generations; execution still validates all current upstream/catalogue
   custody and live authority. Publication failures leave the intent recoverable.
   Duplicate delivery uses the existing deterministic operation ID and replay.
4. Workers receive only the immutable approval operation ID and use its stored
   selection/digest; no caller policy body, actor choice or runtime factory.
   Broker task IDs derive from that approval ID. A mismatched delivery is denied.
   Transient infrastructure failures retry with bounded backoff; stale/denied
   deliveries do not mutate policy. Scans and workers expose bounded outcomes.
5. Add the exact downstream policy ID to the existing authorized proposal read.
   This supports discovery after a lost response. The full post-policy read
   returns its existing correction receipt; another currently authorized manager
   can discover and dispatch the pending successor after the creator is revoked.
   Creating a correction performs no inference; the later explicit dispatch
   retains its existing runtime behavior.

Synchronous derivation inside the upstream approval transaction would prepare a
second authority after product locks. A new state table or separate correction
subsystem would duplicate durable owners. Neither is needed.

## Acceptance criteria

- [x] Public approval commits upstream custody and schedules the exact derivation;
  broker failure or process interruption can be recovered from that custody.
- [x] Real PostgreSQL delivery/redelivery creates one compiled policy and one
  derivation receipt with matching hashes; no extra provider/document/checker call.
- [x] Project managers discover the policy from an existing public read and
  inspect its complete canonical body, lifecycle and upstream lineage.
- [x] Approval remains a separate explicit mutation. Exact project scope, current
  role grants, revocation, stale/mixed targets and replay retain existing guards.
- [x] Lost correction response plus creator revocation is recoverable entirely
  through public reads and the existing manual dispatch API by another manager.
- [x] Both new mutation routes reject missing/duplicate/malformed keys before
  identity or database work; mismatched path/body identities are concealed.
- [x] Failed authority, invalid/stale custody and transactional failures leave no
  partial policy/operation/audit state; shared existing guard tests remain intact.
- [x] Public OpenAPI and current documentation agree; POL-07 remains the next
  single CHECKER service-port boundary. No submitted-work evaluation or guide activation is claimed.

## Risk and review routing

- Risk class: `L1` (authorization, workflow and policy exposure).
- Required reviewers: plan review before implementation; architecture/reuse,
  security, QA/test delta, documentation/product operations, CI integrity for
  changed lane registration and proof custody.
- Human review focus: separate approvals, automatic recovery, discoverable manual
  correction, and no activation or evaluator scope expansion.

## Evidence

The public proof lives in `tests/projects/post_policy/test_public_api.py`:
`test_public_policy_body_separate_approval_replay_and_revocation` checks complete
canonical body/hash equality and current authority; the commit-failure test
stages real writes and proves rollback for read, approval and correction.
`test_public_recovery.py` proves failed-publication recovery, public-only manager
handoff, stale denial, service revocation, post-write rollback, keyset progression
and independent concurrent worker delivery. `test_delivery_worker.py` isolates
transport admission, retry classification, pagination and cleanup. Existing
POL-06A/AUTH-12G database constraints, compiler and authorization tests remain
required; none protect an obsolete compatibility implementation.


| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing owners support this boundary | Inspected post-policy service/repository/API, proposal routes/custody, AUTH composition and Celery registration on main `a81df4d6` | Contract feasible | Public/worker execution proof remains to be implemented |
| Public workflow and authority | `pytest tests/projects/post_policy/test_public_api.py tests/projects/post_policy/test_public_recovery.py` with isolated PostgreSQL | Executed public body, approval/replay/revocation, broker recovery and manager-handoff proofs | Hosted full regression remains the broad check |
| Recovery and zero inference | The public recovery tests plus `pytest tests/projects/post_policy/test_delivery_worker.py` | Actual Celery task functions, real SQL/AUTH and fail-on-call runtime/document/evaluator hooks | Publication transport is controlled; this does not claim a live broker drill |
| Test integrity and coverage | Required hosted seven-lane suite, inventory checks and affected module coverage at least 90% | Pending | No skipped/deselected tests accepted |
| Current documentation | Markdown-link check, stale wording scan and roadmap assessment | Current public boundaries and next dependency reconciled | No local sheet exports present |

## Review findings

Plan review passed with low risks. Recovery uses stable approval-ID keyset pages,
advances past denied candidates and schedules the next bounded page; each new
sweep starts at the beginning. Delivery reloads immutable approval selection and
digest, resolves the provisioned service, rolls back identity reads, then opens
a fresh root transaction. Discovery binds the requested compilation and its own
approval custody, never the guide-wide current approval tip. Focused tests protect each boundary.

## Reconciliation

- Current-source reconciliation: Main `a81df4d6` includes merged POL-06A and
  AUTH-12G, including the corrected proof-map reference. Their operations and
  authorization remain authoritative.
- Next usable boundary: POL-07 single CHECKER service port, followed by its adopted activation
  dependency; CP06 is not part of this change.
- Remaining risks: Asynchronous derivation requires a running worker and beat
  recovery scanner. Live model testing is unrelated to this deterministic chunk.
