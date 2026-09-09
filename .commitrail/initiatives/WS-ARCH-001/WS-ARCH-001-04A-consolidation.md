# ARCH-04A consolidation — One initial v0.1 checker contract

- Initiative: WS-ARCH-001
- Durable disposition: Planned
- Intended merge outcome: remove superseded post-submission catalogue, compiler,
  parser, registry, and projection branches retained or introduced by ARCH-04A;
  use one canonical initial-v0.1 contract throughout its consumers.

## Human intent

Workstream has no released software contract requiring backward compatibility.
The human explicitly rejects legacy code, fallback behavior, and parallel
internal v1/v2 implementations. Earlier assumptions that development hashes and
schemas must remain executable are withdrawn. Obsolete implementations must be
deleted, not renamed, aliased, or disabled for deferred cleanup.

POL-04B is not the next implementation boundary until this correction is complete.
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

## Plan and boundaries

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
  locked facts. ORM and detached inputs are adaptations to that same fact shape,
  not alternative implementations. Remove the obsolete PaymentPolicy requirement.
  Do not claim compilation/ContributionPolicy task locks exist before their
  persistence owners implement them. The full guide-activation requirements remain
  normative and unavailable until their remaining owners supply the evidence.

Dependent application paths: `checkers/service.py`, `tasks/service.py`, and
`projects/service.py` for canonical policy parsing/derived lists and context
adaptation; `projects/guide_compilation/context.py` and `orchestrator.py` only if
the single projection type requires annotation correction. This correction adds
no database columns; policy bodies are JSON. Earlier development data requires
a clean baseline, not a compatibility reader or migration bridge.

Dependent tests: the nine `tests/checkers/post_submit/test_*.py` modules and their
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

## Acceptance and review

- Exactly one supported post-submit catalogue/projection and compiled policy
  representation; every consumer uses it.
- Exactly one registered implementation per checker; no old/new dispatch routes.
- Obsolete imports, symbols, schema branches and preservation-only tests removed.
- Required context and policy hashes remain validated against exact current facts.
- No runtime fallback for unsupported input; no weakening of database/AUTH guards.
- Existing domain policy versioning and pre/post phase separation remain intact.

Risk: L1; architecture/reuse and security plan review precede implementation.
Implementation reviews: architecture/reuse, security, QA/test delta,
documentation/product operations; CI integrity if test ownership is affected.
Human focus: complete consolidation, no disguised compatibility path, and honest
remaining integration dependencies.

Focused checks run locally. Full PostgreSQL/concurrency/backend coverage remains
hosted. Run boundary, stale wording and link checks, discriminating invalid-input
and missing-lineage tests, then wait for final-head CI and internal reviews.
No correction is complete merely because old identifiers have been renamed.
