# Reconcile delivery plans through allow_review

- Initiative: None
- Durable disposition: Planned
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
- REV/XINT-003 entry navigation only, to adopt the exact upstream `allow_review`
  boundary without changing downstream review/revision execution.
- `.commitrail/INDEX.md` and `docs/roadmap_status.md` for affected navigation,
  current capability, ownership and next-boundary reconciliation.
- Current canonical specifications, contributor entry pages and owner
  conformance documents where they contradict this pre-review planning chain.
  Preserve normative product decisions; correct stale adoption, ownership and
  sequencing rather than silently changing product requirements.
- Local roadmap exports only if present; no new export or roadmap system.

### Not allowed

- Product code, schemas, migrations, tests, CI, skills or reviewer changes.
- Rewriting completed change records or historical review evidence.
- Downstream review/revision execution, ContributionRecord implementation,
  public Submission cutover or new automatic implementation starts.
- Declaring future capabilities implemented, broad authority, arbitrary model
  tools/plugins, or compatibility paths that bypass the new owner boundaries.

## Design and decisions

### Accepted direction: project-controlled acceptance mode

The human clarified that v0.1 must support projects requiring human review and
projects permitting automated acceptance. This extends the earlier planning
boundary: reconcile downstream acceptance/revision/CON contracts, but do not
implement those subsystems in this change. The planning audit is not complete
for this amendment until those consumers are reconciled and reviewed.

Use one boolean in the existing guide-bound ReviewPolicy:
`human_review_required`, default `true`. Do not add an `acceptance_mode` enum,
new policy entity, workflow engine, or second policy-selection system. After
required post-submit checks pass, `true` routes to human review; `false` routes
to authorized FinalAcceptance and the submitter ContributionRecord, without a
reviewer contribution. Both paths retain the complete locked guide and
contribution-policy context. The [policy setting is delivered](review-policy-human-review-required.md);
automated acceptance execution remains unavailable, and configured `false`
cannot activate a guide. No missing/legacy field implies automated acceptance or makes an
otherwise incomplete policy valid. No setting can change for an existing
attempt through a current-policy lookup. Adjudication remains outside v0.1;
do not add its switch or execution path in this work.

- CHECKERS owns evidence, not acceptance. Automated acceptance requires exact,
  approved acceptance conditions that supported post-submit capabilities can
  establish. An unresolved human-review requirement prevents automated-mode
  activation; capability gaps cannot be acknowledged away.
- REV owns the shared FinalAcceptance lifecycle and an explicit automated
  decision participant; TASK owns routing and task transitions, AUTH the exact
  service authority, ART output custody, and CON contribution effects.
- The human branch continues through canonical `allow_review`, ReviewLease and
  Review. The automated branch must consume a separately specified TASK handoff
  bound to the same immutable submission/current checker evidence, never
  reinterpret `allow_review` or insert a synthetic human Review/ReviewLease.
- Both branches use one atomic final-acceptance/submitter-ContributionRecord/
  applicable compensation-effects contract. Only an actual eligible human
  review can create a reviewer contribution; automated execution earns none.
- Correctable work failure follows explicit locked remediation rules.
  Infrastructure failure or uncertain execution is not contributor failure.
  Preserve existing checker-remediation semantics unless a reviewed contract
  explicitly changes them; no invented human revision round or implicit rebase.
- Submission ZIP bindings remain distinct from checker output/log bindings.
  Both reference the exact attempt; automated acceptance must retain the same
  inspectable evidence that a human reviewer would need.

Required follow-through before automated-acceptance runtime implementation
(not before the policy-setting change below): reconcile FinalAcceptance source
shape and database constraints, CON source validation and compensation terms,
TASK branch/currentness/replay, AUTH action custody, guide activation and policy
schema/hash lineage, and revision limits/recovery. Specify tests for stale or
mixed evidence, cross-project denial, duplicate completion, mode substitution,
unsupported human requirements, absent required outputs, and atomic rollback.
The existing human-only contracts remain implementation authority until their
explicit replacement is reconciled; this amendment does not activate a bypass.

<a id="product-builder-handoff-implement-the-setting-next"></a>

### Product-builder handoff: setting delivered

The [bounded implementation](review-policy-human-review-required.md) delivers
this handoff: the existing guide-bound ReviewPolicy has the strict boolean,
persistence, read projection, versioned hashes, migration and activation guard.
The original acceptance criteria below remain the preserved handoff contract.
Current work advances to the remaining boundaries in Reconciliation; this
setting adds no POL compiler or permission surface and preserves exact mutation
authorization.

Acceptance criteria for that change:

- Initial policy creation defaults to `true`; persist and expose an actual boolean.
  Input must accept only strict JSON booleans, not strings, numbers or null;
  require negative tests for each alongside omission handling.
  Include it in the immutable policy semantics/hash and normal lineage.
- For a policy update/supersession, omission preserves the predecessor's
  effective boolean; explicit true or false changes the new version only.
  Distinguish omitted input from explicit true before applying creation defaults.
  Test that an omitted setting cannot silently reset an explicit false policy.
- Explicit `false` is configurable as planned policy, but must not activate a
  guide until the authorized automated acceptance/CON path is available.
  Reject unsupported activation explicitly; never silently flip it to `true`.
  This change must guard the existing `ProjectService.activate_guide` path,
  not only future composition. CP07 hidden activation and AUTH-12H live
  activation must inherit the same requirement; test both current activation
  reachability and the future owner contract without implementing those chunks.
- Migrate existing history without rewriting stored policy hashes or inventing
  missing policy completeness. Specify legacy-version interpretation versus
  new-version hashing explicitly and prove existing locks still resolve.
  Use an explicit persisted semantics/hash-format discriminator: legacy-format
  rows interpret the absent setting as true and retain their exact digest;
  new-format rows hash the explicit boolean. Pin the format to the immutable
  policy version. Never infer it from timestamps, trial-validation against two
  hash shapes, or the boolean value itself. Backfill must not make legacy true
  indistinguishable from new-format true.
- Policy read/write round-trip, omitted-input default, explicit false, invalid
  input, unauthorized/cross-project mutation, hash differentiation, old-version
  preservation and unavailable-path activation denial require focused tests.
- Prohibit checker execution changes, synthetic Reviews, new permissions,
  automatic acceptance activation, adjudication, and weakened checks here.
  Review routing: architecture/security and product/docs, proportionate to
  this exact policy-lineage change. Risk L1. Human focus: safe default and no
  changes to already-locked attempts.

Then extend the existing TASK post-check routing and REV/CON final-acceptance
work, not a parallel lifecycle: current successful evidence plus locked `true`
admits human review; locked `false` invokes the separately authorized shared
acceptance participant. Its implementation must prove source exclusivity,
atomic task/acceptance/contribution/conditional-award effects, replay safety,
and no reviewer record. Live `false` activation follows that proof, without
depending on live human queues/leases/decision endpoints. It still depends on
shared final-acceptance and contribution foundations. This can deliver the
first automated end-to-end path before human review is live; it does not
remove human review/revision from the v0.1 release requirements.

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
| Dependency order is feasible | Cross-owner plan inspection and a 30-boundary topological check; restored activation-cycle mutant rejected | Local planning check passed | Future implementation must prove the described locks, authority and transaction behavior |
| Navigation and wording agree | Markdown links, stale-wording scans, Commitrail validator, diff check, focused cross-document finding replay | Local checks and finding replay passed | This is not exact-head hosted evidence or a merge-readiness verdict |
| No product or gate mutation | Exact changed-path inspection | Verified | No runtime capability is delivered by this PR |

## Review findings

The cross-document audit found additional defects. Local corrections include active
ContributionPolicy selector validation for new guide activation without
reselecting existing locked work; a predecessor-owned evaluation identity and
currentness protocol before TASK dispatch consumes it; and stale current
authorization/conformance instructions. Earlier exact-head review of the
smaller diff is not evidence for these broader edits; focused local finding
replays cover the corrections without claiming exact-head or runtime readiness.

### Cross-board audit trace

| Boundary inspected | Concrete mismatch | Local planning correction |
|---|---|---|
| Unified setup / provider adapter | Stored UUID was described as provider recovery although the adapter receives no key and has no retrieve/resume | Uncertainty stays blocked; same-operation recovery cannot be claimed without typed provider support |
| Catalogue -> compilation | Sparse PROJECTS projection could not supply promised evaluator configuration/result/budget facts | CHECKERS owns the public catalogue/schema before approval-eligible compilation; old generations remain immutable |
| Requirement classification | Plans invented acknowledgeable optional capability gaps and universal semantic automation | Existing capability gaps all block; explicit human-review requirements remain valid; test each evaluator's actual coverage claim |
| Complete proposal -> approval | Existing GETs show status/IDs, while full visibility/correction was deferred until POL-08 | POL-05A owns bounded review and setup-wide correction; AUTH-12F4 governs it before live approval |
| Finalized setup -> post policy | Operating docs resumed a terminal setup row | Separate immutable approval/correction/projection operations; no second inference or row reopening |
| CON -> guide -> task | Any published version could be selected, while canonical activation requires active current selector | Activation validation and later guide-bound revision validation are distinct; existing work never reselects global latest |
| Task/Assignment -> Submission | A naive composite FK would couple old immutable stamps to mutable current assignment policy | Creation-time equality plus immutable historical stamps and rebase-safe guards; direct SQL counterexamples required |
| Task public surfaces | Broad AUTH-13 named actions that do not exist and neither owner allowed the router | Current 03B/03C route/action/principal manifest; hidden declarations then exact live activation |
| Submitter invalidation | Response hint was not a reconciliation worker | TASK owns exact event handler; originating AUTH event is durable; dispatcher/service authority is explicit |
| Checker output | Input materialization, result persistence and activation left ART output storage unowned | Named ART-04B2 output custody, then atomic verified binding/result/completion-event publication |
| Async delivery | Shared outbox had persistence only | AUTH-OUTBOX-01 -> CON-02B hidden mechanics -> AUTH-OUTBOX-02; handlers require separate feature authority |
| Checker -> TASK | Attempt identity was defined after its consumer and currentness serialization was implicit | 04A envelope, 04C fence, TASK-then-CHECKERS lock order; 04E hidden/authority/live boundaries |
| Retry and routing | Terminal Operator retry was conflated with unfinished recovery; old direct routing could coexist | Separate retry identities/authority, atomic submission+request and manifest+state, canonical legacy-call cutover |
| Contributor entry points | Current docs exposed historical pending gates/counts and archive-first navigation | Current owner links first; completed foundations labeled; runtime owner values distinguished from historical plan labels |

These are planning/source inspections, not evidence that the future runtime
has been implemented or stress-tested. Focused architecture/security and
documentation/product finding replays closed their identified local defects.
New action/permission manifests remain proposed for human design review;
neither this record nor local reviewer feedback registers or activates them.
The human approved publication of this reconciled planning change; product
implementation remains a separate bounded change owned by the product builder.

The acceptance-setting amendment also scopes higher-level definitions and
human-only lifecycle examples explicitly: README, architecture lockdown,
glossary, product brief, operating flows and architecture sources must not
make human review universal. Existing binary architecture exports remain
labeled human-branch snapshots rather than claimed current full-scope exports.
Provider-uncertainty proof is blocked/no-second-call until real recovery exists;
delivery/in-flight recovery must not be confused with a new terminal retry.

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
- Delivered product-builder boundary: the existing ReviewPolicy boolean in the
  preserved handoff above; automated acceptance remains unavailable.
- Next usable boundaries: CP05 policy activation and ARCH-04A catalogue/schema
  reconciliation retain their independent prerequisites; POL-04B consumes that corrected
  catalogue plus completed finalization authority. Shared dispatch is an
  explicit independent foundation, not implicit delivery from outbox storage.
- Remaining risks: required unsupported evaluator capabilities must be
  implemented and registered before the affected guide can activate.
