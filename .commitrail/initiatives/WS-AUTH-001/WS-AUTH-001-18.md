# WS-AUTH-001-18 — Public manager guide activation

- Initiative: WS-AUTH-001
- Durable disposition: Complete
- Intended merge outcome: an exact-project Project Manager can discover the
  complete activation selections and invoke the existing atomic guide activation
  through public APIs, without Finance privileges or internal database access.

## Intent

Main `ed4ac83e` contains canonical history cleanup and public Finance policy
administration. PROJECTS `GuideActivationService.activate` already binds separate
pre/post approvals, review/revision versions and a published ContributionPolicy,
with AUTH-12H live manager authority, replay and PostgreSQL custody. Public post
policy review exposes approved source facts but not all remaining activation
selectors. Public activation is absent. The next boundary must deliver a usable
manager journey, not an isolated POST whose inputs require private queries.

## Bounded change

### Allowed

- PROJECTS public activation/post-policy value contracts, the existing activation
  and post-policy services/repositories, and directly affected owner tests.
- A bounded CON published-selector read on its existing owner repository/public
  port; application adapters translate to PROJECTS-local facts. No Finance body
  or unpublished policy details are disclosed through manager context.
- Application composition/dependencies and public guide activation routes,
  current post-policy read composition, existing AUTH read/activation adapters
  only where necessary to preserve exact authority and safe HTTP errors.
- Focused public API tests, existing activation/approval fixtures, actual API
  drill, route/action/OpenAPI/lane/ownership and identifier-generation inventories
  affected by exposure.
- README, operating/canonical activation contracts, roadmap affected summaries,
  scoreboard/dependency/gates/trace references, current diagrams and their rendered
  exports, AUTH/ARCH/CON/POL overview/chunk-map and index next boundary, this record; ignored spreadsheet exports if present.

### Not allowed

New activation semantics or duplicate readiness engine; Finance policy mutation
by managers; default/economic policy fabrication; provider inference, checker
execution, intake/Submission activation, acceptance/revision implementation;
leases/skip; compatibility routes or fallback authority; retained-data deletion;
weakening CI, selecting away failures, or percentage-driven test additions.

## Design and decisions

Reuse manager post-policy read authority (`project.guide_compilation.review_package.read`)
for bounded activation selections associated with that exact approved chain.
Prefer extending the existing read rather than introducing another authority or
parallel policy discovery workflow. The response must expose review/revision
IDs, generations and hashes, guide generation, exact predecessor guide identity
and generation, separately approved post-policy operation/digest, and published
ContributionPolicy/version selectors needed by the existing command. It must
not promise readiness merely because selectors exist. Missing prerequisites
remain explicit; no hidden auto-publication or auto-approval.

CON retains ownership of finding its current published selector through a typed
owner port. This read grants neither policy-body access nor mutation authority.
PROJECTS retains guide, approvals and policy semantics. AUTH locks precede product
locks; use existing project-root serialization and lock ordering. Scope SQL by
project before locks and bind the entire disclosed context to read audit facts.

Expose the existing activation command through a project/guide-scoped POST.
Require exactly one UUID Idempotency-Key before actor resolution/product SQL;
server context supplies actor/request identity. Reject mismatched path/body
identities. Do not accept audit/authority/actor fields. Response validation occurs
before commit; effects, AUTH evidence and replay commit atomically. Typed denial,
missing targets, conflicts and unavailable storage remain sanitized and distinct.
Existing replay must recheck live authority and preserve the original receipt
through supersession/retirement; do not silently regenerate a command on retry.

Inspect existing read behavior for activated/superseded guides and preserve exact
retained receipt recovery where offered. A new activation uses only current
approved inputs; a stale display must reject rather than substitute newer facts.
False human-review mode remains blocked by current readiness. No new authority
or broader role is needed for the existing activation operation.

## Acceptance criteria

- An authorized manager obtains required selectors through public reads and
  activates an approved guide without private setup queries. Finance publishes
  its policy independently; manager cannot perform Finance mutations.
- Separate pre/post approvals remain mandatory. A context read is not activation
  or approval. Stale policy/guide/predecessor changes reject the old command.
- First activation and successor activation retain exact locked lineage; repeat
  key returns the original receipt without duplicate effects/audit. Revocation
  denies both reads and replay. Wrong-project requests do not lock foreign rows.
- Duplicate/missing/invalid headers reject before actor/product access. A failed
  response validation or real audit/storage write rolls back all effects.
- Public API drill reaches activation through real routes; meaningful existing
  PostgreSQL replay, race and lineage tests remain. Add only missing boundary
  proof, with failing-defect probes for new critical guards.
- Current documentation distinguishes public exposure from deployment and moves
  next dependency to approved-guide intake while retaining both planned
  human-review and automated-acceptance branches.

## Risk and review routing

- Risk class: L1 (bounded authorization and public lifecycle exposure).
- Required reviewers: security/architecture plan review; security/architecture,
  QA/test-delta and product operations implementation review; docs and CI integrity
  for actual affected contracts/evidence, proportionate to changes.
- Human focus: complete usable manager journey, no Finance privilege expansion,
  exact selection/replay, atomic evidence, no premature execution/acceptance.

## Evidence

Existing activation and AUTH-12H suites establish owner semantics. Inspect their
proof before adding tests. New focused public activation tests and real API drill
are implementation targets, not claims of completed execution. Run Ruff,
module/AUTH/structure and contract inventories, Markdown links/stale wording,
Commitrail validation and the complete hosted suite. Coverage remains diagnostic.
No local sheet exports are currently present. Coordinate with open test-audit PR
#448 by preserving its service-provisioning scope. No roadmap capability is
claimed delivered until the intended implementation and verification exist.

Next usable boundary: approved-guide intake integration, then immutable admitted
Submission and durable post-submit evaluation. This does not resume lease work.

## Plan-review resolutions

- Read lock order is explicit: existing manager AUTH PREP, exact requested
  PROJECT row, existing proposal/finalization/guide/post-policy rows, predecessor
  and review/revision selectors, then CON published-selector query. Publication
  and retirement lock this same PROJECT first. Never acquire the PROJECT lock
  for the first time after guide/attempt locks. Wrong-project queries cannot
  lock a foreign guide or policy.
- Extend the draft-only post-policy review package with `activation_context`.
  Review/revision triples, predecessor ID/generation, published CON policy/version
  and post-approval operation/output digest are complete pairs/triples or absent.
  Read the approval digest from retained `custody.approval.output_digest`.
  The existing read facts digest commits to the entire expanded package.
  Do not add a readiness flag, implicit command builder or active-guide re-read
  dependency: replay uses the original POST body and immutable receipt.
- POST input excludes idempotency and server authority facts. Validate and detach
  the receipt via TypeAdapter before commit, including serialization validation;
  response-model validation after commit is insufficient. Apply this same
  pre-commit validation to the expanded read response.
- Refine the existing shared guide error boundary: AuthorizationDenied keeps the
  concealed `authority_unavailable`/404 outcome. AuthorizationUnavailable and
  PreparedAuthorizationInvalid become `authorization_service_unavailable`/503.
  Keep missing=404, stale/conflict=409, SQL=503. Existing absent-adapter, non-human
  and invalid-root preconditions remain fail-closed. Shared guide proposal error
  helper/HTTP mapping and their directly affected failure tests are allowed files.
- Add focused proofs for stale guide/predecessor/review/revision/CON/post-approval
  selections; replay after active/superseded state and CON retirement; revoked
  new/replay authority; project lock races with CON publication/retirement and
  competing activation; wrong-project noninterference; both response validation
  and serialization failure after staged writes; a real audit insert failure.
  Reuse existing owner proofs where they already establish the same boundary.
- Plan review traced feasibility, not executed new runtime evidence. No new
  migration or AUTH action is required by this design.
- At activation's exact CON validation boundary, translate the adapter's invalid
  selection `ValueError` (foreign, missing, retired or changed selector) into the
  same sanitized `proposal_stale`/409. Do not catch storage or authority failures
  as staleness; those retain unavailable handling. CON's validation remains
  fail-closed and no policy-existence distinction is exposed.

## Implemented proof boundaries

- `tests/projects/public_activation/` covers public selection/activation, stale
  inputs, retirement/revocation replay, transaction rollback on serialized response
  failures and an actual audit INSERT failure, project-scoped noninterference and
  concurrent Finance retirement/activation.
- Existing PROJECTS and AUTH activation suites retain successor/historical replay,
  exact policy custody, service denial and live authorization race proof.
- `scripts/api_contract_e2e.py` uses scripted setup prerequisites, separate public
  Finance publication, public manager selector reads and public activation/replay
  before the existing claim/start drill. It does not claim live model inference
  or public Submission/post-submit execution.
- The affected post-policy fixtures now create governed guide metadata through
  the existing authorized fixture; no missing-generation fallback was added.
- No migrations, new dependencies, compatibility routes or retained-data deletion.
  Coverage is diagnostic. Exact candidate execution/reviewer freshness belongs to
  the PR, not this durable record. Local spreadsheet exports are absent.
