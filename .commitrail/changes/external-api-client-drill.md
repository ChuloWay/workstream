# External API client drill

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: a reusable real-HTTP inventory distinguishing tested client behavior from untested or unavailable routes.

## Intent

Support an external MCP adapter proposal with observed API behavior, not route
existence or internal fixture success. Do not use the existing API drill: it
seeds downstream state and replaces model execution, which cannot establish
external-client lifecycle readiness.

## Bounded change

Allowed: `backend/scripts/external_api_drill.py`, `backend/scripts/admin_api_drill.py`,
`backend/scripts/admin_guard_probe.py`, focused tests under
`scripts/test_external_api_drill.py` and `scripts/test_admin_api_drill.py`,
this record, the usage document and the
human-requested `docs/engineering/external-api-drill-findings.md` repair handoff.
Generated raw evidence stays outside Git. Reuse the existing
isolated-database runner and administrator bootstrap, not the old API drill.

No product code, CI, thresholds, provider changes, peer-worktree changes, direct
product SQL writes, disabled guards or model fakes. No existing/deployed
database, production credentials or non-loopback server use. A fresh isolated
database and an explicitly reported initial administrator bootstrap are setup,
not API proof. The tool launches its own server with test-only HMAC identities;
it does not connect to an arbitrary supplied deployment.

## Design

The human requires field-level behavioral proof, not merely endpoint smoke
tests. Maintain a coverage manifest for every public OpenAPI operation and its
path/query/header/body fields, including nested fields and response assertions.
Each field maps to explicit named cases or an honest untested/blocked reason.
Valid values, omission/defaults, nullability, types, bounds, closed enums/extras,
cross-field rules and foreign-resource substitutions require relevant cases;
schema-generated inputs alone do not prove business behavior. Read back mutations
through HTTP to verify persisted values and forbidden side effects. Cover retries,
idempotency conflicts and lifecycle restrictions where the contract has them.
An operation is not fully verified merely because one successful call exists.

Use a small test-only Flow-compatible token issuer inside the drill. Generate
short-lived signed human/service tokens for the actual configured verifier,
including invalid-signature, expired, wrong-issuer/audience and future-not-before
controls. The issuer is an isolated harness component, not a new Workstream
authentication service. Token claims do not supply canonical grants. Establish
authority through the documented initial bootstrap and real administration APIs.
Never require or impersonate the production Flow issuer. Report this distinction.

Require the isolation runner's provisioned metadata and exact derived database
and role names, matching the connection's database/user; verify no actor profiles
exist before bootstrap. Use a controlled child environment and artifact storage disabled initially;
storage/provider-dependent APIs remain untested rather than falsely passing.
Exercise real HTTP identity/profile, administration/grants, project/guide and
policy operations; include replay and unauthenticated/foreign-resource denials.
Every assertion checks status and relevant response values. Stop a dependent
scenario on failure. Independent boundary probes may collect separate failures
and continue; any collected failure must still make the final exit nonzero.
Preserve results and classify remaining OpenAPI operations
as untested. Never count an expected denial as a successful positive operation.
Record Git target, local-only authentication/storage limitations, setup actions,
named assertions and sanitized method/route/status results. Do not save tokens,
raw response bodies, source contents or secrets. Use create-once report output.
Always terminate the owned server; the isolation runner drops its owned DB/role.

## Acceptance criteria

### Human-requested administrator deep drill

The human further requests concrete reproductions for the count-guard gap.
Add `backend/scripts/admin_guard_probe.py`, invoked only by the isolated admin
drill, and helper tests in `scripts/test_admin_api_drill.py`. The subprocess
loads the actual stored actors/links/grants, acquires the canonical control lock,
calls the existing grant/profile/link conflict owners, and always rolls back.
It creates no authority, claim handle or fabricated authorization decision.
Verify all four removal checks with one administrator (deny), two (allow),
and one after real HTTP revocation (deny); also test an ineffective second
administrator after HTTP suspension or link revocation, then reactivation.
Keep these owner/transaction checks distinct from HTTP-route enforcement.

In separate short-lived probe subprocesses, deliberately mutate only the
count-comparison boundary from `<= 1` to `< 1` for each of the three owner
methods. Expected probe failure demonstrates that these checks detect the
specific off-by-one defect. No product files or running API process are changed,
no database guards are disabled and no SQL data writes are introduced.
Only read/lock queries against the validated owned database are permitted.
Named proof must verify fetched actor/link/grant relationships and the actual
effective count, then assert guard output; pre/post snapshots must remain equal.
Security/QA plan review checks feasibility before implementation; exact clean
run and discriminating mutation evidence precede a completion claim.

Extend the same isolated harness with `backend/scripts/admin_api_drill.py` and
`scripts/test_admin_api_drill.py`. Add a scenario callback to the existing runner
instead of duplicating server/credential/database lifecycle code. This slice
creates twenty separate human profiles through HTTP with two bootstrap candidates,
all five admin roles, system/project-scoped variants, submitter/reviewer and
ungranted/lifecycle targets. Roles come from actual grants, never token claims.
The peer repair worktree owns the five previously recorded product defects;
do not edit its files. Communicate newly reproduced findings without taking over
product repairs. No roadmap capability changes are implied by this test tooling.

Before any grant: exercise bootstrap invalid target, dry-run with unchanged
authority state, concurrent execute with one winner, and later-conflict behavior.
Use actual CLI subprocesses and permit read-only SQL evidence snapshots on the
already verified isolated database for bootstrap/control/audit and forbidden
side effects. No SQL writes, fixtures, disabled guards or imported product tests.
Then use real grant APIs to establish and test role/scope boundaries, self-grant
and self-revoke, idempotency/replay, cross-project concealment, actor and link
revocation, and last-effective-admin protection. Create two real projects via a
system Project Manager. Finish by leaving one effective admin and verify every
reachable removal route refuses it. Do not claim role catalogue membership proves
unimplemented finance/review/task operations; probe only reachable public routes.

`admin_api_drill.py::scenario` owns these future cases. Its roster and result
assertions require helper tests, a clean exact-target live run, and focused
security/QA review including a falsified-response probe. Existing failures remain
failures; independent groups continue when safe, dependent groups stop on broken
prerequisites. Record blocked/unexecuted scope distinctly. About twenty profiles
means separate identities/subjects, not twenty fabricated grants or DB seed rows.

- No import or invocation of `api_contract_e2e`; no trigger suppression or
  direct product-state seed. No calls to hidden routes to claim public support.
- Wrong status/body/replay identity produces failure and nonzero exit, with a
  report distinguishing successful calls, expected denials and untested routes.
- A real local HTTP run is required; unit tests alone never certify APIs.
- Reports enumerate uncovered OpenAPI operations, not a blanket readiness claim.
- The field manifest accounts for every discovered parameter/request field and
  distinguishes executed behavioral assertions from schema-only observations.
  No operation earns full verification while required field cases are missing.
- Dedicated helper tests prove status classification, response checks and
  external-target rejection. Local execution never constitutes live Flow/S3 proof.

## Risk and review routing

- Risk class: L1 (test credentials, administrative mutations, evidence quality).
- Required reviewers: focused security/architecture plan review; QA/test-delta
  and security implementation review; documentation for usage/report limits.
- Human focus: isolation, truthful readiness, no manufactured lifecycle state.

## Evidence

Run focused unit tests and the new drill through `run_isolated_tests.py` against
a private temporary PostgreSQL instance. Check links, stale wording, record and
diff integrity. Full backend tests are unchanged; no blanket product certification.
The roadmap needs no capability change: this adds verification tooling only.

## Initial evidence and remaining scope

The first committed real-HTTP slice exercised 104 assertions across 23 operations:
54 successful calls and 50 expected denials. The full 77-operation OpenAPI
inventory retained 54 operations as untested; field-level completeness is not
claimed. Both isolated database and role cleanup were verified. The complete
all-field/API audit remains Planned, not delivered by this first slice.

Focused review found a future false-summary risk: a later passing case could
overwrite an operation's prior failure. Failure is now sticky, with fail-then-
success and fail-then-denial regression proof. No existing product tests or
guards were changed. Unit tests live at the explicitly root-relative
`scripts/test_external_api_drill.py` and run with the backend virtual environment.

The continuing drill adds exact self-profile response shape and identity checks,
omission/normalization/readback probes, real policy-selector advancement,
project/database length boundaries, project-role access and revocation, service
provisioning and identity-link lifecycle. Request pacing respects the default
mutation budget without raising server limits. Schema inventory remains distinct
from semantic verification; these extensions do not certify every public field.

Focused review additionally required recursive type-strict response comparison
and current-state verification after a denied guide edit. Both are incorporated;
nested boolean/integer coercions have dedicated helper regressions. Failed
project-role issuance also checks that no active grant or project access survives,
and failed oversized creates are followed by corrected same-key requests to
probe idempotency rollback. No expected product failure is relabeled as a pass.

The human clarified that v0.1 has only submitter and reviewer project roles.
The earlier probe followed the public enum's adjudicator option; that option
must now be treated as unsupported input, not functionality to complete. The
handoff records its existing 503 and remaining contract cleanup. Product repairs
belong to another agent. After those merge, rerun this drill on their exact main
head and finish outstanding field coverage before the MCP endpoint handoff.
