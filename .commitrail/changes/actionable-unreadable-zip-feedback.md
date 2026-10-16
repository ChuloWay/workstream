# Actionable unreadable ZIP feedback

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: The public submission-bundle preparation route rejects unreadable contributor ZIPs with a stable sanitized 422 response before any Submission, admission, checker execution, provider write, or task transition.

## Intent

Give contributors an actionable invalid-upload response when the authorized ZIP
preparation route cannot parse their archive. The existing failure is a
contributor-correctable intake rejection, but it currently escapes as an
internal server error and hides the already stable ART archive failure code.

## Current behavior

`SubmissionArchiveInspector.inspect` converts expected parser and archive-shape
failures to `SubmissionArchiveRejectedError` with one closed, non-sensitive
`SubmissionArchiveFailureCode`. `PreparedSubmissionBundlePreparationCommand.prepare`
prepares selected materialization authorization and then inspects the bytes before
selected PRE reservation, but its exception translation does not include that
error. The mounted route only handles public submission-preparation errors, so the
exception reaches the global 500 handler.
Open PR #575 changes successful preparation feedback but explicitly records this
malformed-ZIP behavior as a follow-up and does not translate the archive error.

## Bounded change

### Allowed

- `.commitrail/changes/actionable-unreadable-zip-feedback.md` for bounded intent,
  decisions, proof, and durable review findings.
- `backend/app/modules/artifacts/submission_admission.py` for exact translation of
  the existing typed archive rejection at the ART preparation-command boundary.
- `backend/app/api/routes/artifact_submissions.py` only if the public route must
  preserve the stable archive code in the canonical 422 envelope.
- `backend/tests/tasks/test_public_submission_intake.py` for a real authorized
  public-route regression and its valid-ZIP control.
- `backend/tests/test_submission_bundle_preparation_recovery.py` for lightweight
  route-envelope sanitation and unexpected-exception escape proof.
- `docs/spec_artifact_storage_service.md`, `docs/architecture_data_model.md`, and
  `docs/roadmap_status.md` for the affected current public contract and capability
  claim.

### Not allowed

- No archive-inspector, ZIP safety, resource-limit, scratch-custody, authorization,
  locked-lineage, task-transition, checker, provider, schema, migration, CI, CLI,
  finding-contract, or deployment changes.
- No catch-all `ValueError` or `Exception` translation, fallback response, alias,
  compatibility path, or duplicate preparation workflow.
- No change to pre-submit checker failure semantics or post-submit evaluation.

## Design and decisions

Keep `SubmissionArchiveRejectedError` as the sole expected inspector failure and
translate it only around the command's initial archive inspection. Preserve its
closed stable code as the existing generic non-retryable 422 envelope's actionable
`detail`; the canonical envelope retains its existing `invalid_request`
classification. All unexpected inspector, programming, and infrastructure failures
continue to escape this mapping and remain 500/503 as owned by their existing
boundaries. A typed archive failure from selected execution after its durable PRE
reservation also escapes unchanged so the reservation remains owned by the
existing retry and recovery path. The contributor rejection stays before selected
PRE reservation and the existing `AsyncExitStack` continues to close prepared
scratch.
Selected materialization authorization still occurs before inspection; the change
does not reorder or bypass that existing authorization preparation.

## Acceptance criteria

- [x] An authorized malformed or unreadable ZIP request returns HTTP 422 with the
  stable sanitized `submission_archive_malformed` detail and no parser, provider,
  scratch, or submitted-path detail.
- [x] The rejection creates no Submission, ready admission, selected PRE run,
  checker run, provider put attempt, or lifecycle/outbox effect and leaves the task
  and assignment in their valid working states.
- [x] Prepared scratch resources are released after the response.
- [x] A valid ZIP control still reaches the existing preparation path.
- [x] Unexpected inspector or runtime failures are not classified as contributor
  archive errors.
- [x] A typed archive failure raised by selected execution after PRE reservation is
  not translated to a contributor 422 and does not begin durable admission.
- [x] Existing archive-limit and safety cases remain protected and public/current
  documentation describes the delivered 422 mapping.

## Risk and review routing

- Risk class: L1
- Required reviewers: `security`, `qa`, `test_delta`; add `architecture` only if
  implementation changes the public owner contract rather than translating through
  the existing ART rejection contract.
- Human review focus: Narrow exception translation, stable/sanitized response,
  no-effect and scratch-cleanup proof before selected PRE reservation.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Pre-fix path escapes as 500 | Remove only the typed catch, then run `scripts/run_isolated_tests.py ... pytest -q tests/tasks/test_public_submission_intake.py::test_public_malformed_zip_returns_bounded_422_without_effects` | FAIL as intended in 196.82s: all preceding no-effect, state, scratch-cleanup, and spy assertions passed; response was sanitized HTTP 500 `internal_error`, failing only `500 == 422` | The probe uses the local provider and isolated PostgreSQL rather than hosted infrastructure. |
| Narrow repair returns sanitized 422 without effects | Same isolated public-route regression with the catch restored | PASS, 1 test in 94.26s; valid ZIP control returned 202 `stored_pending_verification` | Hosted environment behavior remains CI evidence. |
| Archive rejection is sanitized and unexpected failures escape | `pytest -q tests/test_submission_bundle_preparation_recovery.py` | PASS, 14 tests in 196.28s | Mounted route uses a rollback-only session fake because this suite owns HTTP mapping, not PostgreSQL. |
| Post-reservation typed failures retain recovery ownership | `pytest -q tests/test_submission_bundle_preparation_recovery.py::test_post_reservation_archive_failure_remains_recoverable` | PASS, 1 test in 75.46s; selected PRE reservation completed, the exact typed failure escaped, durable admission did not start, and scratch/authority cleanup ran | The focused command proof uses deterministic owner-port fakes; durable recovery itself remains covered by its existing PostgreSQL tests. |
| Existing archive-limit and safety behavior remains protected | `pytest -q tests/test_submission_bundle_preparation_recovery.py tests/test_submission_archive.py` before the helper isolation correction | All 41 archive tests passed; five route tests failed before route execution because the pre-existing mounted helper depended on an ambient database URL, then passed after the rollback-only dependency override | The clean post-fix command above covers the affected route suite; archive implementation is unchanged. |
| Python changes pass lint | `python -m ruff check` on the three changed Python files | PASS | Repository CI does not impose `ruff format`; unchanged surrounding files are not mechanically reformatted. |
| Repository contracts remain sound | Commitrail gate, stale Workstream/artifact scans, Markdown link check, and `git diff --check` on rebased main | PASS; Markdown checked four changed files and the artifact scan passed at `guide_source_cutover` | Hosted CI remains PR evidence. |

## Review findings

Plan review and exact-head reviewer findings will be recorded after the bounded
candidate is frozen.

- Independent plan review: PASS. Keep the existing public preparation rejection
  contract, translate only `SubmissionArchiveRejectedError`, prove closed-code
  sanitation and unexpected-exception escape, and make no blanket `ValueError`
  catch or new response DTO. The reviewer corrected the order claim above:
  selected materialization authorization preparation precedes inspection.
- Independent security/QA/test-delta implementation review: BLOCKED the first
  candidate because its command-wide typed catch also covered selected execution
  after durable PRE reservation. The catch is now scoped to the initial inspection,
  and a command-level regression proves a later typed failure escapes after
  reservation without starting durable admission.

## Reconciliation

- Current-source reconciliation: Baseline is `34501cd64`; merged main
  `801b8dabb` changes only CI lane capacity plus its operations/roadmap accounting
  and does not change the ART preparation owner or public behavior. Open PR #575 overlaps
  the command, route, public-intake proof, and roadmap but leaves this defect as an
  explicit follow-up. Reconcile its eventual merged response shape before PR
  readiness without duplicating its successful-feedback work.
- Next usable boundary: Independent exact-head implementation review, pull request,
  CI, and human merge; no additional product chunk is implied.
- Remaining risks: Hosted CI and exact-head reviewer conclusions remain PR evidence,
  not durable product behavior.
