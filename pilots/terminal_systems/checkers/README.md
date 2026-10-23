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

Publish through the same command with `--publish --account-id` and the intended
AWS account. Its default destination is `workstream-checker-pre-terminal-systems`
in `eu-north-1`. The reviewed implementation was published on 2026-10-23 as:

```text
094032936130.dkr.ecr.eu-north-1.amazonaws.com/workstream-checker-pre-terminal-systems@sha256:24d8d0ad46e1f10c85d8883ddd29bcc7708501e560df067cdd3fdab34785a83c
```

The publisher pulled that exact manifest back and passed all seven samples with
config image ID `sha256:85f32d02a7febd1b476810f5cb7cd0b6056a9b29c377f78e492b005b23a81aef`.
The local rehearsal registry entry is `01a1665b-892e-7a56-a511-6fd9be45a60a`,
created through the Operator CLI. These are image publication and registry facts,
not deployment or activation. Runner cache provisioning, corrected proposal
approval and activation remain separate operations. Local `docker-dev` samples
do not establish hosted gVisor isolation.

## POST prerequisites

POST engineering is in progress against the retained six model and two execution
suggestions; those counts describe the historical handoff, not an eligibility
set or approval. The project agent now has strict material/rubric validation, a
bounded source-cited plan, invocation-local model-session and execution-socket
clients, protected build/state projections, and receipt-bound runtime and author
assessment cores. The shared runner has a generic offline Kaniko/runsc trial
engine with resource, cancellation, cleanup and recovery controls. Provider-free
tests and a real engine qualification are development proof only: the complete
model→trial→retained-receipt→model flow has not yet completed a controlled
provider qualification, and this POST image has not been published, registered,
approved or activated.

The author-accuracy draft adds `reproduction_procedure_unavailable` for the
narrow case where an absent or ambiguous exact procedure prevents authenticated
comparison. It reports incomplete coverage; it does not call healthy runtime
infrastructure unavailable, invent an unobserved discrepancy, add a guide duty,
or reuse another requirement's finding. The retained setup handoff remains
byte-for-byte historical. The #555 owner must include this exact draft finding
and image contract in a fresh PRE/POST proposal for review before any binding or
activation.

The shared model-account owner retains provider budget/effect custody and the
durable receipt resolver. TASK/ART/CHECKERS owners supply authenticated revision
context and predecessor material; project code does not query their private
tables. Credentials stay outside the sandbox, nested submitted code receives no
relay sockets, and all model/trial unavailability remains infrastructure rather
than a contributor finding. Do not publish passing substitutes or treat this
engineering checkpoint as the live contribution journey.
