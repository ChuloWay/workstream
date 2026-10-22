# Terminal Systems — live setup qualification

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Produce a useful, typed and reviewable guide-setup specification from the original guide, including correct checker classification and platform-limit inheritance; qualify it with the real provider before engineering images.

## Intent

Exercise the real guide upload and provider-backed setup before implementing
project checkers. Use the actual proposed requirements and capability gaps as
engineering input. Do not replace inference with a prepared response.

The user expanded PR #651 to include classification, structured engineering
specifications and invalid-output diagnosis. Keep these related repairs in this
PR, committing and reviewing each completed stage before advancing. The setup
agent must reduce PM interpretation work and produce a concrete implementation
handoff, not merely label requirements or return schema-valid prose.

## Current behavior

Main `91df16e76` includes the original guide/example/briefs and generic ECR image
publisher. Real setup of the original guide finalized a proposal blocked on
missing file/package limits despite ART already enforcing platform limits. The
corrected nullable contract produced a retained v5 draft from unchanged original
bytes, with all four project limits null. This proves that size-limit omission
need not block setup; it does not qualify the draft's checker classifications.
Other test containers on the workstation are separate retained environments.

## Bounded change

### Allowed

- Existing project-agent contract, instructions, SDK adapter and affected
  validation/finalization/public proposal owners; narrowly scoped adjacent
  interface modules if needed to keep the typed specification cohesive.
- Existing CLI proposal decoder and text renderer, affected API/process tests,
  manager-authored rules consumers, current setup specifications and runbooks.
- Focused pure, SDK-parser, PostgreSQL custody/hash/approval and CLI regressions,
  plus isolated live provider runs using unchanged guide bytes.

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

### Remaining stages in this PR

1. Define a bounded typed checker specification linked to each atomic
   requirement: evaluation method/stage, input materials, checks, pass criteria,
   failure findings, positive/negative examples and execution/infrastructure
   needs. Explain human-review and lifecycle classifications explicitly.
   Infer suitable verification from required outcomes; lack of a registered
   checker must yield an engineering gap, not a human-review fallback.
2. Preserve retained immutable result hashes and exact public reads when
   evolving the contract. Require complete specifications from newly compiled
   results, without rewriting earlier evidence or inventing implementation IDs.
   Keep all policy approval, registration and activation authority unchanged.
3. Render a concise PM overview followed by readable per-check specifications
   through the existing CLI command; retain complete structured JSON output.
4. Diagnose invalid structured results with bounded, non-content diagnostics;
   reproduce and fix actual contract/prompt gaps. Never weaken validation or
   silently retry terminal attempts until a result passes.
5. Replay the original guide, inspect semantic completeness of the resulting
   PRE/POST handoff, verify stored/public exactness and cleanup, then perform
   independent final review and required CI. No project-specific logic enters
   the shared runner. Building project images remains the next product step.

The specification design is subject to architecture review before implementation;
the existing nullable-limit repair and its evidence remain intact below.

The user clarified that platform limits already govern every upload. Silence
in the project guide must not block setup. Remove the attempted guide-level
duplication; retain uploaded versions and their outcomes unchanged. The canonical downstream project policy already represents absent overrides
as null. Align the inference result with that contract instead of copying
platform numbers into an immutable project restriction. Explicit project limits
may tighten, never lift, platform limits. ART remains the enforcing owner, including admission quotas;
setup does not own or bypass archive safety. No new configuration knob, schema
migration or parallel inference path is needed.

## Acceptance criteria

- [x] Isolated API, durable worker, scheduler and storage are healthy at a recorded source head.
- [x] Distinct local actors and service identities receive authority through existing supported operations.
- [x] The exact merged guide/example is uploaded through public routes, with verified document custody.
- [x] Real provider setup produces a retained proposal; no result is substituted.
- [x] A guide without numeric intake limits is not blocked for their absence; null project overrides leave ART platform limits in control.
- [x] The public proposal reader accepts null overrides while rejecting invalid positive limits.
- [x] Complete the isolated PostgreSQL explicit/null approval, replay and revoked-authority regression; a timed-out run is not a pass.
- [ ] New setup results include typed, evidence-linked specifications sufficient
  to implement and test each proposed check; malformed or contradictory specs
  are rejected without policy writes.
- [ ] Classification distinguishes mechanical checks, agent evaluation,
  explicitly human decisions and Workstream-owned lifecycle rules. Missing
  implementations remain visible engineering gaps.
- [ ] Prior retained result hashes/readability remain exact; new specifications
  survive projection, public read, approval/correction and CLI display.
- [ ] Invalid-output diagnosis identifies reproduced failure boundaries without
  exposing guide/model text, credentials or provider state.
- [ ] Real setup of the unchanged guide yields a useful reviewed engineering
  handoff; no activation/image/contribution claim substitutes for that proof.

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

Verification completed: 98 focused backend cases, nine CLI process tests,
229 clean-environment configuration tests, and both isolated PostgreSQL public
approval/replay/revocation cases passed. The final PostgreSQL run used source
`f7304e328`, whose runtime and test tree matches the final documentation-only
successors, and confirmed database/role cleanup. It replaced an earlier
incomplete timeout; that timeout is not counted as passing evidence. Go build
and vet, Ruff/CLI formatting, Markdown links, Commitrail and the three applicable
stale wording/authorization/artifact checks passed. Hosted full CI remains an
external merge check, not a claim established by these local results.

Version 2, the first real provider run, finalized a blocked proposal with 11 requirements
and five POST capability suggestions. Its blocking finding was missing finite
file/package size limits. The user clarified that platform defaults must not
be duplicated in the guide. The local 64 MiB task admission quota is an aggregate
storage limit, distinct from the configured per-source byte ceiling; do not turn
that quota into a project archive rule. Version 3 was already uploaded and produced terminal
`schema_invalid`; retain it unchanged. Version 4 used the original guide with the
nullable repair but also ended `compilation_invalid_terminal` / `schema_invalid`.
Neither result is repaired or retried in place, and their invalid-output cause
has not been diagnosed. A manually initiated fresh version 5 returned
`policy_draft_ready` from the same 12,110 original bytes (SHA-256
`13d789d4b8df5d6b310d844c622336f265d53d2ddc38e8aa101b67765f9f7183`).
The exact public proposal reports all four project limits null and nine
requirements: eight human-review dispositions and one lifecycle disposition,
with no bindings or capability suggestions. This proves nullable handling on
one real provider run, not repeatable model correctness or a complete checker
handoff. Review those classifications before approving anything.

Version 5 ran through the real durable worker and provider with local diagnostic
wrappers that retained normal validation and only attempted to report validator
locations/types on failure. No model output was substituted or repaired. The
ordinary worker command is restored after that run. Local retained evidence is
under the ignored `.local-agent-loop/terminal-systems-live/` directory: v4/v5
setup statuses, the exact v5 public proposal, original-byte proofs, and test
logs. No PRE/POST approval, guide activation, project checker/image, released
task or contribution outcome is claimed. All uploaded attempts remain retained.

The public original-document download matched all 12,110 uploaded bytes and
SHA-256. Deliberate unchanged-key upload replay returned the original receipt
without creating a successor setup generation. An unassigned actor's setup
read returned concealed 404. After version 5, all 12 provider resources recorded
across versions 2 through 5 were confirmed deleted.

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
- Next usable boundary: review the actual v5 requirements and determine correct
  PRE/POST capability gaps before engineering images or approving policy.
- Remaining risks: earlier schema-invalid model outcomes remain unexplained;
  requirement classification, model/tool reliability, offline builds and the
  contribution journey still need qualification. A successful nullable proposal
  is not end-to-end project readiness.
