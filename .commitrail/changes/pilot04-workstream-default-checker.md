# [PILOT-04] Define The One Workstream Default Checker

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Deliver one versioned, unselected Workstream default
  checker contract and implementation with exactly four blocking defaults and
  warning-only summary and attestation observations.

## Intent

Issue #491 replaces the built-in pre- and post-submit catalogues with one
Workstream-owned default checker plus digest-pinned project images. The merged
external service can execute project images, but the repository does not yet
have the one default checker whose behavior must precede those images. This
change establishes that executable behavior and its stable result contract
without selecting it in the current intake path.

## Current behavior

`backend/app/modules/checkers/pre_submit_execution.py` dispatches the current
versioned pre-submit catalogue. It mixes platform custody checks, project rules,
packet requirements and advisories. The post-submit catalogue separately owns
structural defaults. Both remain active until complete replacement proof permits
one clean cutover. The merged external runtime is intentionally unselected.

## Bounded change

### Allowed

- This record.
- `backend/app/modules/checkers/api/default_checker.py` for closed input/result
  contracts, stable checker identity and behavior digest.
- `backend/app/modules/checkers/default_checker.py` for the four Workstream
  defaults over detached ART/TASK facts and the existing CHECKERS-owned bounded
  material-read capability.
- Focused tests under `backend/tests/checkers/default/` for every positive,
  negative, infrastructure and warning boundary.
- The minimum test-lane and behavior-owner metadata needed to run the new tests
  and assign the two new modules exactly once.
- `docs/architecture_checker_framework.md` and the exact PILOT-04 checker rows
  in `docs/roadmap_status.md` for the implemented but unselected boundary.

### Not allowed

- No policy binding, guide activation/F-020, external project-image selection,
  service composition, public route, CLI or Submission/admission caller wiring.
- No migration, registry mutation, durable run/result/receipt, scheduler,
  retry worker, acceptance or routing behavior.
- No deletion, bypass or parallel execution of either current catalogue. No
  change to their hashes, policies, active callers or tests.
- No project required-file, project size, forbidden-file or generic rule logic.
  No extra blocking Workstream default. Summary and attestation remain warnings.
- No held PILOT-05, PILOT-06 or PILOT-09 work, deployment, merge or issue closure.

## Design and decisions

The checker consumes detached owner facts rather than reparsing a ZIP or
inventing storage access: ART's structural inspection, server-computed archive
commitment and canonical semantic manifest, plus TASK/ART canonical predecessor
identity. It reads bytes only through the existing CHECKERS-owned callback-scoped
material capability, recomputes the manifest identity and rechecks every file
digest. The existing ART sealed-tree projection satisfies that capability without
a CHECKERS-to-ART dependency or any path/storage authority. Unsafe contributor
archives become the one archive-safety finding; storage-integrity and timeout
failures remain recoverable infrastructure outcomes. Exact material/manifest
disagreement also fails as infrastructure instead of blaming the contributor.

The result always has four ordered blocking slots: archive safety, received
identity, high-confidence secrets and task-rule-aware unchanged resubmission.
An evaluated slot is `passed` or `failed`; a slot unavailable after an unsafe
archive is `not_run`. Warning-only summary and attestation observations are
separate closed values. Findings retain only stable categories and counts, not
matched bytes or contributor text.

The checker has a code-owned version and canonical behavior digest. Its manifest
contains the exact four check identities, warning identities, and each secret
signature's category, executable regex source and flags. The implementation
compiles from that same canonical constant, so detector changes alter the
behavior digest and golden contract proof. This is a Workstream implementation
that changes only with a deploy; project rules remain external images.

This component is unselected. A later bounded cutover will bind approved
external policy entries, execute every required pre-image through the merged
service, and invoke the existing caller-owned atomic Submission operation only
after this checker and all required project checks pass. Both catalogues are
removed only after complete pre/post replacement proof; no parallel runtime is
introduced here.

## Acceptance criteria

- [x] The result contract admits exactly four ordered blocking checks and only
  the closed warning-only summary/attestation observations.
- [x] Valid safe ZIP custody, recomputed manifest identity, no high-confidence
  secret and first/changed work pass all four defaults.
- [x] Malformed, encrypted, unsafe, colliding or platform-limit archives return
  one bounded archive finding and do not expose material to later checks.
- [x] Stored-byte/manifest disagreement, inspection timeout/integrity failure or
  stale/unavailable predecessor facts are infrastructure outcomes, never work
  findings or silent passes.
- [x] Exact private-key, cloud-credential and API-token signatures fail without
  retaining matched content; representative near misses pass.
- [x] Exact archive or semantic-manifest replay fails unless the canonical task
  rules/predecessor changed, with parity against the canonical owner semantics.
- [x] Empty summary and attestation add warnings only and never change the four
  blocking verdicts.
- [x] Existing catalogue identities, hashes and execution tests remain unchanged;
  no production composition selects the new checker.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, security, reuse_dedup, qa, test_delta,
  documentation, product_ops, ci_integrity
- Human review focus: Exact four-default boundary, high-confidence pattern
  precision, contributor-vs-infrastructure classification, reuse of ART custody
  and predecessor ownership, bounded secret-free results, and absence of a
  parallel active execution path.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Current owner map | Source inspection of ART inspection/manifest/change owners, both current catalogues and the merged external runtime | Complete at main `e77c48b1086c95cc4c2fc05bdf2fdcffdce52494` | Policy binding, live pre-admission orchestration, post cutover and catalogue removal remain later slices |
| Default behavior and actual ART callback | `pytest -q tests/checkers/default/test_contract.py tests/checkers/default/test_execution.py` | 25 passed | Component remains deliberately unselected |
| Test-lane ownership and focused behavior | `pytest -q tests/checkers/default/test_contract.py tests/checkers/default/test_execution.py tests/test_ci_lane_catalogue.py` | 71 passed | Hosted full-suite evidence follows in the draft PR |
| Public module boundary | `pytest -q tests/architecture/test_module_boundaries.py::test_repository_matches_the_protected_module_boundary tests/architecture/test_module_boundaries.py::test_art_implements_checker_consumer_ports_without_a_public_cycle` | 2 passed | Existing catalogues retain their recorded debt until cutover |
| Behavior-owner partition | `python -m scripts.behavior_ownership validate` | Passed | Hosted evidence still validates the exact merge tree |

## Reconciliation

- Current-source reconciliation: Started from merged PR #528 at main
  `e77c48b1086c95cc4c2fc05bdf2fdcffdce52494`.
- Next usable boundary: Bind approved external policy identities and compose the
  default plus every required project pre-image before the existing atomic
  Submission operation.
- Remaining risks: No caller selects this component in this change; whole-issue
  acceptance, F-020 and both-catalogue removal remain open.
