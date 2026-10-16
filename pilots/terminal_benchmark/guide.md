# Terminal benchmark authoring pilot — project guide

## Purpose and scope

Author small, reproducible terminal repair tasks. A benchmark task contains an
instruction, a container environment with a broken starting program, independent
correctness tests and a working reference solution. Workstream contributors
create these benchmark packages; the future solver runs the task inside the
package. These are different roles.

This original, shareable pilot exercises the complete governed contribution
journey. It checks bounded mechanical properties. It does not certify task
novelty, difficulty, absence of solution leakage, or general semantic quality.
No private contributor material or external benchmark dataset belongs here.

## Required submission

Submit one ZIP with package files at its root, without an enclosing directory:

- `task.toml`: the exact external task ID and execution/build metadata.
- `instruction.md`: clear solver instructions, input/output rules and edge cases.
- `environment/Dockerfile`: the approved digest-pinned CPython environment.
- `.dockerignore`: exclude `solution/` and `tests/` from the image build context.
- `workspace/program.py`: a genuinely defective starting implementation.
- `solution/program.py`: the correct reference implementation for calibration.
- `tests/test_task.py` and `tests/cases.json`: independent black-box assertions.

Use UTF-8 text and regular files only. No links, encrypted members, parent-path
traversal, absolute archive paths, executables fetched at build/runtime, embedded
credentials, or external network requirements. Workstream enforces its governed
archive size, file-count and expansion bounds before project checks. The approved
policy supplies the exact limits; this guide does not override those limits.

## Fixed pilot environment

Use this exact base:

`python:3.12-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2`

Use Python standard-library dependencies only. The approved build recipe sets
`PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1`, works in `/workspace`, copies
only `workspace/` there with ownership `65532:65532`, and runs as that non-root
user. Build context is the package root. The evaluator must inject trusted tests
separately and provide the required bounded writable workspace. Candidate solver
execution must never receive the reference solution. Reference calibration uses
a separate copy of the starting workspace with the solution overlaid.

The program interface is `python /workspace/program.py INPUT.json OUTPUT.json`.
Each task's instruction defines the JSON semantics. Test with independent expected
values, including edge cases and at least one plausible partially correct repair.
Do not derive expected answers by importing or running the reference program.

## Proposed intake checks

After Workstream's own custody and archive-safety checks, the registered project
PRE image should verify required package members, parse metadata, bind the exact
external task ID, reject unsupported dependencies or base images, and verify that
tests and reference material cannot be copied into the candidate image. A failure
must return actionable findings without creating a Submission. No package code
runs on the API host.

The catalogue must contain approved implementations for these checks before the
manager activates the policy. A setup-agent suggestion is not registration,
approval or a substitute for an implementation.

## Proposed post-submission checks

Evaluate the exact retained Submission under its locked policy:

1. Build the environment offline using the approved cached base and bounded
   sandbox. Missing files, invalid build instructions and unavailable platform
   dependencies must have distinguishable findings.
2. Inject tests separately and verify that the unchanged starter fails.
3. In a separate calibration copy, apply the reference and require all tests to
   pass. Inspect database or filesystem effects where the task promises them.
4. Repeat reference execution three times using fresh workspaces and compare
   outcomes. This is bounded stability evidence, not a proof of determinism.

A test that always returns success is invalid. A reference that only passes the
example input is insufficient. Infrastructure failure supplies no judgment of
contributor quality and must remain separate from a work failure.

## Five example briefs

- Ledger reconciliation: exact decimal aggregation, duplicate delivery and
  account/currency separation.
- Event rollup: timezone conversion, daily grouping, duplicate IDs and nearest-rank
  latency percentiles.
- Transactional import: idempotent SQLite writes and complete batch rollback.
- File inventory: nested paths, exact bytes, empty files and deterministic output.
- Configuration overlay: recursive merges, deletion, list replacement and false
  values.

The native `tasks.json` file contains task-authoring briefs, not evaluator
configuration. Task-local acceptance criteria are optional; this guide's package
and verification requirements remain mandatory.

## Manager and Finance handoff

For the first automated drill, propose `human_review_required=false` and
`requires_second_review=false`, with two permitted revision rounds and a 24-hour
revision window. These are inputs for separate authorized policy operations;
they are not fields in guide creation and do not approve themselves. The default
human-review branch remains true unless the manager explicitly changes it.
Finance separately publishes and binds the ContributionPolicy. Choose unpaid
contributions for the first drill unless a separately reviewed award fixture is
part of the planned scenario. No payment delivery is enabled by these assets.

Once required POST checks pass, the governed router uses the shared authorized
FinalAcceptance operation and creates the submitter ContributionRecord. It must
not fabricate a Review or reviewer contribution. Failed work follows the locked
revision allowance; infrastructure and uncertain effects follow operator recovery.
A new guide must never silently change the rules of already locked work.

## Evidence and limits

The checked-in corpus verifier runs trusted sample code locally. It proves only
its observed package checks and golden outcomes. It does not prove Docker builds,
gVisor isolation, actual registered checker execution, manager approval, live
inference, S3 activation, or the hosted Workstream journey. Those results must be
collected through the real project drill before release readiness is claimed.
