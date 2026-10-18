# AWS activation failure and timing corrections

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Bind proof clients to the configured AWS region, reserve and enforce proof-sequence time, and keep configuration outages recoverable.

## Intent

Finish three source defects remaining in #582 before the first real AWS-backed
contribution drill. A merged configuration path is not proof of a deployed
provider. This change repairs the existing ART path, without provisioning AWS
or expanding the product workflow.

## Pre-change behavior

Main `51b868071` includes #592 and #595, with one migration head
`0053_project_reads`. The proof-only adapter constructs IAM and Access Analyzer
clients without the configured region. Native AWS Settings subtract refresh and
clock margins from activation validity, but do not reserve time for the proof
sequence. The ART observation paths catch lazy `ArtifactConfigurationError`
under generic storage errors and can persist conflict or integrity outcomes for
a recoverable configuration outage.

The older local repair branch is unmerged evidence, not an implementation base.
Its backdated `activated_at` counterexample also demonstrates why the new
database duration check must use PostgreSQL time.

## Bounded change

### Allowed

- `backend/app/adapters/artifacts/aws_live_proof.py`: region binding only.
- `backend/app/core/config.py`: one fixed v0.1 proof-sequence allowance and the
  existing activation-window validation.
- `backend/app/modules/artifacts/provider_activation.py` and `service.py`:
  enforce sequence duration in the existing coordinator and classify known
  configuration failures through existing unavailable outcomes.
- `backend/alembic/versions/0054_artifact_proof_timing.py`, `backend/alembic/env.py`:
  replace the existing activation insert guard, admit the immediate predecessor,
  and preserve downgrade refusal. Historical migrations stay unchanged.
- `backend/tests/test_config.py`, `test_aws_artifact_live_proof.py`,
  `test_artifact_admission.py`, `test_artifact_provider_activation_postgresql.py`,
  `test_artifact_provider_activation_terminal_postgresql.py`, `test_alembic.py`,
  and `conftest.py`:
  discriminating regression cases, valid expiry fixtures, upgrade/downgrade
  proof and the combined head fingerprint. Update the existing lane catalogue
  only if adding a test file becomes necessary; prefer the current modules.
- `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`:
  relocate the two touched unavailability tests from the frozen oversized
  admission module into the existing terminal-custody module, preserving every
  original assertion. Refresh exact inventory without changing guard limits.
- `docs/spec_artifact_storage_service.md`, `docs/operations_artifact_storage.md`,
  `docs/roadmap_status.md` and this record: affected guarantees and remaining
  deployment proof, with local roadmap exports only if present.

### Not allowed

No new scheduler, proof service, provider factory, public route, authority,
credential transport or compatibility path. No changes to retained data or
past migrations, no weakening UNKNOWN/terminal custody, no blanket storage-error
retry, no live AWS/identity calls, deployment or spending. No CI timeout,
selection, completeness or assertion weakening. Other agents own checker
negative proofs and uncertain-delivery reconciliation; CLI is separately owned.

## Design and decisions

1. Supply the existing configured S3 region to IAM and Access Analyzer clients
   inside the AWS proof adapter.
2. Reserve a fixed 120 seconds for runtime-first proof through coordination.
   The existing validity inequality becomes maximum operation/read duration +
   persistence + clock safety + proof allowance + refresh interval <= validity.
   Enforce elapsed time from the runtime probe start to database time in ART
   and in the existing PostgreSQL activation guard. Do not trust an inserted
   `activated_at` to establish the current time.
3. Migration 0054 follows 0053 and replaces that function in place, preserving
   the existing search path, qualified tables, trigger and lineage predicates.
   Existing immutable probe/activation rows are not rewritten. Existing
   remaining-validity gates still decide whether any activation may admit I/O.
4. At outer put observation, its nested canonical-read fallback, and verification,
   catch `ArtifactProviderLiveProofRequiredError` first (it subclasses
   `ArtifactConfigurationError`), then the known configuration exception, then
   generic storage errors. Use existing unavailable persistence. Expired live
   proof retains its distinct unknown-effect behavior; actual mismatch/conflict
   stays distinct. Iterator tests raise during actual `open` advancement.
5. Document that the arithmetic assumes successive proof starts within 300
   seconds and successful coordination within the allowance. At maximum bounds
   equality leaves no scheduling/commit latency slack: operators must start
   earlier or use smaller operation limits for margin. No continuous-availability
   or scheduling guarantee is invented; missed cadence fails closed. The hosted
   drill must measure cadence, sequence duration and commit latency.
6. The terminal-expiry fixture first commits a valid ordered group/activation
   through production owners. In a separate isolated-test transaction, disable
   only the named probe/activation immutable triggers, shift every linked probe
   start/completion/expiry and activation activated/expiry timestamp equally,
   then restore triggers in `finally`. Assert the original timing equalities and
   that direct mutation is refused again before exercising terminal expiry.
   This simulates an aged, previously valid record; it is not current insertion
   proof, live AWS evidence, or a production time-travel feature.
7. Extend the canonical `test_alembic.py` graph list and immediate-predecessor
   parametrization. Its existing isolated database/schema reset, migration lock,
   separate Alembic invocations and snapshots own 0053 -> 0054 retention proof.
   Add retained probe/activation snapshots and one-revision downgrade refusal
   there rather than introducing another migration harness.

## Acceptance criteria

- [x] Both proof clients receive the configured region without introducing an
  ambient-region fallback.
- [x] A valid maximum-budget configuration passes and a larger budget rejects;
  the fixed allowance cannot be changed by environment input.
- [x] ART and direct SQL reject an otherwise valid overlong group, including a
  backdated activation timestamp; an ordered recent group succeeds. Removing
  the duration predicate makes the intended negative assertion fail.
- [x] A separately invoked 0053 -> 0054 upgrade preserves existing records and
  installs the guard; a one-revision downgrade refuses without altering state.
- [x] Lazy configuration failures during put observation and verification retain
  recoverable facts and no false conflict/integrity receipt. Live-proof expiry,
  genuine missing/mismatched bytes, replay and retained custody remain protected.
- [x] Current docs and roadmap state the repaired source guarantee, conditional
  cadence assumption, and remaining authorized live AWS/hosted proof accurately.

## Risk and review routing

- Risk class: L1 (storage custody, database guard and failure recovery).
- Required reviewers: security; architecture/reuse; QA/test delta; documentation;
  CI integrity for migration fingerprint/test completeness changes.
- Human review focus: authoritative clock, preserved retained facts, exact error
  classification, and source proof versus deployment readiness.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Merged defects | Inspect the main adapter, Settings and ART observation branches | Three defects repaired through existing owners | No deployment is implied |
| Region/configuration | Configuration and proof-adapter tests, including non-default configured region | 260 passed | No live AWS |
| Database clock and migration | PostgreSQL activation/terminal cases plus separate predecessor upgrade, retained-row snapshots, one-step refusal and lazy-stream failure tests | 26 activation/terminal and 8 migration/admission tests passed; owned databases cleaned | Provider observations are controlled; no AWS transport |
| Discriminating timing proof | Remove only the new SQL duration predicate in an isolated database, run the exact regression, then restore the function | Intended `DID NOT RAISE DBAPIError`; cleanup confirmed | Demonstrates this guard, not all database predicates |
| Integration gate | Required hosted Backend and repository checks; exact target and review freshness are recorded in the PR | Mandatory before readiness | No hosted product deployment |

## Review findings

Plan review identified missing canonical migration-test scope, an infeasible
pre-insert expiry fixture, and exception-subclass precedence. The bounded plan
now explicitly extends `test_alembic.py`, ages already-admitted records only in
isolated test custody, and preserves live-proof-specific catches before the
configuration catch at all three observation branches. Source timing enforcement
uses the database clock, not a caller-authored activation timestamp. An earlier
fixture rejection is not terminal-expiry proof.

Implementation review found no product-source blocker. Finalization corrected
the record's stale planned wording and retained the deployment limitations.
Hosted preflight also caught growth in the frozen oversized admission test file;
the two touched tests now live in the existing ART terminal-custody module. All
original assertions remain, structural debt shrinks, and no gate is relaxed.

## Retained test proof

The two complete tests move from `backend/tests/test_artifact_admission.py` to
`backend/tests/test_artifact_provider_activation_terminal_postgresql.py` under
their original names. Neither is split or removed. An AST comparison against
main `51b868071` confirms all 28 original assertions remain; parameterized lazy
configuration failures strengthen the original unavailable/retry cases. The
admission file shrinks, its exact debt inventory is refreshed, and structural
limits and validator scope remain unchanged.

| Original and retained test name | Primary invariant |
|---|---|
| `test_put_observation_unavailable_retries_then_exhausts_without_facts` | Recoverable observation failure exhausts only its retry budget, without false receipts or replicas |
| `test_verification_unavailable_retries_then_exhausts` | Recoverable stream failure preserves retry state and creates no verification receipt |

## Reconciliation

- Current-source reconciliation: current main `51b868071`; 0052 is historical,
  0053 remains its canonical successor, and this repair reserves 0054.
- Next usable boundary: authorized role-separated AWS proof and public custody
  drill under #582/#583/#555 after the source repair; no extra subsystem.
- Remaining risks: live AWS, scheduler cadence, production limits and restore
  evidence remain unproved until the authorized environment drill.
