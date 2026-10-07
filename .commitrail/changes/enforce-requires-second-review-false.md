# Enforce requires_second_review=false

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: ReviewPolicy accepts and persists only `requires_second_review=false`, while existing false-policy hashes and immutable lineage remain unchanged.

## Intent

Adjudication and second-review lifecycle behavior are deferred. The current
ReviewPolicy surface nevertheless accepts `requires_second_review=true`, and
the database permits the unsupported value through raw writes. This change
closes both paths without inventing review behavior or rewriting retained
policy facts.

## Current behavior

`ReviewPolicyInput`, `ReviewPolicySemantics`, and `ReviewPolicyResponse` type the
field as an unrestricted boolean. `ReviewPolicy` stores it as a non-null boolean
without a false-only constraint. The authorized policy writer hashes the field,
shared locked-policy projection validates it, and the external API drill
currently submits true on replacement. Migration 0023 is the current stacked
predecessor and owns the separate obsolete TASK payment cleanup.

## Bounded change

### Allowed

- PROJECTS review-policy input, immutable semantics/lineage response and ORM
  constraint metadata.
- One additive migration 0024 after 0023: lock `review_policies`, refuse any
  retained true row, then install the false-only check constraint.
- Alembic accepted-revision registration, graph proof, PostgreSQL 16 schema
  fingerprint, semantic test-lane registration and the external API drill.
- Focused input/hash, shared projection, public API, raw-write and real
  predecessor-upgrade tests.
- Current README, architecture, review lifecycle, guide template and roadmap
  statements affected by the supported ReviewPolicy contract.

### Not allowed

- Second-review, adjudication, reviewer assignment or decision behavior.
- ContributionPolicy, award, payment, routing, activation or acceptance
  semantics.
- Retained-data rewrite/deletion, policy rehashing, migration 0023 changes,
  compatibility variants or duplicate payment cleanup.

## Design and decisions

Use `Literal[False] = False` at untrusted input and immutable typed lineage
boundaries. Keep the stored column because it remains part of canonical v1/v2
policy bodies and removing it would change existing false-policy hashes. Add a
named PostgreSQL check for raw-write enforcement. Migration 0024 takes an
`ACCESS EXCLUSIVE` table lock across preflight and constraint installation so a
writer cannot introduce true between them. A retained true row raises SQLSTATE
23514 before DDL; the migration does not repair, rewrite, delete or rehash it.

## Acceptance criteria

- [x] Public true input returns 422 without advancing the selected policy.
- [x] Omitted/false v1 and v2 canonical hashes retain their exact bytes.
- [x] Typed immutable lineage and shared locked-policy projection reject true.
- [x] PostgreSQL rejects raw true writes through the named model/migration
  constraint.
- [x] Real 0023-to-0024 upgrade refuses a custody-committed retained true policy
  with its row, hash, guide selector and schema version unchanged.
- [x] Ordinary false-only upgrade preserves policy rows/hashes/selectors and
  installs one recognized 0024 head.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, reuse/dedup, security, QA, test delta, documentation
- Human review focus: retained-fact refusal, unchanged hashes, schema/model/type parity, and no accidental second-review or payment semantics

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Typed and shared caller behavior | Focused review-policy, locked-policy and identity-lineage pytest modules | False contracts and fixed hash bytes pass; true lineage fails closed | Full hosted suite remains external evidence |
| PostgreSQL schema identity | Fresh PostgreSQL 16 migration through 0024, canonical fingerprint generation and focused graph/raw-write proof | Head installs the named constraint; fingerprint updated from the real schema; focused boundary nodes pass | Hosted PostgreSQL lane remains external evidence |
| Retained-data safety | Actual 0023 predecessor migration tests | Custody-committed true facts refuse unchanged; false facts upgrade unchanged | Operational handling of any discovered true row requires a separate preservation decision |

## Review findings

No material finding is recorded in this durable change record.

## Reconciliation

- Current-source reconciliation: stacked on the current obsolete-payment cleanup branch; 0024 extends its 0023 head without changing that migration or cleanup behavior.
- Next usable boundary: second-review/adjudication behavior remains deferred; other pilot work proceeds only after this pull request is merged.
- Remaining risks: a database containing retained true policies cannot upgrade until an explicit preservation/disposition design is approved.
