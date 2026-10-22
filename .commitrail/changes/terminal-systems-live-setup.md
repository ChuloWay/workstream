# Terminal Systems — live setup qualification

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Leave absent project size limits null during guide setup, without requiring contributors’ project guides to repeat infrastructure limits; prove with the actual original guide.

## Intent

Exercise the real guide upload and provider-backed setup before implementing
project checkers. Use the actual proposed requirements and capability gaps as
engineering input. Do not replace inference with a prepared response.

## Current behavior

Main `91df16e76` includes the original guide/example/briefs and generic ECR image
publisher. Real setup of the original guide finalized a proposal blocked on
missing file/package limits despite ART already enforcing platform limits. Other
test containers on the workstation are separate retained environments.

## Bounded change

### Allowed

- Ignored local Compose configuration and operator scripts for a uniquely named
  PostgreSQL/Redis/MinIO/API/Celery environment, public API/CLI calls and private
  redacted evidence.
- This record and factual input/runbook corrections supported by observed
  results. Any runtime repair requires its own explicit allowed paths and
  reproducer before editing.
- `pilots/terminal_systems/guide.md`, `guide-request.json` and `README.md`:
  keep the original guide free of duplicated platform limits, use a new guide
  version and record the actual setup boundary.

- `backend/app/interfaces/project_agents.py`,
  `backend/app/core/project_guide_instructions.py`,
  `backend/tests/test_agent_runtime.py`,
  `backend/tests/projects/guide_compilation/test_projection_policy.py`, and
  focused existing PostgreSQL proposal tests: permit null file/package project
  overrides and prove exact projection without inventing platform values.
- `cli/internal/api/guide_proposal.go`, its process tests and `cli/README.md`:
  preserve nullable project limits through the strict public proposal reader.
- `docs/roadmap_status.md` and the setup configuration/operator documentation:
  reconcile default-limit ownership and the actual qualification boundary.

### Not allowed

- No private reference content, credentials or provider tokens in Git or logs.
- No direct product-row writes, prewritten inference results, fabricated
  checker coverage, automatic approval or destructive cleanup of other stacks.
- No claimed guide activation or contribution outcome before real evidence.

## Design and decisions

The user clarified that platform limits already govern every upload. Silence
in the project guide must not block setup. Remove the attempted guide-level
duplication; retain uploaded versions and their outcomes unchanged. The canonical downstream project policy already represents absent overrides
as null. Align the inference result with that contract instead of copying
platform numbers into an immutable project restriction. Explicit project limits
may tighten, never lift, platform limits. ART remains the enforcing owner, including admission quotas;
setup does not own or bypass archive safety. No new configuration knob, schema
migration or parallel inference path is needed.

## Acceptance criteria

- [ ] Isolated API, durable worker, scheduler and storage are healthy at a recorded source head.
- [ ] Distinct local actors and service identities receive authority through existing supported operations.
- [ ] The exact merged guide/example is uploaded through public routes, with verified document custody.
- [ ] Real provider setup produces retained requirements/proposals or a diagnosed explicit failure; no result is substituted.
- [ ] A guide without numeric intake limits is not blocked for their absence; null project overrides leave ART platform limits in control.
- [ ] The public proposal reader accepts null overrides while rejecting invalid positive limits; explicit retained policies and immutable runtime configurations remain readable.
- [ ] Missing capabilities and any configuration/input gaps are reported accurately for the next engineering step.

## Risk and review routing

- Risk class: L1 for live authority/storage/model integration.
- Required reviewers: architecture, QA/test delta, and documentation/product operations for the nullable public contract and live qualification claims.
- Human review focus: actual setup findings, project policy choices and the next image implementation scope.

## Evidence

The focused regression `test_absent_project_size_limits_remain_null_through_projection`
exercises all three nullable combinations; the nullable projection
cases reject None on the original schema and preserve None after the repair.
`test_public_approval_read_replay_and_current_authority` exercises both explicit
and null limits through real PostgreSQL, public approval, exact replay and grant
revocation, including an assertion on the retained policy body. CLI process proof
covers individual and combined null/omitted limits and existing invalid numeric
bounds. The SDK strict-output schema still requires nullable properties in its
wire shape. ART archive/configuration regressions independently protect platform
enforcement; no ART implementation changes are part of this repair.

The first real provider run finalized a blocked proposal with 11 requirements
and five POST capability suggestions. Its blocking finding was missing finite
file/package size limits. The user clarified that platform defaults must not
be duplicated in the guide. The local 64 MiB task admission quota is an aggregate
storage limit, distinct from the configured per-source byte ceiling; do not turn
that quota into a project archive rule. Version 3 was already uploaded and produced terminal
`schema_invalid`; retain it unchanged. The corrected source returns to the
original guide and uses a fresh version after the setup repair.

The public original-document download matched all 12,110 uploaded bytes and
SHA-256. Deliberate unchanged-key upload replay returned the original receipt
without creating a successor setup generation. An unassigned actor's setup
read returned concealed 404. All three recorded provider resources were deleted.

The PM proposal read initially returned concealed 404 because the local actor
had only system-level PM authority. Issuing the required exact-project grant
through the public admin operation enabled the complete proposal read. This
was a test-provisioning omission, not a product defect.

Docker named-volume operations hung on this workstation. The same application
services started with dedicated persistent bind directories and exact image
identities recorded locally. Other stacks and retained volumes were untouched.

## Review findings

Architecture review rejected copying platform settings into proposed project
limits: doing so would freeze a platform default as a separate project
restriction. The smaller repair is nullable project overrides, already supported
by canonical policy and intake consumers. No new runtime configuration field is
needed.

## Reconciliation

- Current-source reconciliation: merged #647 and #649 on main `91df16e76`.
- Next usable boundary: actual setup requirements and capability suggestions.
- Remaining risks: model/tool availability, offline build capabilities and later
  runtime/project qualification remain to be tested.
