# WS-ARCH-001-04A — Registered post-submit contracts for unified guide setup

- Initiative: WS-ARCH-001
- Durable disposition: Planned
- Intended merge outcome: CHECKERS exposes its versioned post-submit catalogue and immutable phase contracts, with conformance evidence for its registered structural implementations; live unified setup remains POL-04B.

## Intent

Finish the unified Project Guide path using the adopted dependency contract.
The guide agent must receive an accurate description of supported post-submit
checks before producing a generation intended for approval. This change does
not invent another policy, checker registry or generation flow.

The selected delivery order is ARCH-04A, POL-04B, POL-05A/AUTH-12F4/POL-05B,
POL-06A/AUTH-12G/POL-06B, then POL-07. Return to CP06/CP07 afterward and connect
guide activation through AUTH-12H. CP06 remains technically independent; this
is the user's delivery priority, not a new hard dependency. POL-08 physical
cleanup remains later under the adopted preservation/routing prerequisites.

This record refines the [adopted contract](planning/chunks/WS-ARCH-001-04A-checker-post-submit-api.md)
and [cross-owner dependency contract](planning/PLAN.md#current-dependency-contract).
One unified invocation produces both phase proposals before approval. Separate
pre/post approvals do not rerun that invocation or execute submitted work.

## Current behavior and discovery

Baseline: main `4e05ebfa` (PR #387 merged). Active migration head:
`0012_contribution_policy_audit_resource`. No migration is planned here.

- `backend/app/modules/checkers/api/__init__.py` currently exports pre-submit
  facts only. `runner.py` owns the actual registered structural handlers.
- `backend/app/modules/projects/post_submit_policy.py` imports that private
  runner and assembles a sparse read-only catalogue. Its default IDs and
  compiler-version snapshots already govern persisted policy hashes.
- `PostSubmissionCapabilityDefinition` in
  `backend/app/interfaces/project_agents.py` exposes only identity, stage,
  default and selection flags. `_validate_bindings` rejects every post binding
  parameter. These limitations must remain honest until versioned replacement.
- `check_acceptance_criteria_present` checks that task criteria are nonblank;
  it does not evaluate whether work satisfies them. The other eight registered
  defaults also perform structural/policy checks, not general quality judging.
- `check_policy_context_present` still requires a legacy payment-policy version.
  New guide contracts must not inherit that prerequisite or fake a payment row.
  Its historical implementation cannot be silently redefined under the same
  version. This is an explicit versioned conformance obligation below.
- Existing compiler/hash and checker tests remain regression controls.
  `tests/test_checker_catalogue.py` covers the pre-submit catalogue; it is not
  proof of a complete post-submit public catalogue.

## Bounded change

### Allowed implementation files

All backend paths below are relative to `backend/`.

- New `app/modules/checkers/api/post_submit_catalogue.py`: immutable definition,
  catalogue snapshot and configuration-validation value contracts.
- New `app/modules/checkers/api/post_submit.py`: immutable evaluation request,
  result/currentness references, failure vocabulary and one async phase port.
- `app/modules/checkers/api/__init__.py`: explicit exports only.
- New `app/modules/checkers/post_submit_catalogue.py`: trusted snapshot builder
  over the existing registered implementations, no second dispatch map.
- New `app/modules/checkers/post_submit_contracts.py`: canonical digest and
  lineage validation; use existing canonical hashing and immutable JSON helpers.
- New `app/modules/checkers/post_submit_implementations.py`: immutable input
  adaptation and the versioned modern policy-context implementation. Reuse
  existing pure structural helpers; do not copy their rule logic.
- `app/modules/checkers/runner.py`: attach explicit versioned definitions to
  the existing registrations and extract only helpers needed for typed reuse.
  Preserve existing callers' versioned behavior and outcome semantics.
- `app/interfaces/project_agents.py`: versioned post-capability input and
  binding validation only; preserve old accepted context/result identities.
- `app/modules/projects/post_submit_policy.py`: consume the CHECKERS public
  catalogue/configuration validator; preserve historical compiler bodies and
  hashes. No approval/service/worker cutover here.
- `app/adapters/checkers/__init__.py` only if construction of the public port
  requires the canonical same-owner composition root. No live composition.
- New `tests/checkers/post_submit/` modules: `support.py`, `test_catalogue.py`,
  `test_configuration.py`, `test_request.py`, `test_result_contract.py`,
  `test_conformance.py`, `test_public_boundary.py`.
- `tests/test_project_guide_compilation_contracts.py`, `tests/test_checkers.py`
  only for focused historical parity controls; no bulk rewrites.
- `scripts/test_lane_catalogue.py`: additive registration of new test modules.
  Existing lane ownership and required collection remain unchanged.
- `.ci/module-boundaries/private-edge-debt.v1.json` at repo root: remove an
  actually eliminated PROJECTS-to-CHECKERS private edge; never add exceptions.
- This record, its adopted chunk pointer, ARCH/POL overviews and ARCH planning
  map, `.commitrail/INDEX.md`, `docs/roadmap_status.md`, and
  `docs/architecture_checker_framework.md` for accurate intended outcomes.

### Not allowed

No ORM/schema migration, AUTH action/permission/service activation, Task or
Submission writes, guide approval/activation, checker-run persistence,
currentness locks, routing, dispatcher, acceptance or compensation effects.
No ART provider/storage/scratch changes, public execution route, per-checker
product command, model evaluator, external call or new dependency. Preserve
pre-submit policy/compiler/executor ownership and mandatory platform checks.
Do not implement POL-04B consumption in live workers here. No CP06 work.

## Design and decisions

### One versioned registry, truthful capability support

Extend the existing explicit `default_checker_registry` registrations with
immutable versioned definitions. Derive the public catalogue from those
registrations; metadata and handler availability must agree. No separate
PROJECTS constants become an alternative registration authority. A definition
pins ID/version, post-submit stage, execution method, typed configuration and
result schema, ordering/dependencies, failure categories, input/resource
limits, provider-recovery support, required output roles and supported claim.
Canonical hashing includes every semantic field and rejects duplicates,
unknown dependencies, invalid order and unsupported schema/version.

The concrete supported set for this bounded change is the existing eight
mandatory defaults plus the sole selectable
`check_acceptance_criteria_present`. All are structural deterministic
implementations. The selectable check has a closed empty configuration; no
invented parameters or substantive evaluator are advertised. Future typed
configurations pass only their registered schema validator, never a generic
name/value acceptance path. Unknown substantive automated requirements remain
capability gaps. Explicitly approved `human_review` remains a valid disposition;
unsupported automation is not silently converted to it.

The modern definition of `check_policy_context_present` gets a distinct
implementation version. It validates the complete immutable guide/policy
references including ContributionPolicy, review and revision lineage, without
PaymentPolicy. Preserve the old version for historical consumers; never
substitute the new version when replaying a pinned old policy. Other handlers
reuse their existing structural logic against immutable owner-local input
facts, with no TASK ORM types exposed by the new public API. Registry tests
must prove every advertised version resolves to its intended implementation.

Resources/configuration are code-owned, not agent-defined. Existing checks
require no generated output/log artifact, external provider or recovery call;
definitions declare those facts explicitly. Input-count/byte ceilings and
execution budgets must be fixed in the implementation's typed definitions and
covered at their boundaries before a catalogue is considered usable. Reuse
existing source-field limits where available; do not infer unlimited input
from the legacy ORM-shaped context.

### Frozen input, phase identity and downstream custody

Use a strict immutable CHECKERS-owned `PostSubmissionEvaluationRequest`, with
UUID evaluation-request/project/task/assignment/Submission selectors, positive
Submission version and evaluation generation, ART content/binding ID plus
SHA-256 and byte count, and exact locked guide/source/compilation, effective,
pre/post, review/revision and ContributionPolicy references. Include the exact
catalogue snapshot and canonical compiled post-policy identity. References are
value facts, never proof that a database row or authorization exists.

Validate nested identity consistency and recompute the canonical request hash;
a supplied digest is not authority. Reject malformed/extra fields, nonpositive
versions, bool-as-int, mismatched policy/catalogue hashes and cross-phase facts.
No runtime port may accept a caller-selected checker-name list. The sole async
post phase command consumes the complete locked request. Its default
implementation raises a specific unavailable failure and performs no I/O.

Result references identify request/digest, attempt, generation and bounded
phase outcome; infrastructure failure is distinct from failed submitted work.
No result carries `accept` or writes lifecycle truth. Currentness facts bind
the exact completed result identity; a value schema does not establish that
only one result is current. ARCH-04C supplies durable currentness and retry
custody; 04E supplies routing. Same-request recovery is distinct from a newly
authorized evaluation after terminal failure. These are contracts tested with
controlled facts, not future database rows or live service credentials.

Preserve `PostSubmitCheckerPolicy.policy_hash` as the only compiled post-plan
hash. A request hash binds additional execution lineage; it is not a second
policy hash. Preserve existing v1 policy bodies/hashes and stored compilation
replay. New catalogue semantics use an explicit new schema/snapshot identity;
POL-04B must create a new generation rather than enrich old results in place.
POL-06 owns compilation of the new approved canonical post-policy body.

## Acceptance and discriminating verification

The following are future implementation tests, not claims of executed proof.
Each negative starts from the same complete passing fixture, changes one
property, and asserts the specific rejecting boundary.

| Proof | Valid control and counterexample |
|---|---|
| `test_catalogue_matches_registered_versions` | Every advertised definition resolves; independently remove a handler, change its version, repeat an ID, or change order/dependency and deny. |
| `test_catalogue_hash_binds_semantics` | Fixed canonical snapshot is stable; each semantic-field change changes identity; mutation of exported nested values cannot change the stored snapshot. |
| `test_binding_uses_registered_configuration` | Empty config succeeds for the supported selectable check; unknown parameter, wrong stage/version, disabled definition, platform default selection and unknown capability each deny. |
| `test_structural_conformance` | Call the real registered handlers for all nine definitions. Nonblank criteria pass the presence claim; blank criteria fail it. Structurally valid poor work is never reported as substantive quality proof. |
| `test_modern_policy_context_without_payment` | Complete modern refs with no payment row pass the new version. Independently omit/cross each required reference and fail. Pinned legacy-version control retains its original behavior. |
| `test_request_digest_and_lineage` | Fully coherent request passes; change each project/resource/generation/policy/catalogue selector independently, recomputing the outer digest where appropriate, to reach semantic checks instead of only hash rejection. |
| `test_post_port_unavailable` | Valid request reaches the unavailable guard. ART/provider/DB spies see zero calls; malformed input alone is not proof of this guard. |
| `test_result_is_not_currentness_or_acceptance` | Matching typed result reference succeeds; wrong request/digest/generation and invalid outcome shape deny. A completed value alone supplies no writer/route/acceptance capability. |
| `test_historical_compilation_and_policy_hashes` | Existing v1 examples preserve byte identity/hash and parameter rejection; new snapshot cannot be injected into old replay or selected as an implicit latest version. |
| `test_public_api_has_no_private_owner_types` | Public imports expose immutable contracts only, one post command and no individual-checker product API; existing pre-submit contracts remain unchanged. |

For the configuration and modern-lineage guards, remove the particular guard
in a temporary test-of-the-test probe and require the named regression to fail
for its intended assertion. Restore source before shared checks/review.
Conformance tests exercise implementations, not a fake returning success.
Substantive-invalid-work proof is required only when implementing an evaluator
that actually claims substantive evaluation; none is added by this change.

## Verification commands and evidence limits

From `backend/`, after the named implementation modules exist:

```sh
.venv/bin/python -m pytest -q tests/checkers/post_submit tests/test_project_guide_compilation_contracts.py
.venv/bin/ruff check app/modules/checkers app/interfaces/project_agents.py app/modules/projects/post_submit_policy.py tests/checkers/post_submit
.venv/bin/python -m scripts.module_boundaries validate --protected-base origin/main
.venv/bin/python -m pytest -q tests/architecture/test_module_boundaries.py tests/test_ci_lane_catalogue.py
```

From repo root, run `python3 scripts/check_markdown_links.py`, stale wording
inspection and, against a committed candidate,
`.venv/bin/python scripts/check_commitrail_records.py --base-ref origin/main`.
Full backend/PostgreSQL/coverage and required collection evidence stay in
hosted CI; do not run the full suite or local database concurrency on this
resource-constrained workstation. New modules must have at least 90% coverage;
preserve existing global floors, no skipped/deselected cases or gate weakening.

Planning evidence consists of current-source inspection and focused plan
reviews only. It cannot establish runtime, race, worker or provider behavior.
No local sheet exports are present. If exports appear before roadmap editing,
update and verify the existing XLSX and CSV together.

## Risk, reviews and human focus

Risk L1: public architecture, immutable policy lineage and catalogue claims.
Plan and implementation reviews cover architecture, security, QA,
product/operations, senior engineering and reuse/dedup as required by the
adopted contract. Combine related tracks in bounded assignments and report
their distinct conclusions. Add docs review for current navigation and
CI-integrity/test-delta review for actual lane/test changes. Shared checks run
once before clean-candidate implementation review.

Human focus: the exposed catalogue must describe only supported behavior;
the structural criteria-presence check cannot stand in for work-quality
judgment. No new human product decision is needed to preserve the registered
structural set and explicit capability gaps. Any new substantive evaluator or
external provider requires its own scoped implementation decision.

## Reconciliation and remaining work

PR #387 completed CP05; #388's shared-acceptance prerequisites remain intact.
This chunk advances the selected unified-guide path, not live post-submit
execution or false-policy acceptance. On implementation merge, record exact
capability and API outcomes in the roadmap and advance next work to POL-04B.
Until implementation evidence exists, retain Planned and do not describe the
catalogue, modern context checker or execution contracts as delivered.
