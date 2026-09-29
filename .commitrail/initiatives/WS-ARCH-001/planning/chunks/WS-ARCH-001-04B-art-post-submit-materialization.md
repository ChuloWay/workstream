# Chunk Contract: WS-ARCH-001-04B ART Post-Submit Materialization

Disposition: Planned. Dependencies: 04A, POL-07, ARCH-03C, ARCH-03D and merged 02H.
Risk: L1. Migration head: `0006_history_read_authority`; no migration planned.

## Intent and boundary

Give the fixed post-submit checker service bounded access to the exact verified
ZIP consumed by one immutable Submission. Replace the unused generic
`ArtifactMaterializationPort` / `BindingMaterializationRequest`; no compatibility
alias remains. Public submission intake, durable execution, output storage,
routing, review and acceptance remain deferred to their existing chunks.

The consumed ART admission alone cannot establish the Submission's TASK-owned
status and frozen policy stamps. Add one small TASK read port rather than reading
TASK tables inside ART or repurposing contributor/history projections. Its query
is project/task/submission-qualified from the start. It returns detached scalar
ownership, artifact and frozen-policy references, not packet content or policy
bodies. No TASK mutation or current-guide rebasing is introduced.

## Design

1. Reuse the closed `PostSubmissionEvaluationRequest` from 04A. It selects exact
   project/task/assignment/Submission and version, binding/content, evaluation
   request/generation/digest and locked context. It cannot choose a provider
   object, replica, namespace, path, arbitrary binding list or service identity.
2. Production composition supplies explicit deny-only materialization authority.
   Its preflight denies before database/provider/scratch access. Controlled test
   authority allows hidden owner proof; this is not live AUTH activation. Exact
   server-selected material facts are authorized before provider access. ARCH-04D
   supplies live service admission and generation/replay/revocation enforcement.
3. A short read transaction resolves public TASK facts and ART's consumed admission,
   exact submission binding/content, admitted replica, verification receipt and
   active namespace. Reuse canonical namespace validation. Read fresh scalar rows,
   not cached ORM objects. Reject missing, foreign, unconsumed, nonverified or
   inconsistent material before storage access. The immutable Submission selects
   historical locked policies, never today's guide.
4. End the transaction before I/O. Stream through the provider-neutral ArtifactStore
   into ArtifactPreparationService. Recompute complete digest/size, inspect the ZIP
   with SubmissionArchiveInspector and compare the rebuilt semantic-manifest hash.
5. Reuse `_process_prepared_submission` and `project_and_run` to supply an asynchronous
   consumer with a typed read-only entry/bounded-file view. The public call remains
   async; blocking projection runs off-loop. The existing synchronous pre-submit
   wrapper and the async post-submit consumer share one projection context manager;
   no second extraction implementation is introduced. The consumer returns only the existing
   closed PostSubmissionEvaluationResult, validated against its request. ART returns
   that value together with typed material custody facts after cleanup. No raw path,
   provider handle, credential or live tree survives the callback. Cancellation
   drains processing before releasing the existing scratch reservations.
6. Re-read and compare the same persisted selection after I/O before returning.
   A changed Submission/replica rejects the result. No transaction or PREP survives
   provider I/O. This is materialization freshness, not final execution/result
   authority: ARCH-04C/04D still own current attempts and fresh final publication.
   Full structural packet construction remains 04C; ART validates only the byte
   and locked-context facts owned by its materialization boundary.

### Exact selection predicates

TASK returns project/task/assignment/Submission ID and version, contributor ID,
predecessor ID, status, contribution-policy version, admission/binding/content IDs,
and guide/source/effective/pre/post/review/revision identities, versions/generations
and hashes. Require Submission status `submitted`, exact project/task/assignment
and Submission/version, and exact binding/content. Compare the full stamped context
with request.expected_context and request.structural_input.observed_context. Other
structural text remains outside this port's authority.

ART requires the stored admission to be consumed by that exact Submission/version,
with matching project/task/assignment/contributor/content and predecessor. Require
binding project/resource_type= submission/resource_id/logical_role=
submission_bundle_original/scope_version=1/content to match exactly. Require content
ZIP media type, digest and size to match the admission and request. The admitted
replica must match content, active namespace and canonical content-derived provider
reference, with verified/available/valid states. Its receipt must be verified with
matching digest/size and a verification job for that replica. Rebuild the exact
semantic manifest from bytes and compare its hash to admission; require the request's
file manifest paths/hashes/sizes and package hash to match server-owned byte facts.

Post-I/O selection compares the complete detached TASK facts plus ART admission,
binding/content/replica/receipt IDs, archive and manifest commitments, replica
states and namespace/provider identity. No current-guide lookup substitutes for
Submission stamps; no run-generation state is invented before 04C/04D.

## Allowed files

- `backend/app/modules/artifacts/api/submission_materialization.py` (new) and
  `backend/app/modules/artifacts/api/__init__.py`.
- `backend/app/modules/artifacts/post_submit_materialization.py` and
  `backend/app/modules/artifacts/post_submit_selection.py` (new owner files).
- `backend/app/modules/artifacts/preparation.py` (shared processor wording only) and
  `backend/app/modules/artifacts/submission_archive.py` (one shared projection lifetime).
- `backend/app/modules/tasks/api/submitted_bundle.py` and
  `backend/app/modules/tasks/submitted_bundle.py` (new read port and owner).
- `backend/app/modules/tasks/api/__init__.py`,
  `backend/app/adapters/tasks/__init__.py`, `backend/app/adapters/artifacts/__init__.py`.
- `backend/app/interfaces/artifact_operations.py` (remove superseded empty contract).
- New `backend/tests/test_post_submit_materialization.py`,
  `backend/tests/test_post_submit_selection.py`,
  `backend/tests/post_submit_materialization_helpers.py`; existing
  `backend/tests/test_artifact_architecture.py`,
  `backend/tests/test_checker_materialization.py` and
  `backend/tests/architecture/test_module_boundaries.py` for affected proof.
- Existing lane catalogue and ownership/structure ledgers and their tests only
  to register affected paths and preserve existing proof, never weaken gates.
- This contract, current ARCH/AUTH/POL overviews/plans/maps, `.commitrail/INDEX.md`,
  `docs/roadmap_status.md`, `docs/spec_artifact_storage_service.md`,
  `docs/architecture_checker_framework.md`, `README.md` and applicable ART specs
  only for this boundary and the next output-custody step.

Prohibited: new routes, TASK writes, policy/compiler changes, checker run/result
writes, REV packet access, generic downloads, worker activation, output ingestion,
new persistence states, data deletion, grant activation, serialized process handles,
private cross-owner imports, alternate scratch or provider implementations.

## Acceptance and verification

- Valid Local and MinIO originals yield the exact admitted files and executable
  flags; output facts identify the stored Submission and ART custody.
- Denial and mismatched selectors fail before provider open or scratch use.
  Default composition remains unavailable. Controlled generation/replay denial
  proves the authority seam, not production generation custody.
- Full-byte digest/size or semantic-manifest mismatch prevents consumer invocation.
  Retained views are revoked after success, consumer failure and cancellation;
  quota/deadline failures release scratch. Existing ZIP-safety proofs remain.
- Real migrated PostgreSQL proves owner-qualified selection and independent-session
  replica/state change during provider I/O; no row lock or open read transaction
  spans that I/O. Valid controls and discriminating guard-removal probes must reach
  the claimed behavioral assertion rather than fail during fixture setup.
- A real admitted/consumed fixture proves the complete stored lineage. Pure
  contract and scratch tests use focused fixtures; no permissive fake is called
  live authorization or durable admission proof.
- Remove the dead interface and update every traced caller/spec/test together.
  Preserve pre-submit behavior and separate production execution unavailability.

The full migrated fixture is the existing
`tests/tasks/test_submission_lineage.py::test_real_zip_admission_and_hidden_creation_copy_exact_assignment`
flow and `tests/tasks/submission_lineage_support.py::_verified_admission`:
real preparation, provider put, independent verifier publication, hidden Submission
creation and admission consumption. Reuse its helpers; do not use the reduced
`test_artifact_bindings_db.py` schema as full-lineage proof.

Concrete commands (from `backend/`, with the existing local test services/env):

```sh
.venv/bin/python scripts/run_isolated_tests.py --metadata-json /tmp/arch04b-focused.json --timeout-seconds 900 -- .venv/bin/python -m pytest tests/test_post_submit_materialization.py tests/test_post_submit_selection.py tests/test_checker_materialization.py tests/tasks/test_submission_lineage.py -q
.venv/bin/python -m pytest tests/test_artifact_architecture.py tests/architecture/test_module_boundaries.py tests/test_ci_lane_catalogue.py -q
.venv/bin/ruff check app/modules/artifacts app/modules/tasks/api app/modules/tasks/submitted_bundle.py app/adapters/artifacts app/adapters/tasks tests/test_post_submit_materialization.py tests/test_post_submit_selection.py tests/post_submit_materialization_helpers.py
```

From repository root run `python3 scripts/check_markdown_links.py`,
`python3 scripts/check_commitrail_records.py`, and `git diff --check`.
Use a unique metadata path per isolated rerun. New test paths above are planned.

Run focused tests with `backend/scripts/run_isolated_tests.py` against migrated
PostgreSQL and existing MinIO; new named files above are planned tests. Run Ruff,
architecture/ownership/lane tests, `git diff --check`, existing markdown-link and
Commitrail validators, then all required hosted lanes. Coverage is diagnostic.
Do not claim production execution or live AUTH from these tests.

Required focused reviews: plan review before implementation; architecture/reuse,
security, QA/test-delta, product-ops/documentation, senior engineering and CI
integrity against a clean candidate. Human review focus: exact source selection,
transaction-free I/O, callback lifetime, fail-closed composition and accurate
separation from future durable execution and live authorization.

## Plan review

Read-only design review identified the missing TASK read boundary and selected
existing closed CHECKERS request/result contracts over generic object returns.
Final expanded-plan review is pending; no product implementation has started.

## ARCH-04B2 — Separate ART output-custody child

Input materialization does not implement output persistence. Keep a separate
ART-owned bounded change for `CheckerArtifactOutputPort.store` and
`ArtifactBindingPort.bind_checker_output`, using 04A's exact immutable request,
attempt/run and policy facts. Reuse the generic admission, put-intent,
verification, quota and binding infrastructure. Replace the current ART
repository's private CheckerRun lookup with the canonical public-fact boundary;
do not import CHECKERS models in ART behavior. Existing relational run foreign
keys may remain and use controlled foreign-row fixtures for hidden proof.

Runtime CHECKERS reserves its run before output I/O. ART admits bounded output
and logs against project/task/fixed-service/deployment quotas, never contributor
quota, independently rereads/verifies bytes, then supplies a flush-only binding
participant. No row lock or PREP survives storage I/O. 04C later composes final
binding publication with final CHECKER result and completion outbox in one
transaction, after fresh exact action authority supplied by 04D.

The output child proves Local/MinIO parity, non-reproducible/unknown outcome
handling without fabricated bytes, crash cleanup, deadline/quota races,
foreign-request denial and fixed-service attribution. 04C/04D separately prove
the integrated run/binding/result transaction. Neither child owns TASK routing,
REV records or contributor-blame decisions. Expand each owner-local child into
its exact implementation record rather than combining ART and CHECKERS writes
in one implementation PR.

## Merge outcome

- Outcome on merge: `planned` until implementation and proof are complete.
