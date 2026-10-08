# ARCH-04E1B-B5 — Reject unrepresentable evaluation input before admission

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: hidden preparation checks the same bounded evaluation content that initial dispatch will consume, before any durable upload intent or ready admission.

## Intent

Close step 2 of the [first contributor milestone](planning/PLAN.md#first-complete-contributor-milestone).
ART's ZIP container ceiling permits 2,000 entries by default, while the locked
CHECKERS contract permits 1,024 manifest items, 1,000-character paths and a 1 MiB
request. Successful preparation must not strand an input that cannot be evaluated.
Preserve the current catalogue identity, locked policies and retained data. ZIP
container limits are not a promise that every archive fits the evaluation contract.

## Bounded change

- CHECKERS owns one immutable evaluation-content value containing the existing
  project, expected context, catalogue, compiled policy and structural input.
  The full evaluation request uses that same value/validation and adds real
  record identities. Before dispatch reuses this projection, verify the stored
  Submission context against these same locked facts; preparation has no stored
  Submission observation, and projection is not a substitute for the existing
  TASK evaluation guard. Move its existing project/policy/version/hash/catalogue
  consistency checks into this base so preparation also rejects impossible
  content. Preserve existing request serialization and digest semantics.
- Reserve 1,024 bytes of the existing 1 MiB envelope for finite UUID, version,
  hash, byte-count and schema fields. Prove the maximum legal envelope fits this
  reserve. Both preparation and dispatch enforce the same content budget; keep
  the existing full-request byte check. Do not invent record identities for preflight.
- One typed CHECKERS adapter projection consumes existing TASK/PROJECTS/ART
  public facts, actual packet text and verified file metadata. CHECKERS public
  contracts import no other product owner. Extend the existing locked TASK facts
  with mandatory nullable acceptance criteria and the existing complete
  TaskPolicyLineage value from the already locked TASK row. TASK verifies its
  locked post-policy body against that hash. Reuse TASK's existing policy-stamp
  projection to compare every locked identity/hash/generation against PROJECTS
  before capacity approval; do not defer this comparison to dispatch. The exact
  PROJECTS activation receipt supplies policy-context values only after that
  equality check. Stored nullable criteria map `None` to the empty checker text;
  both missing forms retain the existing missing-criteria outcome, never a
  fabricated requirement. This pure projection grants no execution or dispatch authority.
- Manifest entries represent every inspected file, without truncation. Evidence
  entries represent only policy-required keys whose canonical `evidence/{key}`
  file exists in that verified manifest, with the actual path/hash and key.
  Reuse the pre-submit compiler's canonical evidence-path rule; do not create
  EvidenceItem rows or infer quality. Missing files remain missing.
- Inject this required pure projection into existing ART preparation composition.
  At preparation pass file facts projected from inspected FILE entries; do not
  construct a post-consumption admission result before admission. Run the check
  after private ZIP inspection/manifest construction and before pre-submit
  attempt reservation, evidence execution or durable put. Reject invalid/oversized
  content with a bounded error, release scratch, and leave no durable admission.
  No provider invocation or extra TASK/PROJECTS lookup is needed for this check.
- Move the existing request-construction helper to the CHECKERS public surface
  for reuse by the later atomic dispatcher; update its consumers and remove the
  old definition rather than keeping an alias. Initial dispatch must reuse this
  content projection and validate the complete request with real identities.

## Allowed files

CHECKERS API post-submit content/request and artifact-path helpers, their exports,
existing request/result construction helper and affected compiler callers;
`app/adapters/checkers/__init__.py`; ART preparation/runtime composition and its
verified metadata projection; TASK submission-context facts/repository, existing policy-stamp validator and
typed TASK adapter, and exact
affected fixtures/callers; focused CHECKERS capacity/projection tests, ART
preparation and real PostgreSQL admission tests, TASK context tests; new-test lane
and behavior ownership registration only where required; this record and affected
ARCH/AUTH/CON/POL/REV navigation, README, checker/ART/TASK specifications and roadmap.

## Prohibited changes

No catalogue-limit/hash change, compatibility path, truncation, retained-data
rewrite, schema migration, dispatch event/reservation, new receipt storage,
authority activation, new route, worker registration, human-review/revision runtime,
claim expiry, provider fallback or weakened checks. Preserve pre/post separation:
this is representability checking, not post-submit evaluation during upload.

## Acceptance criteria

1. Valid real ZIP preparation reaches ready admission through current AUTH and
   storage verification; both ReviewPolicy modes use the same input rules.
2. Independently reject excessive file count, path length, packet/criteria text,
   policy projection and serialized content before attempt/evidence/put/admission
   writes; verify scratch release and no provider put. Include a valid control
   and a same-input retry, without hiding failure behind another invalid field.
3. Input accepted by the content boundary fits a full request using maximum legal
   identity/version/hash/byte-count envelope fields. One-byte overflow rejects in
   both entry paths, with Unicode and escaped text measured as canonical UTF-8.
4. Shared projection uses exact stored criteria, locked policy identities and
   inspected file hashes/sizes; evidence keys map only to matching verified files.
   Stored null and empty criteria both produce the existing missing-criteria
   checker outcome, without treating the capacity check as substantive evaluation.
   Independently changed TASK post/review/revision IDs, versions/generations,
   hashes and body reject before effects. Foreign project/context substitutions
   reject. No arbitrary evidence is added.
5. Removing the preparation capacity call makes a real oversized-ZIP regression
   fail at its intended assertion. Removing the shared byte guard makes its
   independent overflow proof fail. Keep existing authorization, rollback and
   replay tests; update affected callers without compatibility constructors.
6. Preserve catalogue and policy hashes and request digest semantics. Existing
   checker execution, result counters and retained manifest recovery keep their
   bounded contracts. Complete hosted tests without skips or gate changes.

## Risk and review routing

L1: architecture/security/reuse and QA/test-delta plan review before code;
implementation additionally reviewed for CI integrity and docs/product operations.
Shared verification: focused pure projection/boundary tests; real PostgreSQL ZIP
admission test; Ruff; module/AUTH boundaries; test structure, ownership and lane
inventory; links, stale wording, Commitrail; complete hosted suite. Human focus:
early no-effect rejection, exact owner facts, shared content budget, catalogue
preservation and absence of premature dispatch or authorization.

## Evidence

Discovery confirms the mismatch in `artifacts/submission_archive.py`, core
configuration and CHECKERS `api/post_submit.py`/`api/post_submit_catalogue.py`.
Preparation's inspection-to-evidence-reservation boundary is the earliest point
with verified complete file metadata and no durable put intent. Plan review confirmed the typed adapter, evidence projection and envelope proof.
The real ZIP regression covers 1,025 files and a portable 1,001-character path,
each retried without attempt/provider/admission effects, alongside verified ready
admission for valid input. Shared-boundary tests exercise canonical UTF-8 size,
one-byte overflow and the maximum identity envelope. Projection tests cover
exact file evidence, absent criteria, independent locked stamp substitutions and
both review modes as detached facts; they do not claim false-policy activation.
The real oversized-ZIP test exposed prepared scratch closing after its runtime
manager. Preparation now registers release inside the runtime lifetime, before
manager shutdown on rejection, failure or cancellation.
Existing packet-length tests retain their earlier boundary; they are not evidence
that this new capacity call rejects packet text first.

## Next dependency

Step 3 remains atomic initial Submission, ART binding, exact AUTH receipt custody,
CHECKERS reservation and outbox dispatch with fresh-authorized stable replay.
This change supplies representable content only. It does not replace the future
dispatch writer's exact TASK stamp/currentness validation or grant any authority.
