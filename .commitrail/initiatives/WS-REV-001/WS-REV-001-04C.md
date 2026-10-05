# REV-04C — Hidden shared acceptance and TASK terminal participation

- Initiative: `WS-REV-001`
- Durable disposition: `Planned`
- Intended merge outcome: one hidden REV participant stages exact FinalAcceptance, TASK accepted/completed effects and complete submitter economic facts in a caller-owned transaction; live acceptance remains unavailable.

## Intent

Connect the delivered acceptance storage, lifecycle fence and CON-07 participant.
Both eventual acceptance triggers must use this same transactional core. Keep
actual AUTH/source receipt custody and shared audit/outbox composition at the
already-planned activation boundary; this core is not the complete authorized
`SharedFinalAcceptanceOperation` and introduces no alternative business path.

## Current behavior

Main `0ba68eaa` includes merged CON-07. REV owns immutable FinalAcceptance
storage and the disabled generation-zero root-transaction fence. TASK exposes
only `TaskAcceptedEffectsPort`; it has no terminal participant. CON creates or
replays contributions and complete frozen awards, but currently derives its own
new/replay disposition. An enclosing acceptance replay could consequently fill
in a missing contribution rather than reject partial prior effects.

The current source schemas predate required receipt hardening. Neither
`review.decision` nor `task.post_submit.route` can issue a genuine allow. False
guide activation remains unavailable. Existing true-policy stored Review
fixtures are valid storage controls, not authority or a live human workflow.

## Bounded change

### Allowed

- `backend/app/modules/reviews/api/{acceptance,__init__}.py` and `reviews/acceptance/{__init__,schemas,repository,participant}.py`: closed values, exact source identity recovery and one hidden flush-only shared participant.
- `backend/app/modules/tasks/api/accepted_effects.py`, `tasks/accepted_effects.py` and narrowly necessary owner repository methods: exact TASK lineage/prestate locking, terminal mutation and read-only replay.
- `backend/app/modules/contributions/api/participation.py` and `contributions/records/{participant,repository}.py`: explicit enclosing acceptance disposition; reject missing replay records before insertion, without a compatibility default.
- Focused tests in `backend/tests/reviews/acceptance/`, `tests/tasks/accepted_effects/`, `tests/contributions/participation/` and affected canonical source fixtures; retain distinct existing guard proof.
- Exact ownership/lane registrations in `.ci/behavior-ownership/partition.v1.json`, `backend/scripts/{behavior_ownership,test_lane_catalogue}.py`, and their focused expectation tests; no changed gates, caps or partition algorithm.
- This record, current REV/CON/ARCH/AUTH/POL navigation, `.commitrail/INDEX.md`, README and affected canonical lifecycle, contribution, authorization, artifact, data-model, glossary and roadmap claims. Reconcile the linked current ARCH-04E parent contract in the same PR. Local roadmap exports only if present.

### Not allowed

- Production composition/registration, routes, handlers, workers, AUTH activation or fabricated allow/receipt, false guide activation, source publication/current pointer, live human decisions, reviewer contributions, fulfillment roots/delivery, payment or reputation.
- REV imports of private TASK/CON/CHECKERS owners, TASK imports of REV, provider/ART I/O, an additional source table/acceptance engine, compatibility aliases, no-op production participants, or silently repairing retained partial effects.
- No change to the deferred contributor lease/skip scope.

## Design and decisions

Acquire the existing canonical REV fence first, in the caller's root transaction;
managed and raw SQL savepoints remain rejected. Owner-local TASK locking must
precede acceptance/source writes that can take foreign-key locks. The TASK
participant validates the exact project, task, assignment, latest Submission,
contributor, frozen contribution policy and artifact identity. Its terminal
mutation changes only Task status to accepted and the exact assignment status
to completed; no generic user-command transition is enabled.

REV stores or recovers one exact source-bound acceptance. UUIDv7 allocation and
exclusive source replay use existing owner storage, not IDs derived from a
request token or a new reservation store. Caller-preallocated identity remains
available for the future exact AUTH consequence. The request carries a caller-preallocated UUIDv7 acceptance identity; committed
replay must supply that stored identity. A future PREP identity resolver remains
outside this participant. No extra reservation store is introduced.

TASK first locks and validates Task -> Assignment -> latest Submission and
reports the observed new or terminal replay state. REV then inserts only for
new work or selects and exactly compares only for replay, using every unique
acceptance axis (ID, task, submission, exclusive source) to reject conflicting
identity. A new insertion that loses cannot become replay. TASK applies effects
only after this decision. REV validates the human source digest against the
stored Review, and automated source facts through the TASK public contract;
TASK owns the content ID, not artifact bytes.

The strict shared request contains FinalAcceptanceInput, TaskAcceptedEffectsRequest,
expected generation and correlation. Common IDs must match; human uses
review_pending, automated uses evaluation_pending. REV reloads the actual Review
and compares source, policy, assignment, version, reviewer and artifact hash.
The TASK public accepted-effects port also exposes require_routing_source(request,
manifest_id): its owner reads the exact immutable stored routing manifest and
compares project/task/submission/version/assignment/contributor/frozen policy,
content hash and false human-review setting to the already-locked TASK facts.
It never treats caller detached values as stored proof. Exact aggregate AUTH
commitments/currentness remain mandatory at activation. Unpaid participation
retains no correlation and makes no replay-correlation claim.

The acceptance owner derives `new|replay` once. TASK and CON receive it as
operation provenance, not caller authority or a new business policy. New work
requires its valid prestate and absent effects. Replay requires already-complete,
exact TASK/CON/award facts and returns original IDs without mutation. Any partial
prior set conflicts; catching the exception must not leave newly repaired rows.
The existing compensation complete-set owner remains canonical.

The participant returns exact immutable acceptance/TASK/contribution/award facts.
It neither commits nor authorizes. Future complete operation composition evolves this same participant input and
schema to require the verified AUTH event, without a compatibility default, and
adds mandatory shared audit/outbox staging;
it may not replace it with a second sequence or a no-op participant. Future TASK
routing consumes a TASK-owned structural interface supplied by composition so
REV -> TASK/CON remains acyclic; no reverse TASK -> REV dependency is introduced.

No migration is included. This participant guarantees its own call sequence in
a caller-owned transaction, not database enforcement of every direct-SQL
complete effect set. Mandatory source AUTH receipt hardening and deferred
FinalAcceptance/TASK/CON complete-set guards belong together at 04E2-B, before
activation; retained pre-authority rows must be refused, not repaired or deleted.
CHECKERS can currently reserve a later evaluation without the TASK lock. The
04E1B-B/activation work must introduce the existing-direction consumer seam
that locks TASK before CHECKERS and rejects terminal tasks, and the source
handler must revalidate currentness under those locks. This chunk does not
claim acceptance-versus-evaluation-supersession safety or live acceptance.
Before activation, prove both race orders: a successor generation first makes
acceptance stale; acceptance first prevents a successor reservation after TASK
locking. Never enable the generic ALLOWED_TASK_TRANSITIONS accepted transition.

## Acceptance criteria

- Valid human-source storage controls stage one exact acceptance, accepted task,
  completed assignment, submitter contribution and zero/one/two frozen awards.
- Replay preserves every stored identity and scalar, performs no repair, and
  rejects independent valid foreign source/owner substitutions and changed
  correlation where retained.
- Named partial cases: FinalAcceptance only with pending TASK; terminal TASK and
  assignment without acceptance; accepted/active and pending/completed mixed
  states; exact acceptance plus terminal TASK without CON; exact contribution
  with partial awards staged before the existing deferred completeness check.
  Each rejects before any missing effect is inserted; catch and commit where the
  existing database permits the partial fixture, otherwise inspect then roll back. A guard-removal probe reaches the intended replay
  assertion rather than a prior invalid-source guard.
- Late real SQL failure and caller rollback discard every newly staged effect.
  No participant commits, creates reviewer work, or accesses artifact bytes.
- Independent PostgreSQL sessions prove exact-source convergence, conflicting
  source rejection, and the required lock retention/order. Missing root and
  both savepoint forms fail before product writes.
- TASK owner checks reject foreign projects before foreign row locks and reject
  stale Submission/assignment/policy/content facts. Terminal and mixed partial
  states cannot be treated as a new acceptance.
- False-source metadata and true-policy rejection remain covered without
  fabricating positive false activation. Automated positive authority/currentness
  and whole audit/outbox atomicity remain explicit activation obligations.
- A named negative-structure test scans production imports, constructions,
  routes, workers and registrations to prove the hidden participant is unreachable;
  both review.decision and task.post_submit.route remain planned. No no-op
  authority adapter or fallback is permitted.
- Replace the direct-CON concurrent insert-or-replay proof with shared-owner
  concurrent commit/rollback winner proof, retaining stored winner-ID assertions.
- Full hosted suite completes with zero skips/deselections; no required proof,
  ownership guard or CI limit is weakened.

## Risk and review routing

- Risk class: L1 — bounded terminal workflow, economic facts and transaction custody.
- Required reviews: architecture/reuse, security, QA/test-delta, CI integrity for registration changes, documentation/product-operations.
- Human focus: hidden mechanical composition is not live acceptance authority; complete source/evidence custody and automated positive runtime proof remain required before activation.

## Evidence

Plan review must settle source identity recovery, exact lock order, replay
provenance, necessary database complete-set safeguards and fixture reachability
before implementation. Focused real PostgreSQL tests exercise the owner ports
and caller transaction; pure tests cover strict closed values. Run Ruff,
module/authority/ownership checks, stale wording, links, Commitrail and the full
unchanged hosted completeness gate. Exact target/results belong in the PR.

## Review findings

Discovery identified a partial-replay repair gap in the enclosing use of CON-07.
Explicit acceptance-derived new/replay provenance and no-insert replay address
that requirement without adding a second contribution implementation. The
existing REV queue/lease files are active owners and are not obsolete scaffolding.

## Reconciliation

- Current source: CON-07 is merged; preserve current MCP/CLI and observability work.
- Next usable boundary: hidden routing handlers, complete authority/evidence composition and scoped lifecycle activation, then live integration and remediation before public intake/false activation.
- Remaining risks: exact real AUTH/source receipts, complete shared audit/outbox custody, fulfillment-root ordinals, both production trigger paths and human runtime remain outside this hidden participant.
