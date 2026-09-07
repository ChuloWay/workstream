# Checker stage and evaluation semantics

- Initiative: None

- Durable disposition: Complete
- Intended merge outcome: separate checker stages and remove blanket deterministic-evaluation claims from current entry documentation.

## Intent

Correct the blanket description of all Workstream checking as deterministic.
Separate pre-submission intake quality from post-submission work evaluation
without claiming unimplemented evaluators are live.

## Bounded change

Allowed files: this record, `README.md`, `AGENTS.md`,
`docs/product_brief.md`, `docs/glossary.md`,
`docs/architecture_system_architecture.md`, `docs/architecture_lockdown.md`,
`docs/architecture_checker_framework.md`, `docs/decision_0001_core_scope.md`,
`docs/roadmap_status.md`, `docs/product_principles.md`,
`docs/diagrams/task_lifecycle_sequence.md`, and the architecture brief's
`workstream_architecture_brief.md`, generated PDF, `task_lifecycle_sequence.puml`,
and generated `images/task_lifecycle_sequence.png` under
`docs/architecture_brief/`.

Update current definitions and lifecycle explanations together. Preserve
deterministic compilation, hashing, intake primitives, and policy routing
claims where they describe those specific operations.
No runtime, API, policy authority, checker registration, release scope, tests,
CI, historical archive, or unrelated setup migration changes.

## Acceptance criteria

- Current product definitions do not label all checking deterministic.
- Intake precedes Submission creation; work evaluation follows it. Their
  evidence and outcomes are not interchangeable.
- Explain deterministic mechanics versus model-based evaluation, without
  promising identical model judgments or activating a new checker.
- Setup policy derivation is not runtime task evaluation; only supported
  registered implementations execute. Authorized Review retains final decisions.
- Roadmap wording agrees; preserve merged capability status and remaining work.

## Risk and review routing

L2 documentation clarification; no architecture direction or runtime changes.
Paired documentation and product/operations review, focused on stage ordering,
evaluation claims, and current-versus-target behavior. Human focus: useful
checker descriptions without false reproducibility or availability promises.

## Evidence

Verify Markdown links, stale wording, current authorization/artifact/review
documentation checks, Commitrail record validity, and diff hygiene. Inspect
remaining deterministic mentions individually rather than global replacement.
No local spreadsheet exports are present. No runtime test changes are needed
for this documentation-only correction; hosted checks remain independent.
