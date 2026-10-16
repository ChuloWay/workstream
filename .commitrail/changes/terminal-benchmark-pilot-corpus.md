# Terminal benchmark pilot — real project inputs and reference corpus

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: A shareable project guide, five task-authoring briefs and independently checkable reference/negative packages provide concrete inputs for #493 and the first automated hosted pilot #555.

## Intent

Deliver #576 without waiting for hosted deployment or rebuilding the contribution
lifecycle. Contributors author terminal benchmark tasks: environment, instructions,
tests and reference solution. The first project validates bounded mechanical
properties; it makes no automatic difficulty, novelty, leakage or substantive
quality claim. Project-manager approvals remain required in Workstream.

## Current behavior

The public setup/task/intake/outcome owners exist on main `34501cd64`.
`experiments/pilot04_external_checker_runtime/` proves the connected runtime with
recorded inference and filename-based project failures. The separate
`experiments/pilot00_gvisor_offline/` proves a small offline build/oracle mechanism.
Neither supplies the real project guide and task-authoring corpus in #576.

## Bounded change

### Allowed

- `pilots/terminal_benchmark/README.md`, `guide.md`, `guide-request.json`,
  `tasks.json`, `corpus.json` and `verify_corpus.py`: project inputs, public import
  shape, ground truth, and a trusted checked-in-corpus verifier.
- `pilots/terminal_benchmark/packages/**`: five independently understandable
  original sample benchmark packages, each with task metadata, instruction,
  digest-pinned environment, starting work, tests and reference solution.
- `pilots/terminal_benchmark/negative-cases.json`: exact semantic/package
  mutations and expected boundaries, without duplicating entire packages.
- `docs/roadmap_status.md`: only affected pilot input capability and trace link;
  no hosted/runtime completion claim.
- This change record for intent, evidence, independent review and reconciliation.

### Not allowed

- Product API, policy compiler, authorization, storage, checker/runner or CI
  changes; #493 owns actual sandbox evaluator integration.
- Private prior-project documents, externally copied tasks, secrets or binaries.
- Automatic policy approval, registration, guide activation or deployment.
- Generic benchmark runner/framework, arbitrary uploaded-code execution on host,
  hidden product-row seeding, parallel compatibility paths or model judging.

## Design and decisions

Use Python standard-library terminal repair exercises to keep the first corpus
offline, inspectable and inexpensive to reproduce. Five distinct tasks cover
ledger aggregation, timestamped event rollup, transactional import, deterministic
file inventory and configuration merge. Each task has independent expected
examples/assertions, a genuinely broken starting program and a correct reference.
Tests reject the unchanged starter and accept the reference across repeat runs.
The Dockerfile copies only starting workspace material; reference solutions and
tests stay outside the task image and are provided separately by the evaluator.
Candidate evaluation never receives `solution/`. Trusted reference calibration
overlays it only in a separate temporary copy; the evaluator injects tests
separately. Each package has `task.toml`, `instruction.md`,
`environment/Dockerfile`, `workspace/program.py`, `solution/program.py`, and
`tests/` containing independent golden cases and assertions.
`tasks.json` alone owns native TaskImportDocument fields. `task.toml` and
`corpus.json` own package mapping, commands and corpus hashes; their shared
`external_task_id` must equal the corresponding native import row exactly.
Reuse the repository's digest-pinned CPython base as the explicit project base;
record that its approved offline cache/platform digest must be prepared by #493.

The verifier executes only these reviewed repository assets in temporary
workspaces using local Python; it never accepts uploaded ZIP/code or claims to
provide sandbox isolation. It records corpus hashes and observed reference/no-op
outcomes. The project Docker build and genuine gVisor execution remain #493
proof. Local negative cases prove malformed package metadata, wrong reference
logic and ineffective tests. Actual Docker build failures, approved base-cache
availability, platform compatibility and gVisor execution belong to #493 and
must not be reported as locally verified. Each task also names a plausible
near-miss solution rejected by independent golden assertions. A nondeterminism
example cannot be claimed to fail every sample;
record this limit instead of retry-until-green.

Guide request includes at least one meaningful task example. Native task-import
JSON uses title/description and optional criteria according to the current owner
schema; briefs are not auto-created tasks. Proposed first drill policies are
explicit `human_review_required=false`, second-review false, a project-controlled
revision allowance and an independently published ContributionPolicy. These
assets do not grant authority or assert that proposed requirements are registered.
`guide-request.json` contains only current `ProjectGuideCreate` fields. Proposed
ReviewPolicy, RevisionPolicy and ContributionPolicy values remain documented
handoff intent requiring separate authorized manager or Finance operations.

## Acceptance criteria

- [x] Five real task-authoring briefs and a self-contained guide explain package
  layout, mechanical acceptance, offline requirements and omitted quality claims.
- [x] Guide/task JSON matches current public request/import shapes, with no
  invented required task-local criteria or identity selectors.
- [x] Five positive reference packages have independently reviewed expected
  outputs; local execution passes their assertions while unchanged starters fail.
- [x] Repeatability, corpus hashes and locally supported negative mutations are
  reproducible without network, provider secrets or product database access.
- [x] Every claimed observed result is distinguished from future sandbox/build,
  live-inference, manager-approval and hosted-runtime proof.
- [x] #493 receives an unambiguous package/configuration contract and #555 receives
  the same versioned corpus for real public integration, without closure cycles.

## Risk and review routing

- Risk class: L1 (project acceptance contract and executable sample work; no
  product authority/runtime change).
- Required reviewers: product_ops/documentation for project scope and downstream
  integration; QA/test_delta for independently justified expected outcomes and
  real no-op/incorrect-solution detection; security for sample execution boundary.
- Human review focus: agreement with the proposed mechanical project scope and
  example complexity; no implicit approval or promise of general benchmark quality.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing owners and schema | Read current setup/task-import contracts and pilot proofs | Inspected | Public runtime not rerun by this asset change |
| Corpus correctness | `python3 pilots/terminal_benchmark/verify_corpus.py` | Five references each pass three runs; all five starters and named near-miss mutations reject; malformed package and ineffective-test probes distinguish the intended boundary | Local trusted-code execution only |
| Public input shapes | Validate `guide-request.json` with `ProjectGuideCreate` and `tasks.json` with `TaskImportDocument` from current backend | One declared Markdown guide, five examples and five native tasks validate | No product API invoked or authority granted |
| Executable asset lint | Ruff over `pilots/terminal_benchmark` | Passed | Full current-head hosted checks remain required |
| Scope/links/current docs | Repository link checks, diff check, focused reviewer inspection | Passed | Full current-head CI remains required |

## Review findings

Independent plan review corrected fixed-file ownership, candidate/reference
isolation, public guide fields and native-versus-sandbox proof boundaries before
authoring. Expected outputs must be checked independently; deriving assertions
from the reference implementation is not proof. Implementation review must
inspect the independently authored goldens and their named near-miss probes.
Implementation review independently matched all five packages' golden results.
It corrected an overstatement of connected-journey proof, added the explicit
PRE/POST/infrastructure outcome matrix, and removed an invalid build-negative
claim: fixed-recipe validation would reject that mutation before Docker. Actual
build/cache/platform proof remains with #493. These assets do not complete #576's
manager agreement or #555's hosted release evidence.

## Reconciliation

- Current-source reconciliation: PILOT-08 is merged. #575/#577 result/read work,
  #585 CI and #586 README remain separately owned. No edits to those paths.
- Next usable boundary: #493 real checker execution; #580 supported registration;
  #555 public live-inference/local and hosted journey proof.
- Remaining risks: Proposed guide still requires manager approval; local Python
  results do not establish Docker, gVisor, AWS or full Workstream readiness.
