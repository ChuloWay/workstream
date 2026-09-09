# WS-ARCH-001-04A — Registered post-submit contracts for unified guide setup

- Initiative: WS-ARCH-001
- Durable disposition: Complete
- Intended merge outcome: CHECKERS exposes its versioned post-submit catalogue and immutable phase contracts, with conformance evidence for its registered structural implementations; live unified setup remains POL-04B.

## Intent

Advance the unified Project Guide path using the adopted dependency contract.
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
  `test_conformance.py`, `test_public_boundary.py`, `test_compiled_policy.py`,
  `test_input_bounds.py`, `test_requirement_dispositions.py`.
- `tests/test_project_guide_compilation_contracts.py`, `tests/test_checkers.py`
  only for focused historical parity controls; no bulk rewrites.
- `scripts/test_lane_catalogue.py` and `tests/test_ci_lane_catalogue.py`: additive
  registration and exact ownership expectation for new test modules.
  Existing lane ownership and required collection remain unchanged.
- `scripts/behavior_ownership.py` and repo-root
  `.ci/behavior-ownership/partition.v1.json`: register exactly the five new
  CHECKERS executable targets in the existing additive partition; preserve
  every existing assignment, protected base, and enforcement rule.
- `.ci/module-boundaries/private-edge-debt.v1.json` at repo root: remove an
  actually eliminated PROJECTS-to-CHECKERS private edge; never add exceptions.
- This record, its adopted chunk pointer, ARCH/POL overviews and ARCH planning
  map, `.commitrail/INDEX.md`, `docs/roadmap_status.md`, and
  `docs/architecture_checker_framework.md`,
  `docs/spec_chunk_8_submission_artifact_policy_checkers.md` and
  `docs/template_checker_policy.md` for accurate intended outcomes and explicit
  v1/v2 configuration guidance.

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
definitions declare those facts explicitly. The exact bounds below become immutable definition fields and must be covered
at their boundaries before the catalogue is usable. They constrain the new
contract only; legacy input shapes do not gain new live limits in this chunk.

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
POL-06 owns invoking the dormant v2 compiler and persisting the approved
canonical post-policy body; 04A owns its pure compile/parse contract below.

### Exact version and compiler contract

One internal registry is keyed by `(checker_id, implementation_version)`.
Existing name-only `register`/`run` behavior is explicitly pinned to
`workstream-structural-v1`, including the old policy-context handler. It must
not mean latest. Version-aware registrations resolve an exact pair and reject
an absent pair. Keep metadata and callable in the same registration entry;
public exports contain metadata only, never a per-checker callable API.

The current snapshot has nine definitions, all with definition version `v0.2`.
Eight resolve `workstream-structural-v1`; the modern policy-context definition
resolves `workstream-policy-context-v2`. The legacy policy-context pair remains
resolvable for pinned historical consumers but is absent from the current
snapshot. Thus nine advertised definitions resolve from ten registered pairs.
No implicit alias or fallback may replace an unavailable pinned version.

Exact identities:

- Catalogue ID: unchanged `workstream.post_submission_checkers`.
- New source version: `v0.2`; projection schema:
  `post_submission_checker_capability_projection.v2`.
- New compiler: `workstream-post-submit-compiler-v0.2`; compiled body schema:
  `post_submit_checker_policy.v2`.
- Empty configuration schema: `post_submit_empty_configuration.v1`.
- Detached input schema: `post_submit_structural_input.v1`; member result
  schema: `post_submit_structural_result.v1`.
- Request/result/current-result-reference schemas:
  `post_submit_evaluation_request.v1`, `post_submit_evaluation_result.v1`,
  `post_submit_current_result_reference.v1` respectively.

CHECKERS public catalogue types own canonical definitions, configuration
validators and the typed compiled v2 body. The existing PROJECTS compiler owns
pure policy compilation using those types. Its new, explicitly named
`compile_post_submit_policy_v2` and `parse_post_submit_policy_v2` entry points
are dormant: no default switch, live caller or persistence in 04A. POL-06
invokes/persists this compiler after approval; it does not create a competing
compiler. Existing v1 compile/parse entry points and their bytes stay unchanged.

The v2 canonical body contains exactly: `schema_version`, `compiler_version`,
`project_id`, `guide_version`, `catalogue_id`, `catalogue_source_version`,
`catalogue_schema_version`, `catalogue_manifest_sha256`, `entries`, and
`blocking_severities`. Ordered entries contain `checker_id`,
`definition_version`, `implementation_version`, `classification`
(`platform_default`, `project_required`, or `project_warning`), and
`configuration` (the registered strict empty object for this snapshot).
Mandatory entries cannot be removed/repeated; project entries cannot repeat
defaults. Recompute `policy_hash` with the existing `canonical_json_hash` over
that exact body. Validate against the supplied pinned snapshot, never global
latest. A new source snapshot cannot change a v1 persisted body's meaning.

The one-way builder `project_guide_post_submission_capabilities_v2` in
PROJECTS consumes the CHECKERS public snapshot and produces the agent-facing
DTO. CHECKERS never imports `app.interfaces.project_agents`. Preserve the v1
DTO and validator unchanged; add a distinct v2 DTO and discriminate explicitly
by `schema_version`, without changing the meaning of the v1 Literal. The
compilation validator uses the pinned source snapshot's canonical configuration
validator. A parity test compares every agent-visible semantic field to its
CHECKERS source and checks the same catalogue manifest hash; no copied rule or
second catalogue-hashing implementation.

### Exact supported definitions and conformance

Every definition has code-owned `state` (`enabled` or `disabled`) and
`disabled_behavior` (only `unavailable` in this version), both included in the
canonical hash and agent-visible projection. All nine current rows are enabled.
A disabled selectable automated requirement remains an explicit capability gap;
it is never bound, skipped or reassigned to human review. A disabled mandatory
default makes v2 compilation unavailable; defaults cannot be omitted or
substituted. Tests may construct a disabled frozen snapshot with its recomputed
identity to reach these guards. No runtime configuration endpoint is added.

All rows use `deterministic` execution, the empty configuration and structural
input/result schemas above. Order is the table order (1-9), dependencies are
empty, provider recovery is `none`, and required generated-output/log roles
are empty. The first eight are mandatory/non-selectable; only the ninth is
project-selectable. None claims substantive task-quality evaluation.

| Order / ID | Supported claim and input slice | Smallest counterexample and expected result |
|---|---|---|
| 1 `check_submission_packet` | Packet presence: summary, package hash, manifest | Blank summary / blank package hash / empty manifest independently -> failed, `packet_fields_missing`, submission_structure |
| 2 `check_policy_context_present` | Observed locked-reference presence/consistency against complete expected refs; structural, not owner authorization | Each observed field absent or different -> failed, `policy_context_invalid`, task_configuration; complete new refs without payment -> passed |
| 3 `check_evidence_present` | Required evidence-key presence: policy inputs and evidence | Remove sole evidence for one required key -> failed, `evidence_missing`, submission_structure |
| 4 `check_evidence_integrity` | Structural path/hash/reference consistency: manifest and evidence | Duplicate normalized path, malformed hash token, or referenced evidence missing hash -> failed, `evidence_structure_invalid`, submission_structure |
| 5 `check_required_files` | Required path presence: policy inputs and manifest | Remove required path -> failed, `required_files_missing`, submission_structure |
| 6 `check_forbidden_files` | Forbidden pattern detection: policy inputs, manifest/evidence paths | Add matching forbidden path -> failed, `forbidden_path_present`, submission_structure |
| 7 `check_confidentiality_attestation` | Required attestation-token presence | Remove one required term -> failed, `attestation_missing`, submission_structure |
| 8 `check_low_quality_generated_artifacts` | Placeholder-signal detection in summary/attestation/manifest/evidence labels; advisory by default | Add existing registered placeholder pattern -> warning, `placeholder_signal`, submission_structure |
| 9 `check_acceptance_criteria_present` | Nonblank criteria text, not criteria satisfaction | Blank criteria -> failed, `acceptance_criteria_missing`, task_configuration |

All passing results have severity `info`, all failures `high`, and the
placeholder warning `medium`, preserving the structural handlers' current
severity semantics. Failure-category and result-code values are exactly the
ones in the table plus `none`/`passed`; no definition advertises arbitrary
additional failures.

Each row has an otherwise complete, clean passing fixture with result `passed`,
code `passed`, failure category `none`. The modern policy-context fixture
compares observed fields to expected complete references; optional observed
fields permit the negative to reach this checker rather than fail schema
construction first. The historical context fixture retains its payment-field
requirement and executes its exact pinned old handler. Test handler swapping
and always-pass mutations, not just output-schema acceptance. Generated-quality
warnings remain subject to the locked policy's existing severity/blocking
rules; this chunk does not route them.

### Detached input and closed outcome shape

`PostSubmissionStructuralInput` is an immutable CHECKERS-owned value composed
of summary, worker attestation, package-hash text, criteria text, a tuple of
manifest entries, a tuple of evidence entries, policy inputs and observed
locked-policy references. No TASK ORM, session, mutable mapping or lazy load.
TASK/ART/PROJECTS will resolve and construct these facts in their later owning
integration; 04A fixtures construct controlled values directly.

- Manifest entry: `artifact`, `hash`, optional `notes`, optional strict integer
  `size_bytes`. Evidence entry: `label`, optional `uri`, optional `hash`,
  `type`, plus four optional string keys `key`, `policy_key`, `evidence_key`,
  `required_evidence_key`. No arbitrary evidence metadata.
- Policy inputs: tuples `required_evidence_keys`, `required_artifact_paths`,
  `forbidden_artifact_patterns`, `required_attestation_terms`. These are detached
  values derived from the exact effective policy, not an alternative compiler.
  Later owning resolution verifies that derivation against the stored policy.
- Required expected context: project/guide ID and guide version; source ID/hash;
  compilation ID/result hash; effective-policy ID/hash; pre-policy ID/bundle
  hash; post-policy ID/version/hash; review-policy ID/generation/hash;
  revision-policy ID/generation/hash; ContributionPolicy version ID. Observed
  context mirrors each field as nullable to represent missing source facts.
  Expected context has no optional required member and no payment reference.
- Request fields: schema version, evaluation-request ID, evaluation generation,
  project/task/assignment/Submission IDs, positive Submission version, ART
  content and binding IDs, content SHA-256 and byte count, expected context,
  the pinned catalogue, complete typed compiled post-policy body, structural
  input, and request SHA-256. Canonical request hashing excludes only its own
  digest and includes every detached value/reference. Duplicated project,
  guide, catalogue and post-policy identities must agree.

Freeze nested containers as tuples/frozen typed values using existing immutable
JSON support only for the strict registered configuration object. Reject extra
fields throughout. Member result contains exactly checker ID, definition and
implementation versions, status (`passed`, `warning`, `failed`), the closed
code listed above, failure category (`none`, `submission_structure`,
`task_configuration`), severity (`info`, `low`, `medium`, `high`, `critical`),
and bounded integer counters. Counter keys are only `artifact_count`,
`missing_count`, `invalid_count`, `matched_count`. No raw messages, paths,
URIs, free text or legacy arbitrary metadata leave the typed result adapter.
Result validation enforces status/code/category combinations per definition.

Phase result contains schema, request ID/digest, attempt ID, evaluation
generation, result ID/digest, outcome (`completed`, `infrastructure_failed`),
member results and nullable infrastructure failure code. Completed results
contain exactly the locked plan's members in order with matching versions and
no infrastructure code. Infrastructure failure uses one of
`capacity_exceeded`, `deadline_exceeded`, `implementation_unavailable`,
`invalid_output`, and no member results. It never assigns contributor failure.
The current-result-reference contains schema, request ID/digest, attempt ID,
evaluation generation and result ID/digest. It describes a later owner-issued
reference, not a self-authorizing `is_current` flag. Neither type proves DB
uniqueness, ownership, revocation or acceptance.

### Fixed bounds and their meaning

All new shapes reject bool-as-int. Canonical encoded request (including input,
policy and catalogue) is at most 1,048,576 bytes; canonical phase result at most
65,536 bytes and each member result at most 4,096 bytes. Manifest/evidence
collections are each at most 1,024 items; each policy-input tuple at most 256.
Text ceilings are Unicode code points: summary/attestation/criteria 65,536;
artifact path/URI/policy-input token 1,000; label 200; notes 4,096;
evidence-type/key values 200; structural hash text 128. Blank/malformed
structural text remains representable for handler failure tests. Authoritative
SHA-256 fields instead require the existing exact prefixed 64-hex form.

Guide version and post-policy version are nonblank opaque strings of at most
50 code points, matching the existing String(50) owners. The post-policy
version equals its guide version; duplicated references must agree. Submission
version and evaluation/review/revision generations are positive strict integers
of at most 2,147,483,647. Compiler/definition/implementation versions are the
exact string identities above. UUIDs are strict.
Declared content/manifest size is 0..9,223,372,036,854,775,807 bytes, matching
signed database size capacity; this is a reference bound, not permission to
load that many bytes. No content bytes are loaded in 04A. Result counters are
0..1,024. Current snapshot/plan supports at most nine entries, at most one
result per entry, zero generated output bytes and no arbitrary nested JSON;
configuration is empty. Input limits fail before handler invocation and become
infrastructure capacity failures in the future executor, not failed work.

Each definition declares a 5,000 ms deadline; the whole phase declares a
45,000 ms aggregate ceiling. These are contract limits for ARCH-04C's bounded
execution/isolation and deadline enforcement, not claims that a Python value
schema preempts synchronous CPU work. 04A proves finite input validation and
real handler conformance only; its production phase port remains unavailable.
Boundary tests cover exact limit and limit+1 independently plus bool-as-int;
where an inner limit is tested, keep aggregate input below its ceiling.

Local consistency checks reject crossed duplicate/nested references even if
the outer digest is recomputed. A coherently substituted entire foreign fact
set can still be a valid value contract. Tests must demonstrate that distinction;
its authoritative rejection requires later TASK/ART/PROJECTS resolution and
exact AUTH checks before any real execution. No live execution is reachable
until those owners prove stored composite ownership and current authority.

## Acceptance criteria

Focused implementation tests now cover these contracts. Each negative starts
from the same complete passing fixture, changes one property, and asserts the
specific rejecting boundary. Hosted integration remains separate evidence.

| Proof | Valid control and counterexample |
|---|---|
| `test_catalogue_matches_registered_versions` | Every advertised definition resolves; independently remove a handler, change its version, repeat an ID, or change order/dependency and deny. |
| `test_catalogue_hash_binds_semantics` | Fixed canonical snapshot is stable; each semantic-field change changes identity; mutation of exported nested values cannot change the stored snapshot. |
| `test_binding_uses_registered_configuration` | Empty config succeeds for the supported selectable check; unknown parameter, wrong stage/version, disabled definition, platform default selection and unknown capability each deny. |
| `test_structural_conformance` | Call the real registered handlers for all nine definitions. Nonblank criteria pass the presence claim; blank criteria fail it. Structurally valid poor work is never reported as substantive quality proof. |
| `test_modern_policy_context_without_payment` | Complete modern refs with no payment row pass the new version. Independently omit/cross each required reference and fail. Pinned legacy-version control retains its original behavior. |
| `test_request_digest_and_lineage` | Fully coherent request passes; cross duplicated/nested project/guide/catalogue/policy identities while recomputing the outer digest, and assert the specific consistency error. A fully coherent foreign fact set remains structurally valid; later owner resolution must reject unauthorized use. |
| `test_post_port_unavailable` | Valid request reaches the unavailable guard. ART/provider/DB spies see zero calls; malformed input alone is not proof of this guard. |
| `test_result_is_not_currentness_or_acceptance` | Matching typed result reference succeeds; wrong request/digest/generation and invalid outcome shape deny. A completed value alone supplies no writer/route/acceptance capability. |
| `test_historical_compilation_and_policy_hashes` | Existing v1 examples preserve byte identity/hash and parameter rejection; new snapshot cannot be injected into old replay or selected as an implicit latest version. |
| `test_requirement_disposition_is_preserved` | Explicit unbound `human_review` is valid. Unsupported requested automation remains `post_submit_capability_gap`, has no binding and cannot become approval-ready. Add a binding to either disposition and deny; never rewrite a gap to human review. |
| `test_agent_projection_matches_canonical_catalogue` | Every v2 agent-visible field and manifest hash matches the public CHECKERS snapshot; changed/omitted semantic fields deny parity. v1 parser/hash controls remain unchanged. |
| `test_input_and_result_bounds` | Exact-limit inputs pass and limit+1 fails for each input scalar/collection and the reachable request aggregate guard; malformed nested fields and noninteger limits deny independently. Maximal closed result shapes remain below the declared byte ceilings; no unreachable result-byte guard is claimed. |
| `test_public_api_has_no_private_owner_types` | Public imports expose immutable contracts only, one post command and no individual-checker product API; existing pre-submit contracts remain unchanged. |

For configuration, modern-lineage and requirement-disposition guards, remove
the particular guard
in a temporary test-of-the-test probe and require the named regression to fail
for its intended assertion. Restore source before shared checks/review.
Conformance tests exercise implementations, not a fake returning success.
Substantive-invalid-work proof is required only when implementing an evaluator
that actually claims substantive evaluation; none is added by this change.

## Evidence

From `backend/`, run the focused implementation checks:

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

The focused suite covers contract/compilation cases across the five new
CHECKERS modules. The declared member and phase result byte ceilings are
upper bounds: closed fields/cardinality limit a member to 607 canonical JSON
bytes and a completed phase to 5,972 bytes. The maximal-shape regression proves
these tighter bounds without unreachable byte guards. Input aggregate-limit tests reach
the actual byte guard independently. Plan reviews establish contract
feasibility only; no worker, database currentness or provider behavior is
claimed by this change. Exact-head hosted and implementation review evidence
belongs in the PR.
No local sheet exports are present. If exports appear before roadmap editing,
update and verify the existing XLSX and CSV together.

## Risk and review routing

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
execution or false-policy acceptance. Its intended merged outcome is the hidden versioned catalogue, dormant v2
compiler, detached phase facts and registered structural conformance. Next
work is POL-04B live unified setup; no worker/route default is changed here.

## Review findings incorporated

The first focused plan review identified missing exact registry/version
selection, v2 compiler/type ownership, detached input/result shapes, numeric
bounds, per-handler conformance and human-review/gap proof. The design now
fixes those choices and distinguishes local fact consistency from later stored
composite ownership and AUTH checks. Subsequent review also corrected the
existing string version types and made disabled-definition fixtures explicit
through hash-bound state/disabled behavior. Implementation preserves those
decisions; contract and handler conformance do not imply live phase execution.

## Implementation scope and proof limits

This is one cohesive public-contract boundary with no migrations or live
activation. The diff exceeds the preferred small L1 line guideline because
it includes closed catalogue/policy/input/result schemas and independent
per-handler, lineage, version and bound tests. Splitting those mutually
constraining value contracts would leave the guide consumer without a complete
reviewable contract. Review tracks receive bounded ownership/proof scopes.

The historical runner remains name-pinned to v1. Modern policy-context checking
compares detached observed references to complete expected references; this
proves structural consistency only. The future owner resolvers must prove
that those references and detached policy values match stored composite
ownership before real execution. Catalogue budgets are finite declarations;
worker deadline/isolation enforcement remains ARCH-04C. No new substantive
evaluator or automatic acceptance is provided.


Implementation review refined the contract in four places. Resource metadata
uses exact integer literals so it cannot advertise limits the schemas do not
enforce. Definitions reject repeated dependencies before canonical hashing.
Private read-only protocols distinguish common structural input from the
legacy locked-context shape. The modern adapter normalizes valid copied paths
before the registered handler detects duplicates, while invalid paths still
reach its bounded failure and original request facts and v1 behavior remain
unchanged. A self-hashed catalogue is still identity, not installation proof;
POL-04B/POL-06 must obtain the pinned snapshot from the trusted CHECKERS builder.
