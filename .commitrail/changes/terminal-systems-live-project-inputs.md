# Terminal Systems — contributor-ready project inputs

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Make the original Terminal Systems guide and initial task briefs precise enough for a real setup run without prescribing its checker implementation.

## Intent

Prepare the actual project material a PM will upload, so setup derives required
checks from the work rather than from a prebuilt checker or a fixed task list.
Use general task-authoring concepts only; no private third-party prose, tasks,
code, identifiers, datasets or operational details enter the project materials.

## Current behavior

`pilots/terminal_systems/` already contains original project inputs. The guide
leaves metadata conventions unspecified and four import briefs have little
detail. Merged PR #647 supplies the generic image build/test/ECR command; it does
not implement this project's checks or prove a live project journey.

## Bounded change

### Allowed

- `pilots/terminal_systems/`: refine contributor requirements; define project
  metadata; expand five independently authored briefs into readable documents;
  keep public guide/import inputs synchronized; explain actual onboarding.
- `docs/roadmap_status.md`: reconcile the input-preparation boundary.
- This record.

### Not allowed

- No copied private reference material, renamed private task, bundled solution,
  credential, third-party dataset or private operational detail.
- No backend, Rust, schema, migration, checker implementation or CI change.
- No hardcoded task allowlist, approved checker binding, invented setup output,
  live model call, project mutation, deployment or image publication.
- No policy defaults or pre/post assignments in the contributor guide.

## Design and decisions

Keep one project input directory. Separate contributor requirements from the PM
onboarding notes. Metadata conventions belong to this project, not Workstream's
generic runtime. The five briefs are an initial workload, not supported-task
constraints. Setup must still discover required capabilities and engineering
must prove their implementation before activation.

## Acceptance criteria

- [x] A new author can distinguish their deliverable from the later solver's work.
- [x] Guide metadata, packaging, environment, reference and verification requirements are explicit without selecting a language or checker.
- [x] Five distinct original briefs describe work, observable behavior and meaningful failure cases; the readable and import versions match exactly.
- [x] Guide creation and task import JSON validate against current public schemas; the standalone example matches the creation input.
- [x] No private names, links, task content or copied prose enter the changed assets.
- [x] Onboarding preserves real inference, missing-capability discovery, image qualification, separate approvals and activation; no live result is claimed.

## Risk and review routing

- Risk class: L2
- Required reviewers: documentation and product/operations, one bounded combined review.
- Human review focus: project requirements and task usefulness before a live setup run.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Usable inputs | Public Pydantic guide schema, task-import parser, TOML parse and exact document comparison | Passed; all five briefs and the uploaded example match their readable sources, and the uploaded guide contains the metadata example | Does not execute setup or any checker |
| Independent content | Private-marker scan and normalized 14-word phrase comparison against the local reference; authored-task inspection | No private markers or shared 14-word phrases found; existing original subjects expanded independently | Local comparison is not an exhaustive external originality search |
| Coherent onboarding | Markdown and Commitrail checks plus scoped documentation/product review | Links and diff checks passed; review must bind to the committed candidate before readiness | Live inference and project execution remain separate work |

## Review findings

The metadata example is embedded in the uploadable guide as well as supplied as
a local TOML file, so the contributor document does not depend on a repository
relative attachment. The onboarding notes preserve the execution-host cache step
and distinguish image publication from registration, approval and activation.
Scoped documentation/product review also replaced the misleading instruction to
rerun a finalized setup run with the actual public choices: a PM correction
successor with explicit dispatch, or a new guide version. The same correction is
reflected in the capability ledger.

## Reconciliation

- Current-source reconciliation: main `b1da3f8eb`, including merged #647. Preserve project-neutral Rust and the existing public onboarding owners.
- Next usable boundary: PM review, actual guide upload and inference, then engineering implementation of uncovered requirements.
- Remaining risks: offline image building, semantic judgments and runtime qualification must be assessed by real setup; these documents do not deliver those capabilities.
