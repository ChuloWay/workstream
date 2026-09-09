# WS-ARCH-001-04A — One initial v0.1 checker contract

- Initiative: WS-ARCH-001
- Durable disposition: Complete
- Intended merge outcome: remove superseded post-submission catalogue, compiler,
  parser, registry, and projection branches retained or introduced by ARCH-04A;
  use one canonical initial-v0.1 contract throughout its consumers.

## Intent

Workstream has no released software contract requiring backward compatibility.
The human explicitly rejects compatibility layers and parallel old/new
implementations retained merely to preserve earlier development code. Earlier assumptions that development hashes and
schemas must remain executable are withdrawn. Obsolete implementations must be
deleted, not renamed, aliased, or disabled for deferred cleanup.

This correction is limited to the affected post-submit module and its traced
consumers. Repository-wide cleanup is parked and is not a prerequisite. Retain
authorization, locked lineage, atomicity and immutable evidence throughout.

POL-04B follows this already-started bounded correction.
Its incomplete local changes are saved separately and establish no capability.
This correction repairs merged ARCH-04A; it does not resume live guide cutover.

## Observed problem

- `project_agents.py` accepts both a sparse post-submit projection and a separate
  rich `PostSubmissionCapabilityProjectionV2`.
- `projects/post_submit_policy.py` retains the existing compiler/parser and adds
  an independently callable dormant compiler/parser.
- `checkers/runner.py` registers two policy-context implementations and pins
  name-only calls to the older implementation.
- Tests and current documentation explicitly require historical hash and
  implementation preservation. Those requirements contradict the human intent.

## Bounded change

1. Trace both compiler outputs and registry entry paths to all actual consumers.
   Identify domain requirements that remain necessary separately from obsolete
   representation/compatibility machinery.
2. Adopt one complete catalogue/projection shape, one compiler/parser, and one
   policy-context implementation. Remove version-suffixed implementation names,
   dual-schema unions, old registration paths, sparse projections, and hash
   compatibility branches. No replacement aliases or unsupported-schema fallback.
3. Update active consumers, baseline fixtures and relevant persistence contracts
   together. Keep missing required lineage fail-closed; do not invent future
   Task/Submission/ContributionPolicy fields or silently implement another chunk.
4. Replace obsolete preservation tests with canonical-contract and strict rejection
   proof. Preserve meaningful security, integrity, and lifecycle assertions.
5. Reconcile current specifications, roadmap, initiative navigation, and downstream
   chunks so they no longer require deferred legacy preservation/cleanup.

Allowed implementation owners: CHECKERS `api/post_submit_catalogue.py`,
`api/post_submit.py`, `api/__init__.py`, `post_submit_catalogue.py`, `runner.py`,
`post_submit_implementations.py`, `post_submit_contracts.py`; PROJECTS
`post_submit_policy.py` and `interfaces/project_agents.py`. Exact dependent
service, model, migration and test paths must be enumerated by feasibility
review before application edits. Relevant ARCH/POL records, current roadmap,
checker framework documentation, and AGENTS preserve the corrected direction.

Prohibited: POL-04B live cutover, new provider attempts, weakening policy/lineage
checks, retention under misleading new names, new backward migration/compatibility
bridges, and unrelated activation of acceptance, checker execution, or payments.

## Concrete consolidation design

- Keep the complete typed catalogue and compiled-policy shape as the single
  supported representation. Use unsuffixed implementation/schema names and the
  initial product baseline identity; remove the alternate sparse projection,
  alternate compiler, alternate parser, and version-selection maps.
- The existing constrained-spec entry point compiles into that one typed policy.
  Existing services consume derived checker lists from its entries, not a second
  serialized policy representation. Parsing validates the same model and exact
  catalogue/hash. Unsupported earlier bodies reject without translation.
- Registry keys are checker IDs, with one handler and its metadata per key.
  Metadata comparison can reject mismatches, but cannot select an older handler.
- One policy-context checker consumes explicit expected and observed current
  locked facts: guide version; source snapshot ID/hash; effective artifact policy
  ID/hash; pre-submit policy ID/bundle hash; post-submit policy ID/version/hash;
  review policy ID/generation/hash; revision policy ID/generation/hash. Project ID
  remains checked in the owning request/task/policy envelope, because Submission
  has no independently persisted project ID. Exclude guide ID, compilation and
  ContributionPolicy references rather than inventing observations. ORM and detached inputs are adaptations to that same fact shape,
  not alternative implementations. Remove the obsolete PaymentPolicy requirement.
  Do not claim compilation/ContributionPolicy task locks exist before their
  persistence owners implement them. The full guide-activation requirements remain
  normative and unavailable until their remaining owners supply the evidence.

- CHECKERS public catalogue owns the single immutable metadata factory; its
  registry validates installation against that metadata. PROJECTS consumes only
  that public value and removes its private runner import.
- Use schema identifiers `post_submit_checker_policy`,
  `post_submission_checker_capability_projection`, compiler identity
  `workstream-post-submit-compiler`, implementation identity
  `workstream-structural`, and single capability/source identity `v0.1`.
  These identify the current contract, never select alternate readers.
- Parsed entries are canonical custody for derived checker lists. Existing policy
  required/warning/blocking sidecars must equal those derived values at setup
  continuation, activation, task lock/read, submission validation and execution.
  Independently crossed sidecars must fail before writes or execution.
- Mandatory platform defaults cannot be reclassified. Project additions use the
  catalogue's selectable entries; project blocking severities can strengthen the
  platform floor. Remove redundant fixture selections of mandatory defaults.

Additional allowed dependent application paths: `checkers/service.py`, `tasks/service.py`, and
`projects/service.py` for canonical policy parsing/derived lists and context
adaptation; `projects/guide_compilation/context.py` and `orchestrator.py` only if
the single projection type requires annotation correction. This correction adds
no database columns; policy bodies are JSON. Retained development data is not deleted or rewritten. Unsupported bodies reject;
new setup generations use the current contract. Code cleanup grants no data-deletion
authority and introduces no compatibility reader or migration bridge.

Additional traced caller: `adapters/project_agents/openai_agent_sdk.py` must
prohibit repeating mandatory defaults in project selections; its current prompt
otherwise contradicts the consolidated compiler. POL `planning/CHUNK_MAP.md`
must match the scoped cleanup rule and the adopted POL-04B deletion boundary.

Allowed dependent tests: the nine `tests/checkers/post_submit/test_*.py` modules and their
`support.py`; `tests/test_checkers.py`, `test_projects.py`, `test_tasks.py`,
`test_project_guide_compilation_contracts.py`, `test_agent_runtime.py`,
`tests/projects/post_submit_fixtures.py`, `diagnostic_read_fixtures.py`,
`test_activation_readiness.py`, `test_diagnostic_read_composition.py`,
`test_diagnostic_read_rejections.py`, and `guide_compilation/helpers.py`,
`test_context_builder.py`, `test_hidden_orchestrator_postgresql.py`,
`test_projection_service.py`, `finalization/pg_prerequisites.py`; authorization
compilation adapter fixtures only where catalogue identity changes. Inspect
additional callers found by symbol search before editing them; no bulk removal
of unrelated tests or assertions.

## Acceptance criteria

- Exactly one supported post-submit catalogue/projection and compiled policy
  representation; every consumer uses it.
- Exactly one registered implementation per checker; no old/new dispatch routes.
- Obsolete imports, symbols, schema branches and preservation-only tests removed.
- Required context and policy hashes remain validated against exact current facts.
- No runtime fallback for unsupported input; no weakening of database/AUTH guards.
- Existing domain policy versioning and pre/post phase separation remain intact.

## Risk and review routing

Risk: L1; architecture/reuse and security plan review precede implementation.
Implementation reviews: architecture/reuse, security, QA/test delta,
documentation/product operations; CI integrity if test ownership is affected.
Human focus: complete consolidation, no disguised compatibility path, and honest
remaining integration dependencies.

Required negative proof includes old sparse bodies with recomputed hashes, each
current context field independently absent/crossed, each sidecar independently
crossed, obsolete/future context fields rejected as extras, and complete current
facts without PaymentPolicy passing. Owner lineage/AUTH checks remain authoritative;
coherent checker values alone grant no authority.

## Evidence

Focused checks run locally. Full PostgreSQL/concurrency/backend coverage remains
hosted. Run boundary, stale wording and link checks, discriminating invalid-input
and missing-lineage tests, then wait for final-head CI and internal reviews.
No correction is complete merely because old identifiers have been renamed.

## Explicit documentation and verification scope

Allowed documentation: `docs/architecture_data_model.md`, `docs/roadmap_status.md`, `docs/architecture_checker_framework.md`,
current checker policy template/spec, `.commitrail/INDEX.md`, `AGENTS.md`,
ARCH-001 overview/ARCH-04A record/chunk map, POL-003 overview and downstream
POL-04B contract where they require superseded preservation. No unrelated roadmap
capability may be declared delivered. Conditional test-lane/behavior ownership
files may change only if an owned test file is actually added, renamed or deleted;
no removal of required checks or thresholds.

Commands: from backend, `.venv/bin/ruff check app tests scripts`, focused
`.venv/bin/python -m pytest tests/checkers/post_submit -q`, and pure affected
compiler/context tests; `.venv/bin/python -m scripts.module_boundaries validate
--protected-base ade2edc16368ef0c81a084f28342df39aac124a1`,
`.venv/bin/python -m scripts.authorization_boundary validate --ledger
../.ci/auth-boundaries/IMPORT_LEDGER.md`, plus test-structure and behavior-ownership
validators. Root checks: `.venv/bin/python scripts/check_markdown_links.py`,
`.venv/bin/python scripts/check_stale_workstream_wording.py`, and
`.venv/bin/python scripts/check_commitrail_records.py --base-ref origin/main`.
Hosted backend suite supplies PostgreSQL/lifecycle coverage for the named owners;
record exact commands, nodes and results against the implementation candidate.

Allowed boundary bookkeeping: remove the resolved PROJECTS post-submit compiler
and service private CHECKERS runner edges from `.ci/module-boundaries/private-edge-debt.v1.json`;
this removes debt and permits no replacement private edge.

## Locked severity semantics

The registered placeholder detector still emits raw warning/medium. Mandatory
entries cannot be selected again as project-required entries. Policy application
escalates a warning when its original severity is in the validated locked blocking
severities, or a selectable checker is explicitly required. It records the actual
escalation reason, persists failed/high, and requires revision. Default critical/
high leaves the medium warning advisory. This preserves stricter project intent
through one canonical policy, with no handler alternative or default reclassification.
Adjusted routing outcomes do not masquerade as raw catalogue-conformance results.
Security/QA feasibility review confirmed this bounded policy correction; test the
raw/default/explicit-medium controls and mutation removing severity escalation.

The structural-debt inventory updates only observed positions/hash and reduced
size for the touched PROJECTS test owner in `.ci/auth-boundaries/TEST_STRUCTURE_DEBT.json`;
no new debt, exceptions, limits or test-selection changes are allowed.

## Intended delivered boundary

The correction replaces both development representations with one rich catalogue,
one compiled policy and parser, and one ID-keyed registration per checker.
PROJECTS no longer imports the private CHECKERS runner. Active consumers derive
execution lists from canonical entries and validate stored summary equality.
Current context uses actual task/submission locks, with no fabricated future facts.

Preservation-only hash/alternate-handler tests are removed. Their replacements
prove canonical round trips, unsupported sparse-body rejection even with recomputed
hashes, each current context omission/cross, exact catalogue/configuration identity,
sidecar custody before execution, and policy-driven warning escalation. No test
lane, skip policy, coverage threshold, workflow or dependency is relaxed.

POL-04B remains the next independently bounded change. This correction does not
activate unified setup, durable public phase execution, acceptance or compensation.
No local roadmap spreadsheet exports are present. Current navigation and normative
checker/data-model documentation describe the intended merged contract.

## Correction of the earlier delivery

PR #389 supplied the public catalogue and bounded phase contracts but retained
alternate development representations. This record now describes the corrected
scoped implementation; the earlier hash/handler preservation requirements are
withdrawn. Its former reviews prove only that earlier target, not this correction.

## Review-driven regression corrections

Affected caller instructions now prohibit repeating platform defaults in project
selections. All summary consumers use the canonical validator, and worker-facing
severity escalation describes a blocking finding without claiming required
classification. The sparse-projection type branch is removed.

Obsolete success-after-sidecar-corruption tests are replaced by release, submission
and manual-checker denial tests with durable side-effect assertions. An idempotent
finalize request no longer stands in for execution proof. Real PROJECTS fixtures
exercise independently crossed summaries before approval, correction and activation.
Queued invalid-policy execution stays submitted until validation succeeds. The
constant-default-drift preservation test is removed; canonical lock integrity
remains covered. Current POL navigation assigns physical inference replacement to
POL-04B and imposes no separate cleanup prerequisite.

The checker-denial snapshot includes mutable existing-run status, current-run
flag, failure details and timestamps as well as row identity/routing. Denial
proof must catch mutation of retained runs, not only newly inserted rows.

Traced shared fixture consumer `tests/projects/review_policy/test_activation.py`
now uses the canonical post-submit compiler/parser supplied by its existing
readiness fixture. Its obsolete sparse-parser mock is removed; review-policy
semantics and required human-review/automated-acceptance guards stay covered.

The aggregate API-contract drill is another traced compiler consumer:
`backend/scripts/api_contract_e2e.py` now seeds no project additions by default
and serializes blocking severities as a list. It uses the same canonical compiler;
no E2E assertion, database-isolation check or CI step is removed. Its existing
`backend/tests/test_api_contract_e2e.py` owner covers omitted/empty additions, a
selectable addition, and rejection of explicit default reclassification before
any fixture write. The focused regression failed before the fixture correction.

Shared helper caller `backend/scripts/week2_api_e2e.py` expresses its low-quality
revision scenario through a locked medium-severity floor, not reclassification
of the mandatory default. Its routing, failed/high result and revision assertions
remain intact. API-drill fixture proof covers both default and explicit-medium
floors. No historical script-only compatibility selection remains.
