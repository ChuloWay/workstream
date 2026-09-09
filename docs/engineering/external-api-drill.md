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
  --timeout-seconds 300 -- .venv/bin/python scripts/external_api_drill.py \
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

This does not prove deployment connectivity, real Flow integration, S3 custody,
model quality, the unified setup pipeline, or end-to-end acceptance. Storage and
automatic setup execution are disabled. A successful partial run cannot certify
those surfaces for an MCP adapter.
