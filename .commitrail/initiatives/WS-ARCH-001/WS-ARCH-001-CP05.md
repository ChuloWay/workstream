# WS-ARCH-001-CP05 — Exact ContributionPolicy authorization activation

- Initiative: WS-ARCH-001
- Durable disposition: Planned
- Intended merge outcome: The five existing ContributionPolicy actions use exact Finance Authority and transaction-bound authorization through the existing CON public ports.

## Intent

Continue after the delivered ReviewPolicy setting by activating the existing
ContributionPolicy operations under their canonical permissions. This unblocks
CP06 selected-policy validation without enabling guide activation or payment.

## Current behavior

Main `dab12dcb` includes PR #386. CP04 draft/publication/retirement behavior and
immutable operation custody already exist in CONTRIBUTIONS. The five
`contribution.policy.*` catalogue entries remain planned. CON defaults to
`DenyContributionPolicyAuthorization`; AUTH public resource facts already exist.
The adapter-binding activation supplies the established kernel/PREP and public
adapter composition pattern. Only Finance Authority holds the existing
`compensation.policy.manage` permission.

## Bounded change

### Allowed

- AUTH `catalogue.py`, `kernel.py`, `prepared.py`, `runtime.py`; new focused
  `domain/contribution_policies.py`, `domain/prepared_contribution_policies.py`,
  `contribution_policy_authorization.py`; public `api/contribution_policies.py`
  and exports for the exact mutation-authority port/facts.
- `app/adapters/auth/contribution_policies.py` and AUTH composition exports;
  existing `app/adapters/contributions/__init__.py` only if explicit composition
  needs a bounded adjustment. Keep cross-owner imports on public APIs.
- Focused `tests/authorization/contribution_policies/` and CON integration tests,
  existing registration/parity expectations and shared fixture reuse. Existing
  CP04 tests remain authoritative for product validation/publication behavior.
- Exact AUTH/module ledgers and test-lane registration/debt refresh if required;
  no new structural debt or relaxed thresholds.
- This record, ARCH/CON/AUTH overviews and index, roadmap and current AUTH/CON
  specifications/operations/custody docs for the five action availability delta.
  No modification of a second change record; adopted planning skeletons remain
  planning history with current navigation pointing to this implementation.

### Not allowed

- New permissions, roles, service identities, service matrix entries or HTTP
  routes; no broad Finance, Project Manager, Operator or service powers.
- CON policy lifecycle, selector, quantity, compensation-binding or validation
  redesign; no new ORM table/migration expected (current head is 0011).
- CP06/CP07 guide binding/activation, TASK/REV/checker behavior, automated
  acceptance, awards, fulfillment, providers or frontend implementation.
- New caller commits, bypassed PREP, permissive fallbacks, changed test gates,
  current-policy rebase or weakened historical evidence.

## Design and decisions

Activate only `contribution.policy.read`, `.create_draft`, `.update_draft`,
`.publish` and `.retire`, keeping their IDs, owner metadata and sole permission.
The closed principal manifest permits active human Finance Authority with an
active verified identity link and either system grant or exact project grant.
Deny foreign-project grants, inactive/substituted actors/links/grants, all other
admin/project roles and every service identity; unrelated planned actions stay
unavailable. Scope and permission come from canonical AUTH repositories/policy,
never inference from a role label or caller-supplied grant.

Use action-specific strict frozen resource contexts, canonical public resource
digests, and exact kernel registrations. Read authorization is serialized with
current actor/link/grant locks. Four mutations prepare/consume/close through the
existing transaction-local PREP owner; bind actor, action, operation/request,
project, policy/version IDs, expected state, and publication graph/bindings.
AUTH public facts must carry the complete server-owned CON authorization facts;
application adapters translate public values without private CON imports.
Publication/retirement graph and lifecycle locks remain CON-owned. One caller
transaction owns decision evidence and product writes, with one final commit.

Retain fresh authorization on exact committed CON replay: replay grants no new
mutation, but revoked authority cannot recover a result. Conflicting replay,
changed public facts or substituted PREP handle fail closed. Keep hidden default
composition unavailable unless the explicit authenticated AUTH adapter is supplied;
no ambient context or new transport exposure.

## Acceptance criteria

- The exact five catalogue actions become active; permission/owner/cardinality,
  database parity, service matrix and unrelated planned denial are unchanged.
- Each action allows system/exact-project Finance Authority through real kernel
  composition and conceals unauthorized or foreign targets; other roles and
  services deny. Actor/link/grant revocation and substitution fail at consume.
- Strict public facts and resources bind every action-specific field; mutated
  operation, digest, project, policy, version, state and publication graph/binding
  facts cannot reuse a handle. Read cannot issue mutation authority.
- Existing CON behavior executes through real AUTH/PREP and public adapters:
  draft creation/update, compensated and unpaid publication, retirement and exact
  replay. Invalid quantities, incomplete graph and inactive/foreign bindings still
  reject through existing CON validation rather than AUTH-only doubles.
- Publication/retirement races serialize under existing ownership, exact replay
  requires fresh authority, conflicting replay denies, and failed transactions
  retain neither policy changes nor decision/effect evidence.
- New authorization owners reach at least 90% coverage with meaningful negative
  controls. No changed assertion or marker weakens the hosted execution gate.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, security, product_ops, QA, test_delta,
  documentation; CI integrity for exact registrations/ledger changes.
- Plan review: architecture/security before implementation, including reachability
  of real CON mutation/replay tests under PREP and lifecycle locks.
- Human review focus: only Finance Authority policy powers, exact five-action
  activation, fresh replay authorization, one-transaction evidence and unchanged
  policy/compensation semantics.

## Evidence

Use focused local pytest with explicit asyncio plugin and local Ruff; hosted CI
owns PostgreSQL, concurrency, full-suite and coverage execution. Add discriminating
controls for planned-action activation scope, Finance grant scope, exact PREP
fact substitution and replay after revocation. Reuse CP04 invalid-publication
controls with the real AUTH adapter so earlier guards cannot hide the target.
Run module/AUTH/test-boundary validators, Commitrail, Markdown links and stale
wording scans. No local spreadsheet exports are present. Final PR records exact
commands, hashes, hosted totals and impact-routed review closure.

## Reconciliation

- Current-source reconciliation: main `dab12dcb`; CP04A/CP04B prerequisites are
  merged, PR #386 setting is delivered, and there are no open overlapping PRs.
- Next usable boundary: CP06 selected-version validation; ARCH-04A catalogue and
  evaluator conformance remains independent. Do not start either automatically.
- Remaining risks: guide activation, automated acceptance and compensation effects
  remain unavailable until their own complete authority and persistence boundaries.
