# Workstream CLI

An independent Go client for Workstream's public REST API, for humans and
agents using the terminal. It provides human self-profile reads and editing,
plus exact-project inspection and authority reads:

| Command | Public API |
|---|---|
| `workstream whoami` | `GET /api/v1/actors/me` |
| `workstream profile update` | `PATCH /api/v1/actors/me` |
| `workstream project access PROJECT_ID` | `GET /api/v1/actors/me/authorization-context?project_id=PROJECT_ID` |
| `workstream project show PROJECT_ID` | `GET /api/v1/projects/PROJECT_ID` |

Workstream verifies the caller's Flow bearer and owns identity resolution,
authorization and lifecycle decisions. Reading a profile can admit a first-time
caller and update server-owned last-seen/audit data. Project access is a current
snapshot; each later API operation must independently authorize the caller.

## Build and use

Use Go 1.27.1, matching `go.mod` and CI. From this directory:

```sh
go build -trimpath -o /tmp/workstream-cli ./cmd/workstream
export WORKSTREAM_API_URL=https://your-workstream-api.example
# Supply WORKSTREAM_TOKEN through your existing secret environment mechanism.
/tmp/workstream-cli whoami
/tmp/workstream-cli project access PROJECT_ID --output json
/tmp/workstream-cli project show PROJECT_ID --output json
```

`WORKSTREAM_API_URL` is the API origin, without `/api/v1`, credentials, query or
fragment. HTTPS is required except for loopback HTTP during local development.
`WORKSTREAM_TOKEN` contains the caller's unprefixed bearer value. It is forwarded
unchanged in the Authorization header. Avoid putting tokens in shell history;
the CLI reads its environment and does not save credentials. Configure the API
origin you trust to receive that credential. Redirects and ambient HTTP proxies
are disabled; system certificate verification remains enabled.

The binary runs independently of Python, the backend source tree and MCP. The
source package is buildable; published binaries, installers and signing are a
later release boundary. The [CLI initiative](../.commitrail/initiatives/WS-CLI-001/OVERVIEW.md)
describes subsequent public workflows and an optional TUI.

## Output and automation

Commands need no TTY or interactive prompts. Default human output escapes
terminal control characters in API text. `--output json` (or `-o json`) writes
the successful API object to stdout without a wrapper. Failures leave stdout
empty and write bounded error metadata to stderr; JSON errors use an `error`
object with `code`, optional HTTP `status`, and optional `correlation_id`.
For machine-readable argument errors, place `--output json` before the command;
flag parsing can stop at an invalid argument before reading later flags.
Raw error bodies and transport exceptions are not printed.
Server error codes and correlation headers containing the caller's bearer
are suppressed, including case-only reflections. Success responses require
valid UUID identities and non-null string array members. Project access compares
UUID identity rather than spelling, while sending the supplied selector unchanged
and preserving the successful API JSON.

Exit status is `0` for success, `1` for API/network/response failure, and `2`
for invalid arguments or configuration. A request times out after 12 seconds;
responses are bounded to 64 KiB and requests are not automatically retried.
Use `--help`, `--version` and `completion bash|zsh|fish|powershell` without a
credential or network connection.

## Inspect a project

Use `workstream project show PROJECT_ID` for a project whose ID you know.
Workstream selects the response: an exact contributor grant receives only
`id`, `name` and `status`; applicable administrative authority receives those
fields plus `slug`, nullable `description`, `created_at` and `updated_at`.
The CLI prints only the returned fields and never chooses a projection from
cached roles. `project access` remains a separate snapshot, not a preflight
or an authorization token for `project show`.

Project selectors must be UUIDs of at most 100 bytes. Supported compact, brace and `urn:uuid:`
spellings are sent as one escaped path segment and compared by UUID identity.
Invalid selectors fail before any request. Success requires a complete public
response shape, with no duplicate or unknown fields, null required strings,
invalid timestamps or mismatched identity. JSON output preserves that API
object; text escapes terminal controls. Foreign or revoked authority remains
a server denial with empty stdout, not an empty successful project.
This command does not list projects, edit setup, activate guides or claim tasks.

## Edit your profile

```sh
workstream profile update --display-name 'Ada' --contact-email 'ada@example.test'
workstream profile update --clear-contact-email --output json
```

Only human caller-owned `display_name` and `contact_email` are writable.
An omitted flag leaves its field unchanged; a clear flag sends explicit JSON
null. You can also use `--clear-display-name`. Select at least one field; setting
and clearing the same field is invalid. Text must be valid UTF-8 and the JSON
request is capped at 8 KiB. Workstream validates and normalizes the text:
display name has a 200-character limit, contact text 320, and blank or NUL text
is rejected. Contact text does not change your Flow login or identity.
Service-actor editing and authority/lifecycle changes are not CLI operations.

A successful update prints the validated API profile, using the same text/JSON
output as `whoami`. No preflight read or automatic retry is performed, and no
idempotency/version mechanism is invented. If the server might have received
the update but no trustworthy result arrives (including lost connection,
malformed success, redirect or server error), exit status is nonzero and JSON
includes `error.outcome_unknown: true`; text explains the uncertainty. Do not
assume rollback or blindly retry: use `workstream whoami` to inspect the current
profile. That observation cannot establish global order against concurrent
later edits. Complete 4xx replies with a parseable Workstream error envelope
(a nonempty string `error.code`) remain known denials or validation failures,
even when sensitive metadata is suppressed. A gateway 4xx without that envelope
is uncertain too; HTTP status alone does not establish a Workstream denial.

## Verification

Behavior tests invoke the built executable from outside the repository, with
no import of Go internals. One suite uses a controlled HTTP server to exercise
credential/destination safety, output and failure boundaries. The other uses
the current FastAPI app with isolated real PostgreSQL to prove first admission,
profile fields, authorized exact-project context and foreign-project denial.
It also proves persisted profile edits, normalization, omission/null semantics,
field limits, caller isolation and suspended denial. The HTTP fixture proves
the exact PATCH body, invalid local input, redirect refusal and no-retry behavior
when a response is lost after body receipt.
Project inspection adds full/minimal projection parity, encoded selectors and
malformed/substituted response rejection at the process boundary. Real API
proof creates two projects and an exact contributor grant through public APIs,
then verifies foreign-project, revoked-grant and suspended-actor concealment.
Local Flow-compatible tokens are test fixtures, not deployed-provider proof.
No coverage percentage or test-count target is used.

```sh
go mod verify
go vet ./...
go build -trimpath -o /tmp/workstream-cli ./cmd/workstream
# With the backend test environment installed:
WORKSTREAM_CLI_EXECUTABLE=/tmp/workstream-cli python -m pytest -q tests/integration/test_http_boundary.py
# From backend/, with a local disposable PostgreSQL admin URL in the environment:
WORKSTREAM_CLI_EXECUTABLE=/tmp/workstream-cli python scripts/run_isolated_tests.py --metadata-json /tmp/workstream-cli-isolation.json -- python -m pytest -q ../cli/tests/integration
```

The real API fixture uses the documented local administrator bootstrap solely
to arrange test authority, then creates its project through public APIs. These
test dependencies are absent from the shipped CLI. See the workflow for the
complete [hosted check](../.github/workflows/cli.yml).
That reusable check runs in parallel with Backend lanes; its failure also fails
the existing required Backend `test` result. No separate optional PR workflow
or extra branch-protection setting is needed.
