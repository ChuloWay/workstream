# Review policy human-review requirement

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Existing immutable ReviewPolicy versions persist and expose strict `human_review_required`, default true, without activating automated acceptance or changing locked history.

## Intent

Implement the [merged product-builder handoff](pre-review-plan-reconciliation.md#product-builder-handoff-implement-the-setting-next).

## Current behavior

PROJECTS owns immutable policy creation/supersession through
`policy_mutation_service.py`; exact AUTH actions and selectors already govern it.
`policy_lineage.py` hashes review semantics in the v1 domain. `ProjectService`
validates those semantics before guide activation. Policies and downstream
selectors are immutable; no automated acceptance participant exists.

## Bounded change

### Allowed

- PROJECTS `models.py`, `schemas.py`, `policy_lineage.py`,
  `policy_mutation_service.py`, and activation/read projection in `service.py`.
- Add migration `backend/alembic/versions/0011_review_policy_human_review.py`.
- Focused policy/activation/migration tests and necessary existing fixture updates;
  register new modules in the existing lane catalogue and refresh exact structural
  debt fingerprints when changed owners require it. Preserve all gates.
- This record, current policy specifications/roadmap/templates and the adopted
  CP07/AUTH-12H activation contracts and REV overview where needed to state delivered configuration
  versus deferred automated execution. No protected historical archive edits.

### Not allowed

- New policy entities, permissions, checker execution, synthetic review/lease,
  automated acceptance/CON activation, adjudication or frontend changes.
- Rewriting historical digests, completing incomplete historical policies,
  changing locked attempts through a current-policy lookup, weakening checks.

## Design and decisions

Add non-null `human_review_required` and persisted `semantics_format` to
ReviewPolicy. Migration backfills true and `v1` with column defaults (no row
updates or digest rewrites); subsequent database/ORM format defaults to `v2`. Drop the temporary boolean
server default after backfill; API/ORM creation defaults true, while direct SQL
must supply a non-null boolean. Downgrade refuses any v2 policy history; a
legacy-only downgrade may drop the new columns without losing semantics.
A constraint restricts formats and requires v1 to have true. Existing immutable
row triggers protect both columns. v1 hashing excludes the setting and retains
its exact domain/bytes; v2 hashes the explicit strict boolean in a v2 domain.
No timestamp, boolean-value inference, trial hashing or completeness backfill.

Input defaults true but retains Pydantic field-presence information. Creation
uses true when omitted. Supersession inherits the exact predecessor value on
omission before preparing the final digest; explicit boolean overrides only the
new version. Request identity hashes all existing defaulted semantics and excludes only
omitted `human_review_required`, preserving legacy request bytes. Committed
replay is checked before any guide, current-selector or predecessor lookup.
For a new supersession, load the exact If-Match predecessor ID and verify
project, guide version, generation and hash before inheriting its boolean;
then compute the v2 digest. Final PREP/consume binds the
resolved digest and existing selector; the locked selector is rechecked under lock before PREP consume or
writing. Reads include the setting and persisted format; legacy stored replay
responses interpret the absent setting as true/v1 without changing hashes.

The current activation validator validates exact format-aware semantics and
explicitly rejects false with an unavailable automated-acceptance error. Future
CP07/AUTH-12H must preserve that same guard until REV/CON execution exists.

## Acceptance criteria

- Creation/read round-trip defaults true; true/false are accepted, strings,
  numbers and null rejected; omission is distinguishable from explicit true.
- Omitted supersession preserves false; explicit true/false affects new version
  only; replay stays exact after later selector changes; unauthorized and
  cross-project mutations retain existing denial and no writes.
- v1 complete and incomplete history keeps original hashes and selectors; v1
  cannot represent false. v2 true/false differ and bind the setting. Invalid
  format, missing v2 boolean and altered digests fail closed.
- PostgreSQL upgrade preserves old hashes and locks, persists both formats,
  enforces constraints and immutable history, and does not invent completeness.
- A valid true activation control reaches current activation; changing only
  the mode to validly hashed false yields the specific unsupported-path error.
  Future owner contracts explicitly retain the guard without new execution.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, security, product_ops, documentation, QA,
  test_delta; CI integrity only if gate/registration owners change.
- Human review focus: safe default, omission/replay semantics, explicit hash
  versioning, preserved locked history and unavailable automated activation.
- Plan review: focused architecture/security feasibility before implementation.

## Evidence

Use focused local tests and guard-removal probes; hosted CI owns PostgreSQL,
full suite and coverage. New materially changed behavior must achieve 90%
coverage; existing global floors remain unchanged. Run lint, structural checks,
Commitrail validation, Markdown links and stale wording scans. No local exports
are currently present. Exact results belong in the PR trust summary.

## Review findings

Plan review clarified exact omission/replay ordering and non-destructive
migration rollback. The existing adopted WS-XINT-003-02B response-recovery
contract remains unchanged; this setting adds no authority to replay or mutate.
Generic historical reauthorization wording does not replace that exact contract.

## Reconciliation

- Current-source reconciliation: main `3bb3a23d` includes AUTH-12B2 and merged
  planning handoff PR #385; no open PR overlaps were found at discovery.
- Next usable boundary: existing POL/ARCH/TASK/REV/CON owner plans; this change
  starts no subsequent chunk and enables no automated acceptance runtime.
- Remaining risks: automated activation remains unavailable pending its exact
  acceptance/contribution authority and atomicity proofs.
