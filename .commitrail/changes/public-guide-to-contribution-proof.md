# Public guide input to governed contribution proof

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Replace the approved-guide shortcut in the bounded public runtime drill with public guide upload, asynchronous setup, separate manager approvals and exact policy activation, preserving both outcome branches.

## Intent

Issue #552 closes the integration gap between existing guide setup and the public
contributor journey. The first usable v0.1 path must start with original guide
bytes and task examples, not injected approved policy rows. This is integration
proof and owner-scoped defect repair, not a new setup or acceptance subsystem.

## Current behavior

Main `82a46ff3c` includes #549 public intake and #550 false-guide activation.
`experiments/pilot04_external_checker_runtime/run_public_journey_probe.py` runs
real API, MinIO, Redis, prefork workers, Beat and external checker images, but
`_one_mode` arranges compilation and approved policy facts through `source_case`.
`backend/scripts/guide_document_api_drill.py` covers real public upload and live
setup separately. `backend/scripts/guide_compilation_e2e.py` provides a scripted
external runtime behind the canonical adapter port. Neither composes the whole
journey from public source documents to contribution facts.

## Bounded change

### Allowed

- `experiments/pilot04_external_checker_runtime/run_public_journey_probe.py` and
  narrowly scoped companion guide-input/runtime helpers in that directory:
  replace fixture setup, retain downstream custody/outcome assertions.
- `experiments/pilot04_external_checker_runtime/README.md`: exact invocation,
  input, evidence, resource cleanup and limitations.
- `backend/scripts/guide_compilation_e2e.py` only where sharing existing scripted
  provider behavior avoids duplicate source/custody rules; callers must retain
  their current supported contracts.
- Focused drill tests under `scripts/test_public_guide_journey*.py` or existing
  affected test owners; root tests must not silently require a backend install.
- This record, README, affected current roadmap and ARCH/POL navigation: connected
  local proof versus hosted deployment and held evaluator work.
- Product fixes only after a concrete integration failure is reproduced and its
  exact owner/files, requirement and discriminating regression are added here
  and reviewed before implementation.

### Not allowed

No direct guide, compilation, policy, activation, Task, Submission or acceptance
fixture writes for the connected setup path. No weakened AUTH/custody guards,
new approval semantics, fallback routes, provider discovery, live model claim
from recorded output, private project documents, CI gate changes, evaluator
expansion, payment delivery, contributor lease work, frontend or CLI work.
Checker registry, initial identity/service provisioning, and the existing project
points unit plus AUTH-governed adapter binding remain explicit isolated
infrastructure preconditions. They cannot supply guide/policy facts, create
awards, activate fulfillment, or justify new public routes.
Held #492/#493/#496 remain held. Security #565 and pagination #497 are separate.

## Design and decisions

Extend the existing real runtime drill; remove its superseded approved-guide
bootstrap mode rather than maintain parallel fixture/public journeys. Use only
synthetic shareable guide originals with at least one meaningful task example.
Exercise actual Celery delivery and the canonical runtime adapter port with an
explicitly recorded test provider in the isolated worker entry point. The
production composition must not gain a test switch or fallback constructor.
The recorded provider opens exact ART-granted documents and returns the existing
closed proposal schema; production owners perform compilation/finalization.
The recorded provider must observe the exact normalized task examples, not
merely read documents. Assert their retained hash on the guide and source
snapshot, and bind the runtime-observed full input to the stored compilation
input hash (raw compilation context is not stored).
Public reads supply every manager decision target. Public PUT review-policy and
revision-policy operations set the exact true/false and revision configuration
with If-Match and idempotency headers; replay preserves their identity and a
stale selector cannot mutate them. PRE approval and POST approval remain
separate; Finance publishes ContributionPolicy through its
public owner and PM activates the exact context. Existing downstream public
claim, preparation, submission, selected POST, retry/replay and outcome proof
remain authoritative.

Use read-only database observations to prove complete lineage and no premature
or duplicate effects. An optional provider suggestion is advisory; a required
unsupported capability cannot silently disappear or authorize activation.
Insufficient source and provider failure must remain distinct. Prefer existing
owner tests for already-proven negative boundaries, adding only missing
connected proof and regressions for discovered defects.

## Acceptance criteria

- [ ] Original guide upload and task examples drive real async setup; no direct
  compiled/approved/active row insertion supplies the public journey.
- [ ] Setup stops at proposal; independent public PM PRE/POST approvals and
  Finance publication precede exact public activation, including replay.
- [ ] Original task examples and their normalized hash/snapshot commitment
  reach the actual worker runtime unchanged.
- [ ] Source document, setup/proposal, policies, activation, Task, Submission,
  checker and outcome identifiers/hashes form one exact retained lineage.
- [ ] Default true reaches `review_pending` without acceptance/economic facts;
  false reaches exactly one shared FinalAcceptance and submitter contribution
  with the applicable awards, no fabricated Review/reviewer contribution.
- [ ] Insufficient source, provider failure, required unsupported capability,
  correction, stale completion, cross-project access and replay have explicit
  authoritative proof; new integration defects have discriminating regressions.
- [ ] Real runtime cleanup releases every owned database, storage prefix,
  scratch area, worker, broker and subprocess; failure is bounded and reported.

## Risk and review routing

- Risk class: L1, cross-owner integration proof using real policy/AUTH/runtime.
- Required reviewers: architecture/security; QA/test_delta; documentation and
  product_ops for source-to-outcome scope and claims. CI integrity only if an
  actual gate change becomes necessary (not currently allowed).
- Human review focus: no fixture shortcut, real async execution, exact locked
  lineage, independent approvals, realistic outcome proof and honest limits.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing shortcut identified | `_one_mode` and guide API drills inspected | Confirmed | Public composition not yet run |
| Connected journey | Updated isolated public journey invocation (to be recorded) | Planned | No hosted Flow/S3/gVisor or live model claim |
| Failure boundaries | Existing owner tests plus focused new drill tests | Planned | Exact nodes mapped below |
| Repository integrity | Lint, boundaries, links, Commitrail, full hosted CI | Planned | No sampling or weakened gates |

## Reconciliation

- Current-source reconciliation: #550 merged at main `82a46ff3c`; its manifest
  renewal and replay guarantees remain unchanged. Parallel #565/#497 own their
  separate branches and PRs; existing CLI agent owns #499.
- Next usable boundary: #555 hosted operation and pilot after connected proof.
- Remaining risks: Recorded inference proves integration, not model quality;
  local identity, MinIO and development container isolation are not deployment.

## Focused failure-proof map

All paths below are relative to `backend/tests/`. Run named existing nodes with
`.venv/bin/python -m scripts.run_isolated_tests --metadata-json
/tmp/ws552-owner-proof.json --timeout-seconds 600 -- .venv/bin/python -m pytest -q tests/<node-path>`
from `backend/`, with the supported isolated PostgreSQL/MinIO environment. No
existing node is counted as connected public proof merely because it passes.

| Boundary | Exact existing proof or planned connected observation | Expected effect boundary |
|---|---|---|
| Insufficient source | `projects/guide_compilation/proposals/test_postgresql.py::test_blocked_result_allows_correction_but_never_approval` | Blocked report, no approval; a canonical correction successor is permitted |
| Uncertain provider | `projects/guide_compilation/test_hidden_orchestrator_postgresql.py::test_uncertain_provider_failure_never_redispatches` | PROVIDER_UNRESOLVED, one provider call, no invented success |
| Accepted-result recovery | Same module `::test_accepted_result_recovers_without_a_second_provider_call` | Existing retained result resumes without additional inference |
| Required missing capability | `projects/guide_activation/test_postgresql.py::test_checker_registration_requires_corrected_approval_before_activation` | No activation until registered implementation, corrected proposal and separate approvals |
| Stale completion | `projects/guide_compilation/test_live_cutover_postgresql.py::test_stale_delivery_rejects_before_any_compilation_effect` | Before provider/configuration and before new audit/product effects |
| Foreign-project reads | `projects/guide_compilation/proposals/test_public_api.py::test_public_package_denies_other_roles_and_scopes` | Public concealed denial under wrong grant/project |
| Exact examples | `projects/guide_compilation/test_task_examples_postgresql.py::test_required_examples_reject_before_product_effects_then_exact_replay` plus new connected runtime comparison | Missing examples deny; normalized examples/hash reach worker unchanged |
| Connected correction/replay | Planned `_public_guide_setup` in the updated runtime drill: one real PM correction, explicit dispatch, successor read, old-result preservation and exact request replay | Generation advances only once; source document/example commitment remains exact and stale source approval cannot activate |

Run the extended real runtime proof using the existing isolated runner with
`python ../experiments/pilot04_external_checker_runtime/run_public_journey_probe.py
--image-reference <owned-digest> --service-binary <built-local-service>
--broker-url <owned-loopback-redis> --work-dir <private-disposable-directory>`.
Its two branches cover source upload, worker setup, public policy configuration,
separate approval/publication, activation and downstream outcomes. This is an
explicit recorded-provider local drill; #555 retains live hosted-provider proof.

## Plan-review corrections

The first review identified omitted compensation infrastructure prerequisites,
public review/revision policy configuration, exact task-example observation and
an insufficiently specific negative-proof map. The plan above now specifies
all four; no production code was changed before resolving them.

## Connected-drill defect repair

The isolated connected drill reproduced PostgreSQL SQLSTATE `40P01`: the
public latest-setup read held Project and waited for Guide, while compilation
reservation held Guide and its attempt INSERT waited for the Project foreign-key
lock. This is a product defect, not an inference failure.

Additional allowed files are
`backend/app/modules/projects/guide_compilation/service.py` and
`backend/tests/projects/guide_compilation/test_automatic_request.py`.
Use the existing ProjectRepository parent lock at the start of the request
transaction, before replay classification, AUTH preparation and admission. Both
automatic and correction requests use that transaction. Do not add a Project lock
to the shared manifest reader or weaken diagnostic/AUTH locks.

The focused PostgreSQL regression pauses real attempt reservation immediately
before INSERT, starts the authorized public latest-setup read, observes its lock
wait from an independent session, then releases reservation. Both operations must
finish, with one attempt, one request operation and one request authorization
event. Removing the parent lock must make that same scenario fail. Inspect shared
request/replay consumers for ordering conflicts; preserve caller transaction and
exact replay behavior.

Separately, the drill poller must observe the existing in-flight
`provider_outcome_unresolved` marker until completion or its bounded deadline.
It must not retry HTTP 503 or other terminal errors. Focused pure tests cover
in-flight completion, bounded unresolved state and propagation of real failures.
This repair retains the original L1 reviewers and introduces no new subsystem.
The bounded plan replay passed before implementation; final code review remains
required after PostgreSQL and connected-runtime proof.

## Focused repair verification

The isolated PostgreSQL automatic-request module completed 29 tests, including
concurrent public latest-setup observation, replay, revocation and request custody.
Database and MinIO cleanup completed. The pre-repair-method probe and connected
runtime rerun remain pending; this focused result is not full journey proof.
The pure drill tests passed five cases, including source commitment substitutions
and bounded observation without hiding terminal errors. Initial hosted
`project_lifecycle_a` exceeded its 1,200-second bound, so full-suite evidence is
incomplete and must be refreshed on the repaired candidate.
