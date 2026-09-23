# AUTH-OUTBOX-02 — Authorized shared delivery and retained phase decisions

- Initiative: `WS-AUTH-001`
- Durable disposition: `Planned`
- Intended merge outcome: Activate only shared dispatcher mechanics through existing AUTH/PREP, bind every retained phase to real authorization evidence, and compose the existing delivery owner in Celery without feature-handler authority.

## Intent

Committed background requests need a provisioned, revocable dispatcher before
assignment invalidation and later post-submit routing can use shared delivery.
Delivery authority must never authorize the product effect requested by an event.

## Current behavior

Merged CON-02B supplies claim/invoke/finalize/recover and committed observation in
`backend/app/modules/outbox/`. AUTH-OUTBOX-01 supplies exact phase facts, digest,
nominal prepared handle and planned dispatcher action. No live authority adapter,
phase decision references or production worker exists. The existing AUTH kernel,
fixed-service context resolver and PREP own authority locks, root-transaction
binding, single consumption and audit emission. Reuse those owners.

## Bounded change

### Allowed

- AUTH domain resource, catalogue activation, shared kernel/PREP integration,
  fixed-service adapter and exact public outbox authority contract wording.
- OUTBOX attempt decision references, existing writer receipt consumption,
  exact owner checks, bounded candidate discovery and delivery composition.
- One forward migration after 0027: audit vocabulary and immutable exact
  phase decision matching/FKs, schema fingerprint and affected migration proof.
- `app/adapters/auth/`, `app/adapters/outbox/`, `app/workers/outbox.py` and existing
  Celery registration: explicit empty production handler registry until feature
  owners install separately authorized handlers; no runtime plugin discovery.
- Affected tests in AUTH/OUTBOX/audit/worker/migration/catalogue suites and their
  existing lane/ownership metadata; preserve required proof while replacing
  permissive fake-ALLOW database fixtures with real authority evidence.
- Current AUTH/CON/ARCH/POL navigation, canonical specs, operating docs and
  capability roadmap reflecting the intended merged boundary.

### Not allowed

No feature handlers, TASK invalidation, checker execution, acceptance, fulfillment,
public dispatcher routes, service auto-provisioning, broad grants, new general
scheduler, alternate dispatcher, backward-compatibility path, retained-data
mutation/deletion, baseline migration rewrite, weakened CI or private guide data.
Do not convert existing guide workers into outbox consumers in this change.

## Design and decisions

1. Activate the existing exact `outbox.dispatch` action only for the existing
   fixed `workstream.outbox.dispatcher` identity. Resolve provisioning at the
   operation boundary, never at app import/startup. Humans and other fixed
   services remain denied; dispatcher authority grants no feature action.
2. Adapt the existing nominal port to canonical PREP. Prepare locks the fixed
   service authority before OUTBOX locks event then attempt; consume binds every
   fact and phase to the same session/root transaction and exact prepared input.
   Use one dedicated AUTH `OutboxDispatchResourceContext`; its digest is the
   existing `outbox_dispatch_resource_digest`, never the generic resource hash.
   PREP input contains that digest, and the wrapper revalidates frozen facts.
   Add explicit OUTBOX branches to the existing PREP scope/consumption seams;
   do not classify dispatch as project setup or artifact materialization.
   No handle crosses a commit, handler call or worker wait. Keep database wall
   clock lease checks after lock waits. Do not broaden setup-service semantics
   merely to admit the unrelated dispatcher.
3. OUTBOX remains the authoritative owner of event eligibility and committed
   generation. Recompose exact immutable facts from locked rows before consuming
   authority; no AUTH private import of OUTBOX persistence. Claim binds proposed
   generation; invocation binds retained claim; finalization binds canonical
   outcome digest, including recovery after expiry and historical receipt replay.
4. Store real claim/invoke/finalize decision event IDs in retained attempts.
   Forward SQL guards validate immutable phase selectors, fixed actor/link,
   project/event, action/permission, allowed outcome and exact public resource
   digest. Revalidation remains a PREP property, not a fictional audit field.
   The audit actor identifies the uniquely provisioned dispatcher profile and
   its unique one-to-one identity link. For newly attached decisions require
   both current statuses active through a nonlocking SQL check; normal owner
   writes already hold profile then link locks before event then attempt. Do
   not acquire reverse-order authority locks in OUTBOX triggers. Historical
   references validate immutable identity/evidence without requiring the actor
   to remain active forever. Nullable invoke decision means invocation never began; a
   completed receipt cannot invent invocation evidence. Historical replay retains
   original references while requiring fresh current authority. Claimed stage
   requires claim decision only; invoked requires claim and invoke; completed
   requires claim and finalize and an invoke decision iff invoked_at is set.
   Once set, each decision reference is immutable and independently FK-bound.
5. Migration refuses existing attempts lacking provable phase authority before
   schema mutation. Preserve pending and unattempted-cancelled rows and all audit
   history. Never synthesize decisions for development data.
6. Add one owner candidate page ordered by immutable event UUID, filtered to
   due supported pending/retryable events OR expired claimed events. Use a
   limit-plus-one page (100, hard maximum 500) and exact next_after UUID; no
   payload/receipt/claim facts leave the selector page. One periodic Celery scan
   publishes selector-only delivery tasks after closing its SQL read, then
   continues the keyset. Failed publication remains eligible for the next scan;
   do not let one failed publication strand later pages. Candidate eligibility
   uses one statement timestamp and a parenthesized predicate union. UUIDs that
   become eligible behind a cursor wait only until the next periodic scan.
7. One `deliver_event` task accepts only event/project UUIDs, validates the real
   Celery request UUID for claim owner, and calls one owner
   `OutboxDelivery.deliver(event_id, project_id, owner)` operation that uses
   existing recover then claim/invoke as eligible. The worker does not duplicate
   owner lifecycle predicates. Duplicate delivery neither repeats an invocation
   nor rewrites a completed receipt. The periodic scan also supplies process-loss
   recovery; no second recovery queue or dispatcher is needed. Infrastructure
   task retries are bounded to three with existing 30-second exponential delay;
   they repeat owner admission, never assume a handler is safe to call twice.
   Unknown invocation remains terminal. Empty production registry claims zero
   unsupported pending events, but expired retained claims remain recoverable
   after a handler is removed. Tests inject a registered async handler only at
   the explicit composition seam and exercise actual worker, owner and AUTH.

This L1 change crosses AUTH/OUTBOX/audit schema/composition as one inseparable
activation boundary: an evaluator without mandatory decision custody would allow
unaudited delivery; mandatory custody without its writer would prevent delivery.
Keep helpers small and owner-specific. Expected size exceeds the 500-line
advisory once database and race proof are included; no unrelated cleanup belongs
in that exception.

## Acceptance criteria

- [ ] Exact provisioned active dispatcher can claim, invoke and finalize with
  three real, independently bound audit decisions; no human/other service can.
- [ ] Missing, suspended/deactivated or revoked service denies without startup
  failure or mutation. Revocation between phases prevents the next phase.
- [ ] Prepared handles reject fact/phase substitution, reuse, session/root
  replacement and post-close use; lock order is identical across all phases.
- [ ] Wrong project/event/generation/digest/owner/lease and forged decision IDs
  reject at the proper boundary with valid surrounding fields and controls.
- [ ] SQL independently rejects omitted/wrong-phase/foreign/non-ALLOW decision
  references and preserves original custody; rollback includes staged audit.
- [ ] Historical/concurrent finalization replay preserves original immutable
  receipts while live authority is rechecked. Expired invoked work remains
  unknown; never-invoked expiry preserves the existing bounded safe retry.
- [ ] Forward migration preserves valid unattempted rows and refuses retained
  attempts without fictional audit backfill or deletion.
- [ ] Actual worker functions use the canonical operation, survive duplicate
  broker delivery, and recover publication/process failure with bounded scans;
  no installed production feature handler or feature action is implied.
- [ ] Existing delivery/append/custody tests retain their required behavioral
  assertions under real authorization. Exact CI selection has no skips and
  affected code remains at least 90 percent covered.

## Risk and review routing

- Risk class: `L1` — bounded service authority, immutable audit custody, SQL and workers.
- Required reviewers: security, architecture/reuse, QA/test delta/product ops,
  CI integrity and documentation; plan review precedes implementation.
- Human review focus: phase-specific real authority; revocation/locks; migration
  refusal without loss; no transitive feature authority or fabricated audit.

## Evidence

Planned tests must exercise real PostgreSQL and canonical AUTH rather than
injecting arbitrary ALLOW UUIDs. For each denial isolate the changed field from a
valid baseline. Mutation probes remove only the relevant prepared/SQL guard so
the named assertion proves that boundary, not an earlier malformed fixture.

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing owner feasibility | Inspect AUTH PREP/kernel, OUTBOX writers and actual Celery composition | Source inspection | Plan review and runtime proof pending |
| Exact phase custody | New AUTH/outbox PostgreSQL integration, independent SQL substitution and rollback tests | Planned | No live activation claim yet |
| Prepared and revocation safety | Real actor/link revocation and concurrent phase tests with distinct events | Planned | Must prove serialization, not just one mocked task |
| Migration preservation | Isolated 0027 to new-head upgrade with retained row snapshots and refusal control | Planned | No retained data repair authorized |
| Worker path | Actual worker functions plus real database recovery and broker-envelope rejection | Planned | Do not claim live broker transport without running it |
| Gate integrity | Existing lint/boundary/ownership, lane selection, docs/links and hosted full CI | Planned | Exact final head required |

## Review findings

Current-source reconciliation requires real phase decision references and their
matching SQL guards to activate with the evaluator. CON-02B fake-ALLOW fixtures
cannot remain evidence of live authorized custody. Plan review made the dedicated exact-digest resource and PREP branches explicit,
kept revalidation in PREP rather than inventing an audit field, and prohibited
reverse-order SQL authority locks. The canonical actor/link uniqueness constraints
supply identity matching without duplicating identity selectors in the public
phase contract. Worker discovery/continuation and test-only handler composition
are explicit. Existing claim/finalization race barriers must run before real
PREP acquires the service locks; post-consumption lease delay stays separate.
Do not replace real authority with a fake merely to preserve a race schedule.

## Reconciliation

- Current-source reconciliation: main `855aa646` includes merged CON-02B and its
  async-only handlers, conservative elapsed deadline and unattempted-only
  cancellation. Preserve these behaviors.
- Next usable boundary: assignment invalidation and its feature-specific
  authority, then ARCH-03C; post-submit handler/authority/integration remain
  their own downstream chunks.
- Remaining risks: unknown external effects require explicit reconciliation;
  production feature handlers and live broker proof are not inferred from shared
  mechanics or unit worker execution.

### Named implementation proof inventory

These are planned additions/strengthenings, not executed evidence:

- `test_real_dispatcher_records_exact_phase_decisions`: real provisioned actor,
  three distinct phase decisions, canonical digest and immutable custody.
- `test_dispatcher_lifecycle_and_matrix_denials`: missing/suspended/deactivated/
  revoked, human and foreign-service controls; dispatcher denied ART/TASK/CHECKER.
- `test_prepared_dispatch_binds_root_session_and_all_facts`: independent phase,
  event/project/generation/owner/lease/payload/outcome changes, reuse/close/root
  replacement, each paired with valid original input.
- `test_phase_decision_sql_substitutions`: valid phase rows plus exactly one
  omitted, swapped, foreign, denied or mismatched decision; verify rollback and
  preserved rows. Current-revoked new-reference control is distinct from valid
  historical references after revocation. No claimed nonexistent revalidated
  audit field or arbitrary fake-ALLOW row.
- Strengthen existing historical/concurrent finalization replay tests to assert
  original decision references unchanged and fresh real FINALIZE audit committed;
  revoked replay yields no result or committed ALLOW. Keep pre-PREP barriers for
  claim race, stale eligible generation and concurrent finalization.
- `test_dispatch_activation_preserves_unattempted_rows` and
  `test_dispatch_activation_refuses_unauthorized_attempts`: actual predecessor
  claimed/invoked/completed rows and exact surrounding custody before refusal;
  preserve pending/cancelled snapshots, repeated upgrade and no deletion.
- `test_worker_duplicate_delivery_and_expired_recovery`: actual task function,
  real owner/AUTH and explicit test-only async registry. Distinct uninvoked
  versus invoked expiry controls; one handler call after duplicate transport.
- `test_worker_scan_continuation_and_publication_failure`: stable bounded
  selector pages, failed publication retained, later pages progress, SQL closed
  before broker work; malformed selectors/task UUID reject before database work.
- `test_empty_production_registry_has_no_feature_authority`: no claims on
  unsupported events and no registered product effect; structure proof limits
  live composition to the canonical owner/worker roots.
