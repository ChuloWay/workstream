# Project guide first — terminal systems authoring inputs

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Remove the fixed-project pilot implementation and supply original guide/example/task inputs for genuine setup-driven onboarding.

## Intent

The PM supplies project requirements and illustrative work. Setup must derive
enforcement proposals from those inputs, expose missing capabilities and obtain
approval; a guide must not be rewritten to fit an existing test fixture.

## Current behavior

`pilots/terminal_benchmark/guide.md` combines contributor requirements with PRE,
POST, registry, lifecycle and policy instructions. The corresponding Rust checker
accepts five exact task IDs, eight fixed files and one fixed Python recipe.
That bounded corpus proves its own implementation, not arbitrary project setup.

## Bounded change

### Allowed

- `pilots/terminal_systems/`: original contributor guide, illustrative task,
  guide-creation request, five native import briefs and separate onboarding notes.
- Remove `pilots/terminal_benchmark/`,
  `experiments/terminal_benchmark_project_checkers/`, its dedicated workflow and
  `external_checkers/workstream-terminal-benchmark-checker/`.
- `external_checkers/README.md`, `Cargo.toml`, `Cargo.lock`, SDK and service: remove the
  project-specific plan, execution profile, continuation and their exclusive tests.
- ART preparation and POST materialization: remove the named capability branch,
  its scratch expansion, and now-unused request fields. Preserve ordinary
  manifest custody, quotas, reservations, cleanup and callback ordering.
- The two affected backend external-runtime/materialization test modules:
  remove obsolete named-profile assertions while retaining general protections.
- Affected checker architecture, glossary, roadmap, direct fixture-navigation documents
  and required test-inventory metadata: reconcile with the retired behavior.
- This change record.

### Not allowed

No migration, registry mutation, policy approval, activation, deployment,
provider calls or live task creation. Do not copy third-party guide prose,
documents, identifiers or private assets. No removal of generic authorization,
request/result identity, sandbox, quota, cleanup, outbox or concurrency proof.
Do not weaken required Backend or Agent Gates checks or introduce another runtime.
Preserve stored registry, policy, submission and evidence records; source removal
must not rewrite their history. No fallback for the retired execution profile.

## Design and decisions

The user's explicit correction retires the five-task sample as the pilot and
rejects task-ID allowlists and project-specific branches in the shared runtime.
Remove that whole implementation and its exclusive proof, rather than merely
renaming its identifiers or maintaining two pilot paths. The generic external
image request/result contract and sandbox execution remain authoritative.

Keep human project input under `pilots/terminal_systems/`. Its guide defines
work requirements without PRE/POST bindings or policy defaults. A separate README
explains public onboarding and the engineering handoff. The five initial briefs
are a batch of work to author, not completed packages or eligibility restrictions.
Missing execution capabilities remain explicit blockers for the real setup run;
retirement does not claim that arbitrary nested builds already work.

## Acceptance criteria

- [ ] A PM can read the guide and example without Workstream implementation knowledge.
- [ ] Five meaningful task-authoring briefs and guide inputs validate against
  current public schemas; task-local acceptance/rejection fields remain optional.
- [ ] Neither examples nor guide impose a fixed task inventory, language, single
  source file, image digest or private provider dependency.
- [ ] Onboarding notes distinguish setup suggestions, engineering implementation,
  registry, fresh proposal/approval, activation and task screening/release.
- [ ] Required unsupported checks remain visible and block activation; existing
  sample checker proof is not presented as support for this guide.
- [ ] No fixed five-task checker, private plan protocol, named runtime profile or sample-only proof remains active; ordinary Backend lanes and release-image triggers remain intact.
- [ ] Generic Rust and Python materialization/runtime tests retain exact custody, cleanup, resource and result-contract protections.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, security, QA/test_delta, CI integrity and documentation/product_ops, grouped into bounded independent reviews.
- Human review focus: contributor requirements, breadth of the five briefs and
  the distinction between prepared inputs and a runnable approved project.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Public input shape | ProjectGuideCreate and parse_task_import on checked-in JSON | Guide/example and five distinct briefs validate; optional criteria omitted | No live setup inference |
| Retained runtime protections | Rust workspace; Python external-runtime and artifact-preparation selection | Initial Rust 26 tests and Python 105 tests pass; final boundary regression and PostgreSQL selection follow | No live project journey |
| Documentation coherence | Links, stale wording, diff, focused review | Pending | No checker implementation or product activation |

## Review findings

Read-only architecture/test-delta scope review found the retirement coherent.
It required preserving generic aggregate quota and mixed POST lineage tests,
reconciling the PRE scoreboard row, and adding a service-level invalid-result
control that proves a project-private output cannot launch a continuation. Those
items are included. Implementation review also required a discriminating
configuration-parser regression: the retired profile key, including a null value,
must reject while the generic configuration shape remains accepted. The generic
private-output test protects result handling but is not presented as a test that
failed the old POST-only continuation. Documentation review corrected the glossary's
superseded catalogue definition and the onboarding trigger: the final declared
document upload queues setup automatically. Clean-target replay remains required.

## Reconciliation

- Current-source reconciliation: main `4ad0812e0`; task audit CLI is merged and
  does not change these input contracts. #576/#555 remain the project preparation
  and connected journey owners.
- Next usable boundary: PM review of the guide and illustrative work, then live
  setup against the registry and explicit engineering handoff for missing checks.
- Remaining risks: the broader project requirements still need setup-derived image implementation. No difficulty, quality, isolation or hosted outcome
  is certified by these assets.
