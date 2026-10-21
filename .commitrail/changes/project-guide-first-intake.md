# Project guide first — terminal systems authoring inputs

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Remove the fixed-project pilot implementation and supply original guide/example/task inputs for genuine setup-driven onboarding.

## Intent

The PM supplies project requirements and illustrative work. Setup must derive
enforcement proposals from those inputs, expose missing capabilities and obtain
approval; a guide must not be rewritten to fit an existing test fixture.

## Current behavior

Before this change, `pilots/terminal_benchmark/guide.md` combined contributor requirements with PRE,
POST, registry, lifecycle and policy instructions. The corresponding Rust checker
accepted five exact task IDs, eight fixed files and one fixed Python recipe.
That bounded corpus proved its own implementation, not arbitrary project setup.

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

- [x] A PM can read the guide and example without Workstream implementation knowledge.
- [x] Five meaningful task-authoring briefs and guide inputs validate against
  current public schemas; task-local acceptance/rejection fields remain optional.
- [x] Neither examples nor guide impose a fixed task inventory, language, single
  source file, image digest or private provider dependency.
- [x] Onboarding notes distinguish setup suggestions, engineering implementation,
  registry, fresh proposal/approval, activation and task screening/release.
- [x] Required unsupported checks remain visible and block activation; existing
  sample checker proof is not presented as support for this guide.
- [x] No fixed five-task checker, private plan protocol, named runtime profile or sample-only proof remains active; ordinary Backend lanes and release-image triggers remain intact.
- [x] Generic Rust and Python materialization/runtime tests retain exact custody, cleanup, resource and result-contract protections.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, security, QA/test_delta, CI integrity and documentation/product_ops, grouped into bounded independent reviews.
- Human review focus: contributor requirements, breadth of the five briefs and
  the distinction between prepared inputs and a runnable approved project.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Public input shape | ProjectGuideCreate and parse_task_import on checked-in JSON | Guide/example and five distinct briefs validate; optional criteria omitted | No live setup inference |
| Retained runtime protections | `cargo test --workspace --locked --offline`; Python external-runtime and artifact-preparation selection | 28 Rust and 105 Python tests pass; removed configuration rejects, generic result handling and cleanup remain | No live project journey |
| POST materialization and quotas | Owned PostgreSQL runner: native POST grant/lease test and aggregate-quota test | Both pass; database cleanup confirmed | Broad local module run hit its 900-second limit with incomplete failure output and is not passing evidence; full module remains part of required CI |
| Provider custody | Owned PostgreSQL/MinIO runner: exact materialization readback and revocation | Pass; owned database and bucket cleanup confirmed | Local MinIO, not a hosted storage deployment |
| Documentation and boundaries | Markdown links, stale wording, diff, module/test boundaries, Commitrail validation and focused review | Pass; stale catalogue and upload-trigger wording corrected | No checker implementation or product activation |

Runtime proofs bind to source candidate `17390e92`; the final change to this
record only reconciles evidence and intended disposition. The initial broad
database invocation omitted the MinIO endpoint and timed out; its partial output
does not establish a module result. The separate successful storage invocation
configured the endpoint and redirected the existing test helper to the runner's
owned bucket without changing product code. Exact-head hosted results and review
freshness belong to the PR, not this durable record.

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
document upload queues setup automatically. The final record removes superseded
intermediate test counts and transient review wording and records the integrated
main boundary.

## Reconciliation

- Current-source reconciliation: main `c6d916cc1`; task audit and Operator task CLI are merged and
  do not change these input contracts. #576/#555 remain the project preparation
  and connected journey owners.
- Next usable boundary: PM review of the guide and illustrative work, then live
  setup against the registry and explicit engineering handoff for missing checks.
- Remaining risks: the broader project requirements still need setup-derived image implementation. No difficulty, quality, isolation or hosted outcome
  is certified by these assets.
