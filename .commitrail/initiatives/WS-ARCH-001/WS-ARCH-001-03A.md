# WS-ARCH-001-03A — Complete active and frozen guide context

- Initiative: WS-ARCH-001
- Durable disposition: Planned
- Intended merge outcome: the existing PROJECTS internal context port resolves
  the complete approved, activated guide graph for new work or exact frozen work.

## Intent

Give TASK one canonical source for the complete guide-bound policy context.
An active guide supplies a new task lock; an existing task resolves its exact
stored guide/source/pre-policy selectors without adopting a newer guide or CON
publication. This is an internal port, not a new HTTP surface or task writer.

## Current behavior and sequence correction

Main `ad0e6b68` includes CP07 activation and AUTH-12H live manager authority.
`ProjectLockedPolicyContextPort` and `ProjectLockedPolicyRepository` currently
resolve only guide/source/effective/pre-submit facts, without activation,
post-submit, review/revision or contribution-policy custody. ART admission and
pre-submit evidence already consume this port. Some downstream fixtures mark a
guide active by disabling custody triggers instead of executing activation.

The user approved ARCH-03A before CP08 after reviewing these concrete defects:
CP08 prohibited every writer needed to satisfy its required lineage constraints;
03A's CP08 prerequisite was artificial; and contribution-only schema tests cannot
prove a complete human revision rebase while old Submission foreign keys still
point to mutable Task context. CP08 will add its fields and minimal existing
writers together after this port. Full authorized revision preparation and its
immutable-context FK replacement remain with the later revision operation.
Retained work must never acquire invented lineage from a current selector.

## Bounded change

### Allowed

- `backend/app/modules/projects/api/locked_policy.py` and exports: extend the
  existing immutable facts and port with an active-for-new-work read; retain the
  exact frozen selector operation with one canonical result contract.
- `backend/app/modules/projects/locked_policy_repository.py` and a small same-owner
  context projection helper if needed; existing PROJECTS adapter root wiring.
- Existing activation, proposal/finalization and post-policy custody readers:
  narrowly reuse their exact validation for active/superseded guide reads,
  refresh cached ORM values, and preserve draft-only mutation guards.
- Exact affected ART consumers only if a required type adaptation is necessary;
  no ART business/authority behavior. Existing TASK selector persistence is not
  changed in this chunk.
- Focused PROJECTS contract/PostgreSQL tests and affected downstream shared
  fixtures, ART/AUTH regression tests, exact test-lane/behavior registrations and
  genuinely shrinking structural-debt measurements if required.
- Current guide architecture/operations/data-model documentation, roadmap and
  initiative navigation; adopted ARCH03A/CP08/03B sequence contracts. Preserve
  main's MCP row and unrelated ongoing work.

### Not allowed

New HTTP endpoints, AUTH grants/actions, migrations or Task/Assignment/Submission
lineage fields/writers; CON selection/evaluation; checker execution; provider
calls; a new guide activation operation; compatibility aliases or a partial
context fallback; historical evidence fabrication or retained-data deletion;
claiming complete human revision rebase or introducing activation chronology.

## Design and decisions

1. Extend `ProjectLockedPolicyContextPort` with `lock_active_policy_context` for
   an exact project. Both active and frozen reads share the same complete loader.
   Frozen lookup continues to use the exact existing guide/version/source and
   effective/pre-submit IDs/hashes. These select one immutable activated guide;
   they do not select current CON or silently substitute another setup.
2. Require CP07 activation custody, its exact post-policy projection/approval,
   unified finalization and separate pre-policy approval, canonical stored
   bodies, selected review/revision policies and same-project contribution
   identity. Reuse existing owner validation rather than another compiler or
   policy-selection algorithm. Active reads require the sole active guide;
   frozen reads admit active/superseded exact custody, including later CON
   retirement, without rerunning current eligibility.
3. Extend the current fact type with required immutable activation receipt and
   canonical artifact/post-submit/review/revision bodies and catalogue snapshots.
   The receipt supplies exact setup/finalization/result/component identities,
   approval custody and contribution-policy selectors. Existing direct pre-policy
   projections remain validated against that same receipt for ART consumption.
   No ORM, session, mutable body, raw guide content or provider handle escapes.
4. Use actual CP07 operation ID, per-guide activation generation and timestamp.
   Do not rename per-guide generation as project-wide chronology. The old planned
   activation-sequence field has no source and is deferred with revision semantics.
5. Require a caller transaction; never commit or mutate product state. Trace
   Project/attempt/guide/source/policy lock order against existing mutations;
   retain fresh reads after waiting. No new AUTH lock is acquired by this reader.
6. Replace affected fabricated-positive guide fixtures with real saved approval,
   CON publication and CP07 activation. Retain deliberate unbound/corrupt fixtures
   only as negative or migration-preservation tests. No guard disabling to make a
   positive complete-context test pass.

## Acceptance criteria

- Active and exact frozen reads return the same complete immutable graph for a
  valid guide; frozen reads remain exact after a successor guide or CON retirement.
- Missing activation, either approval, finalization/source/catalogue mismatch,
  foreign or substituted selectors, invalid bodies/hashes and unsupported
  lifecycle states deny with the existing bounded context-unavailable error.
- A new active read returns the successor while the old frozen request still
  returns its original graph; a newer publication alone selects nothing.
- Active/superseded context reads cannot broaden proposal/approval mutation
  eligibility. Tests retain valid draft operations and active mutation denials.
- Real PostgreSQL readers refresh preloaded rows and serialize against guide
  replacement/archival in both orders, with observed waiter/blocker evidence.
- Existing ART consumers use the sole strengthened port; no second partial path
  or compatibility fixtures remain in the affected scope.

## Risk and review routing

- Risk: L1.
- Plan: architecture/reuse and security/QA feasibility reviews before code.
- Implementation: architecture/reuse, security, QA/test-delta, docs/product-ops;
  CI-integrity for test ownership and final hosted proof.
- Human focus: complete source custody, frozen versus active selection, caller
  transaction/lock order, no task/HTTP scope expansion, and corrected sequence.

## Evidence

Lead runs relevant unit and real isolated PostgreSQL tests, Ruff, module/AUTH
boundaries, Markdown links, stale wording, Commitrail records, exact inventories
and hosted complete coverage. New/materially changed modules remain at least 90%.
Concrete named tests will be recorded with implementation. Required falsification:
remove activation-custody validation and prove the positive-shape unbound-guide
negative fails; substitute one exact receipt/policy selector while preserving all
other valid fields; and remove row refresh to expose a stale identity-map read.
Full suite and aggregate coverage remain hosted. Local evidence records exact
head and resource cleanup; no private guide documents or live providers are used.
