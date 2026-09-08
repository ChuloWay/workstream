# Chunk Contract: WS-POL-003-07 - Single Checker Service Port

Disposition: Planned. Dependencies: 06B, ARCH-04A capability contracts,
and merged ART-04B1-04B3. Risk: L1.

## Goal

Provide one internal typed checker service port with exactly two complete
phase commands:

- `evaluate_pre_submission(...)`, one logical attempt initiated by artifact-flow
  orchestration while exact material is sealed in `ArtifactScratchManager`
  custody;
- `evaluate_post_submission(...)`, one logical attempt initiated by
  artifact-flow orchestration after exact verified content is durably stored,
  bound, and attached to the Submission lineage.

Each command invokes the complete canonical phase executor and returns one
typed result. The pre command is a facade over ART-04B1-04B3's existing
effective-plan execution; it does not reimplement or rerun ART entries. The
post command delegates through the CHECKER-owned execution contract; ARCH-04C
later supplies its canonical current-result persistence implementation.
Artifact-flow callers never
select or call individual platform/project checkers.

## Allowed files

Checker interfaces/service/composition, project policy plan adapters, typed ART
material/result interfaces only, focused checker/project tests, and WS-POL-003
docs.

## Not allowed

ART scratch/storage/provider/binding/lifecycle changes, public contributor
checker routes, caller-selected checker names, per-checker endpoints, dynamic
plugins, arbitrary code/network execution, or prepared handles in payloads.

## Acceptance

- The service exposes exactly one pre and one post command and no generic
  `run_checker(name, ...)` product boundary.
- Pre composes mandatory ART platform entries with exact task-locked project
  pre-submit entries through ART-04B1-04B3 and evaluates them once against one
  sealed scratch generation.
- Post composes durable defaults with exact task-locked project post-submit
  entries and evaluates them against one verified stored/bound content lineage.
- Both commands bind exact project/task/assignment, guide/policy, artifact,
  compilation/result/component/catalogue hashes, manifest, generation,
  attempt, action, service identity, and transaction
  facts; stale/replay/cross-phase/cross-resource calls fail closed.
- The port requires a deterministic attempt identity. Bounded retry/repair may
  call the command again for that same logical attempt, but replay returns the
  existing canonical result without rerunning completed members. This is an
  executor contract, not a claim that 07 installs durable post-submit storage.
  A genuinely
  new evaluation requires a new attempt identity; this chunk does not alter or
  claim the external call sites.
- ART's existing attempt/result/evidence repository is the only pre writer.
  ARCH-04C alone owns post-submit attempts, result/currentness persistence and
  worker recovery; 07 neither creates those tables nor proves their execution.
  The facade returns canonical references without writing competing evidence.
  Its production post command stays unavailable until ARCH-04C/04D, while
  registered evaluator/plan contract tests use controlled material fixtures.
- Guide activation may verify that every selected checker has a compatible
  registered implementation and valid bounded configuration. It never requires
  an actual Task, Submission, completed run, or live post-submit AUTH gate;
  those are downstream. Successful invocation of a fake is not implementation
  coverage; use ARCH-04A's real evaluator fixtures for the supported catalogue.
- One bounded phase result contains every platform/project member with exact
  definition/version/policy trace; infrastructure failure is never contributor
  blame or a review decision.

## Verification and review

All-pairs phase/identity/resource denial, exact-once composition, no-individual-
dispatch reachability, timeout/cancellation, deterministic attempt replay,
scratch and stored-content contract parity, and 90% changed-subsystem coverage.
Required reviewers: architecture, security, QA, reuse/dedup. Human focus: the port permits one complete
call per phase and cannot select individual checkers.
