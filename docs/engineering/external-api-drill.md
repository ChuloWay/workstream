# External-client API drill

`backend/scripts/external_api_drill.py` is separate from the older API contract
drill. It uses a real local HTTP server, real token verification and PostgreSQL.
It does not seed product rows, disable guards, import the old drill or fake
agent/provider results. Initial Access Administrator bootstrap uses the existing
documented CLI and is recorded as setup, not an HTTP capability.

## Run

Use a disposable local PostgreSQL server, never a deployed database. From
`backend/`, with an existing private output directory and the administrative URL
in `WORKSTREAM_TEST_ADMIN_DATABASE_URL`:

```sh
WORKSTREAM_ENVIRONMENT=local .venv/bin/python scripts/run_isolated_tests.py \
  --metadata-json /absolute/private/output/database.json \
  --timeout-seconds 480 -- .venv/bin/python scripts/external_api_drill.py \
  --isolation-metadata /absolute/private/output/database.json \
  --report /absolute/private/output/report.json
```

The runner creates/migrates an isolated database and restricted role, then drops
both. The drill verifies matching runner metadata and connection identity and
requires an empty actor registry. The output file must not already exist and
must be outside the repository. The child server rejects an ambient backend
`.env` file, binds only loopback, and receives fresh test-only HMAC secrets.
No production Flow credentials, external model calls or storage providers are
used. The caller is responsible for stopping its disposable PostgreSQL server.

Run helper tests from the repository root:

```sh
backend/.venv/bin/python -m unittest scripts.test_external_api_drill
```

## Interpret evidence

The separate `backend/scripts/admin_api_drill.py` entry point reuses this runner
for twenty HTTP-created human profiles, bootstrap and administrative authority.
Run the same isolated command above with `scripts/admin_api_drill.py` in place
of `scripts/external_api_drill.py` and allow a 900-second timeout for rate pacing.
It performs actual local bootstrap CLI calls and read-only isolated-database
snapshots to check forbidden authority/state changes. All later mutations use
HTTP. The original no-product-SQL-write/no-disabled-guard rules still apply.
`local_evidence` cases are CLI/state assertions, not additional HTTP endpoints.
Concurrent calls demonstrate observed outcomes, not forced database lock overlap.
Self-removal denials do not prove direct execution of the later count-based
last-administrator guard. Missing groups remain incomplete, never certified.

Run its helper checks with
`backend/.venv/bin/python -m unittest scripts.test_admin_api_drill scripts.test_external_api_drill`.

The OpenAPI manifest inventories nested request/response fields. Each operation
records its executed cases, asserted fields and uncovered fields. These are
partial behavioral observations, not exhaustive schema certification:

- `partial_positive`: at least one successful HTTP case, not full readiness.
- `denial_only`: expected refusal observed; no successful use established.
- `failed`: a scenario assertion or request failed.
- `untested`: no case executed for that operation.

Even a field with a passing case can still need omission, boundary, invalid-type,
cross-field, persistence or permission proof. No operation is promoted to fully
verified by this initial slice. Successful-only counts must never hide failures.

Initial cases cover token rejection, self-profile field values/bounds/nulls and
readback, administration/grant discovery, project creation/replay/conflict,
ungranted read denial, draft guides, initial review/revision policies and grant
revocation. Other methods, nested policy fields and response fields remain
explicitly uncovered. Add independent scenarios as current APIs become reachable;
never manufacture active-guide, task or acceptance state to complete a report.

Extended cases check profile omission and normalization, response shape and
identity, policy replacement with a current selector, project length limits,
project-role access and revocation, service provisioning and identity-link
lifecycle. The client paces mutations against the default server rate budget;
it does not disable rate controls. Independent boundary failures are retained
while other independent probes continue, and any such failure keeps exit status
nonzero. A stored idempotent replay is not treated as current-state readback.

This does not prove deployment connectivity, real Flow integration, S3 custody,
model quality, the unified setup pipeline, or end-to-end acceptance. Storage and
automatic setup execution are disabled. A successful partial run cannot certify
those surfaces for an MCP adapter.
