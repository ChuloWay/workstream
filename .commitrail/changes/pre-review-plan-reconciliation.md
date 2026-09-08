# Reconcile delivery plans through allow_review

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Existing owner plans describe one acyclic, non-overlapping path from unified guide setup through canonical `allow_review`.

## Intent

Finish the planning reconciliation before further product implementation.
Keep pre-submission intake separate from post-submission work evaluation;
preserve platform defaults plus project-specific policy composition. Do not
restart completed work or add another contribution-permission system.

## Current behavior

AUTH-12B2 is complete in PR #384. Its explicit adapter authorizes hidden
finalization; live setup composition remains POL-04B. Existing pending plans
incorrectly give POL-07 durable CHECKER persistence before ARCH-04C owns it,
place the CHECKER contract after guide activation depends on its executability,
and describe CP07 activation through the sufficiency action. PROJECTS still
has a legacy PaymentPolicy readiness guard. Finalized setup rows are immutable,
so later approvals cannot reuse legacy same-row setup writes.

## Bounded change

### Allowed

- This combined change record.
- Existing WS-POL-003, WS-ARCH-001, WS-AUTH-001, WS-ART-001, WS-CON-001 and
  WS-XINT-002 overviews and adopted pending plan/chunk-map records.
- `.commitrail/INDEX.md` and `docs/roadmap_status.md` for affected navigation,
  current capability, ownership and next-boundary reconciliation.
- Local roadmap exports only if present; no new export or roadmap system.

### Not allowed

- Product code, schemas, migrations, tests, CI, skills or reviewer changes.
- Rewriting completed change records or historical review evidence.
- Downstream review/revision execution, ContributionRecord implementation,
  public Submission cutover or new automatic implementation starts.
- Declaring future capabilities implemented, broad authority, arbitrary model
  tools/plugins, or compatibility paths that bypass the new owner boundaries.

## Design and decisions

Use current `planning/` files in the existing ARCH and POL initiatives for
cross-owner dependency order and policy semantics. Their pending corrected
contracts supersede the conflicting proposals in verbatim `pre-cutover/`
history; never modify that protected archive. Overviews link current work
first and preserved history separately. Each behavior has one owner and one
future implementation boundary.
Hidden capability proof precedes exact authority and live composition. A guide
requires executable registered checks, not an already-existing submitted task
or a completed CheckerRun. Runtime execution/persistence follows immutable
Submission creation. Preserve immutable setup history; later policy operations
own separate records. Remove legacy semantic gates when replacing their
consumer; physical deletion does not become an upstream activation dependency.

## Acceptance criteria

- One explicit dependency graph has no cycle; parallel work has disjoint
  mutation owners and no duplicate implementation contract.
- CP07 is hidden PROJECTS activation behavior; AUTH-12H alone owns its exact
  activation authority. Review/revision policy configuration is required,
  downstream REV execution is not.
- Effective intake policy combines mandatory platform defaults with approved
  supported project rules. Post-submit evaluation is a separate registered
  capability, not another setup-agent invocation or automatic acceptance.
- Finalization, approval and correction custody remain immutable and distinct.
- Each pending boundary specifies inputs, output/owner, negative-path proof
  and dependencies; later exact-file expansion does not invent architecture.
- Roadmap and owner entry pages agree; completed history is preserved.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, security, product_ops, documentation;
  plan-review includes feasibility and missing-proof inspection.
- Human review focus: dependency direction, phase semantics, required-check
  executability, policy lock/rebase boundaries, and no scope expansion into REV.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Dependency order is feasible | Plan review against canonical owners and a topological dependency check; restored-cycle mutant rejected | Verified as a plan | Future implementation must prove runtime behavior |
| Navigation and wording agree | Markdown links, stale-wording scans, Commitrail validator, diff check | Verified | Historical files remain historical |
| No product or gate mutation | Exact changed-path inspection | Verified | No runtime capability is delivered by this PR |

## Review findings

Dependency and ownership defects are repaired in current pending plans;
exact-head review results belong to this PR's summary. The review also
identified still-live legacy PaymentPolicy response/checker consumers: CP07
owns complete replacement response semantics, and CP09 deletion waits for
zero consumers. A leftover XINT label now explicitly names ARCH-04D as its
replacement. Preserved history was restored unchanged when archive validation
identified that corrections belong in current records.

External review further clarified public route cutover versus physical deletion,
pre-I/O denial versus post-I/O result suppression, and separate TASK dispatch,
outbox, CHECKER attempt and routing uniqueness. CP09 also requires recoverable
retained history, not merely zero live consumers; unsupported conversion must
never be guessed to permit deletion.

## Reconciliation

- Current-source reconciliation: PR #384 completes AUTH-12B2; main `fb4553cc`.
- Next usable boundary: POL-04B live setup cutover; independent CP05 policy
  activation and hidden CHECKER contract work follow their owner dependencies.
- Remaining risks: required unsupported evaluator capabilities must be
  implemented and registered before the affected guide can activate.
