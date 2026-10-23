# Terminal Systems checker implementation

These are project-owned images. They use the standard request/result protocol
and verified read-only material mounted at `/work/input`; they do not import
Workstream, modify the shared Rust service, or depend on the five initial tasks.

## Source specification

[`setup-handoff.json`](setup-handoff.json) retains the actual final reviewed
setup requirements and capability suggestions from compilation
`01a165a2-7cde-7277-b789-7013d7a2088d`. Its source block identifies the unchanged
guide and full result hash. This is an engineering handoff, not an approved
policy or evidence that any proposed capability is already registered.

## PRE image

The `terminal_systems.package_intake@v1` capability supports two distinct locked
configurations:

| Configuration | Evaluation |
|---|---|
| `{"check":"package_layout"}` | Required regular files and directories directly at the package root; useful extra material is allowed. |
| `{"check":"metadata_contract"}` | The documented TOML format, values, declared file/directory types, contained paths and argument-array shape. Commands are never executed. |

Bind each original requirement separately. Each binding uses its own exact
configuration hash and execution budget. The same image may serve both; this
does not collapse the two invocations. The supplied material tree is already
verified/extracted by ART and the shared runner. Project checks inspect its
actual entry types; they do not repeat archive extraction or custody checks.

From the Workstream checkout:

```bash
python3 -m unittest discover -s pilots/terminal_systems/checkers/pre -p 'test_*.py' -v
./scripts/checker-image pilots/terminal_systems/checkers/pre
```

The image has no network, host socket, secrets or writable submission mount.
Python and its TOML parser are packaged in its pinned base. No Rust or backend
package is needed inside the image. Its metadata parser has a 4 MiB execution
capacity; exceeding it produces `capacity_exceeded`, never a contributor size
violation. Platform upload limits remain owned by Workstream.

The sample directories prove structural intake behavior only. Their short
documents and environment placeholders are explicitly not completed task
packages, semantic review evidence, or a substitute for the real project journey.
The image build excludes samples and tests. Findings contain fixed messages and
safe project-relative paths, never raw TOML, commands or exception traces.

After review, publish through the same command with `--publish --account-id`
and the intended AWS account. Its default destination is
`workstream-checker-pre-terminal-systems` in `eu-north-1`. Registration, runner
cache provisioning, corrected proposal approval and activation remain separate
operations. A local `docker-dev` sample pass is not hosted gVisor evidence.

## POST prerequisites

The six model specifications and two execution specifications are not yet
implemented. The user has resumed the minimal budgeted model runtime needed by
this project. It must preserve digest-pinned project images, exact locked
configuration and Workstream-owned lifecycle decisions. Credentials stay outside
the sandbox. Project-budget reservations, provider-call identity and uncertain
delivery recovery must prevent duplicate paid calls and distinguish infrastructure
failure from contributor failure.

Execution additionally needs a generic isolated build/trial capability and
approved offline material. Author-evidence review needs authenticated trial
records; revision checks need the exact prior work and feedback from their
owners. The current one-container runner does not supply these capabilities.
Do not activate this guide or publish passing substitutes while these gaps remain.
