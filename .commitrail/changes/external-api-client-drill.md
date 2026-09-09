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

Allowed: `backend/scripts/external_api_drill.py`, its focused tests under
`scripts/test_external_api_drill.py`, this record and a usage document under
`docs/engineering/`. Generated reports stay outside Git. Reuse the existing
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
scenario on failure, preserve results and classify remaining OpenAPI operations
as untested. Never count an expected denial as a successful positive operation.
Record Git target, local-only authentication/storage limitations, setup actions,
named assertions and sanitized method/route/status results. Do not save tokens,
raw response bodies, source contents or secrets. Use create-once report output.
Always terminate the owned server; the isolation runner drops its owned DB/role.

## Acceptance criteria

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
