# Hosted Smol project execution

- Initiative: `None`
- Durable disposition: `Planned`
- Intended merge outcome: Replace the hosted Docker/runsc project controller with the existing native Smol node for typed trusted intake, ordered non-model PRE checks and authorized model-enabled POST checks.

## Intent

Give the hosted release one explicit Smol execution boundary without a fallback runtime or a second controller. Preserve the existing ART, CHECKERS, MODEL, AUTH and TASK ownership of material, grants, paid effects, immutable evidence and governed outcomes.

## Current behavior

`deploy/hosted/compose.yml` starts a networkless controller container with the host Docker socket. `preflight.py` requires runsc and Docker image-cache inspection. Trusted intake already uses a native Smol service through a separate typed capability. API and worker mount absolute scratch/socket paths; project execution uses the existing typed `ExternalCheckerExecutionAdapter` and factory.

Current main `fcd32057b` rejects Smol model grants. The pending runtime change in PR #677 owns guest-native model/trial transport, predecessor material, child VM custody and resource enforcement. This hosted change consumes that implementation and cannot establish its qualification independently.

PR #690 at `f3f818265`, incorporated in main `fcd32057b`, owns provider selection and replacement credential overlays. This change preserves that existing dependency rather than creating another provider-selection path. Provider source behavior remains outside this change.

PRE model access is unsupported: `configured_model_profile_selector` rejects model selectors outside `post_submit`; `ModelAwareExternalExecution` and `model_execution_facts` require durable POST lineage. Selected PRE currently invokes the ordinary execution adapter without a model grant. This change preserves that rejection and does not claim PRE model support.

## Bounded change

### Allowed

- `deploy/hosted/compose.py`, `compose.yml`, selected provider overlays, `compose.trials.yml`, `preflight.py`, `checker-service.example.json`, `release.env.example` and `README.md`: replace the controller topology, validate native-node identity/readiness and preserve credential isolation.
- `external_checkers/deploy/workstream-checker.service` and `external_checkers/README.md`: align the existing native service configuration and document operator-managed provisioning and shutdown.
- `scripts/verify_hosted_release_images.py`, `scripts/test_hosted_release_images.py`, `scripts/test_hosted_release_config.py` and existing focused deployment tests: qualify hosted backend images separately from native-node readiness, and exercise the rendered topology and meaningful refusal paths.
- Existing `experiments/pilot04_external_checker_runtime/` public journey helpers and their focused `scripts/` tests: attach to the actual hosted API and durable workers, retain scoped fault injection and verify native acknowledgements without substituting an in-process API or recorded worker.
- `.github/workflows/release-images.yml`: run the new hosted attachment/model qualification refusal tests in its existing frozen backend environment; include their paths without weakening or replacing existing image/runtime proof.
- Owned disposable EC2 qualification resources, source-pinned release builds and isolated database/release records and newly owned content-addressed keys within the existing approved AWS namespace: exercise the rendered hosted release without modifying shared services or production state. Reuse the existing simulated RS256 issuer fixture and label its identity proof accurately.
- `docs/decision_0014_external_service_adapter_convention.md`, `docs/architecture_checker_framework.md` and affected `docs/roadmap_status.md` claims: reconcile the intended hosted boundary and explicit evidence limits.
- This combined change record.

### Not allowed

- No runtime implementation changes in the PR #677 worktree, duplicate guest transport, fallback controller or provider implementation changes.
- No new adapter convention, service locator, backend business policy, schema migration, auth/payment authority, PRE model entitlement or paid retry.
- No shared service restart, `/etc/workstream` change, product deployment, cloud image publication, global cleanup or merge. Activation is limited to the owned disposable qualification database/release and the existing approved artifact namespace; it does not activate the real pilot project.
- Do not weaken existing credential, identity, material, deadline, cleanup or evidence checks to make a deployment fixture pass.

## Design and decisions

1. Use the existing delegated systemd/cgroup Smol service as the sole hosted node. Both typed intake and project execution clients use `/var/lib/workstream/checker-runtime/checker.sock`; their closed protocols and pinned image identities remain distinct.
2. Remove the Compose checker controller and its Docker socket/group grants. API and worker retain the same absolute scratch path and read-only node socket-directory mount. The native process runs as the same numeric UID/GID as the ART grant issuer.
3. Keep model credentials exclusively in the existing trusted model proxy. The native node forwards only invocation-bound guest capability traffic through the PR #677 transport; the project image receives neither global sockets nor credentials.
4. Replace runsc/image-inspection readiness with the existing typed project-execution health capability plus typed trusted-intake health. Validate configured Smol binary/guest/archive identities, native delegation and socket metadata without introducing a deployment controller. Configuration-only mode remains explicitly weaker than live readiness.
5. One trusted `WORKSTREAM_DEPLOYMENT_ROOT` selector derives identical absolute data/socket/model/parser paths on host and clients, defaulting to `/var/lib/workstream`. The root must be canonical, private and owned by the exact service identity; config, provider credentials and executable/cache assets stay outside it. `WORKSTREAM_CHECKER_SERVICE_BINARY` selects one absolute native service artifact under its required digest. This supports independently owned deployments without a test-only controller or validation bypass.
6. Operator provisioning and service lifecycle remain explicit. Compose startup validates the already-running native node; Compose shutdown drains producers/workers but does not stop an unrelated systemd unit. Shared nodes remain untouched; qualification lifecycle is limited to the newly owned deployment.

### Live model qualification authority

The user authorized proceeding with US$10 for the required live model test after
being told that an earlier setup charge remains unresolved. Enforce a separate
hard 10,000,000,000-nanodollar ceiling for this qualification through the existing
project budget and reservation ledger before dispatch. Preserve the earlier
uncertain effect separately; do not mark it free, retry it, reset its accounting,
or count it as reconciled. Record actual settled and outstanding reserved amounts
for the new test. Stop paid dispatch on ambiguous delivery or exhausted budget;
only the existing authorized recovery rules may resolve an effect.

## Acceptance criteria

- [ ] Rendered hosted services contain no checker controller, Docker socket grant or runsc dependency; backend clients use one host Smol socket for the two existing typed capabilities.
- [ ] Hosted configuration rejects Docker/runsc selection, missing or substituted Smol binaries/cache assets, unsafe identities, unbounded capacity and incorrect native socket/delegation.
- [ ] Readiness uses registered typed adapters, validates exact runtime/image identities and fails closed before launch when the native node is unavailable.
- [ ] Provider overlays retain PR #690 credential selection and expose credentials only to the trusted proxy; no provider source behavior changes.
- [ ] Ordered non-model PRE remains supported; PRE model selectors remain unsupported and documented. Model-enabled POST is explicitly dependent on PR #677 and PR #690.
- [ ] Focused contract tests cover valid composition and identity/credential/runtime substitutions. Relevant existing deployment and adapter checks continue to pass.
- [ ] Documentation distinguishes prepared configuration and fixture proof from actual public API/worker, real model, hosted Flow/AWS and interruption qualification. The full public journey remains root-owned evidence.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: architecture/reuse, security, QA/test delta, CI integrity and documentation, routed to the changed boundaries.
- Human review focus: the single native endpoint, preserved absolute paths/UIDs, provider-secret isolation, dependency order and the explicitly unsupported PRE model branch.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Current deployment and typed ownership | Inspect hosted Compose/preflight, existing systemd unit, typed execution/intake adapters and selected PRE/POST owners | Inspected | No hosted operation executed |
| Provider overlap | Read PR #690 at `f3f818265`; reconcile main `fcd32057b` | Existing provider owner preserved | Live provider behavior remains separately qualified |
| Smol callback transport | PR #677 implementation and qualification | Required dependency | Pending runtime integration and root-owned qualification |
| Rendered topology and refusal paths | `python3 -m unittest scripts.test_hosted_release_config scripts.test_hosted_release_images` | 70 passed, exit 0 | Contract/image fixtures; no native VM or provider execution |
| Generated readiness client | Execute the actual generated script using pinned backend Python, real Settings, registered typed factory and a local framed Unix health server | Passed; exact typed health request observed | The responder is a local protocol fixture, not a Smol node |
| Source hygiene | Ruff, Markdown links, stale wording and `git diff --check` | Passed | Does not replace runtime or independent review |
| Public lifecycle and real model behavior | Root-owned public API/Celery journey and scoped live proof | Required before support claims | No EC2 or paid model work performed by this change |

## Review findings

Root plan review of `e07f28b4a`: PASS WITH LOW RISKS for implementation only. The review required exact numeric identity, native/Compose path parity in both directions, native health before API/worker release and explicit drain ordering. Runtime signoff remains separate. The root subsequently approved one trusted deployment-root selector and explicit pinned native binary path because fixed production paths prevented an isolated rendered-topology proof without touching shared resources. Exact UID/GID and live health requirements remain unchanged.

Cold-start inspection found a schema/activation/proxy/node cycle: the proxy reads the activated ART namespace, the native node requires its model socket, and API normally applies migrations. The fixed `migrate`, AWS `proof` and exact proxy-only `up -d model-proxy` stages therefore validate static custody while releasing no application producer/worker; full `up` still requires both typed native health checks. AWS proof itself uses DB/AWS directly and retains its exact existing credential-separated observations.

The actual `docker/backend/release-entrypoint.sh` API role only loads its four role secrets and executes the supplied command; it performs no application startup, activation or readiness call. `backend/alembic/env.py` loads settings and model declarations, then runs migrations against PostgreSQL. A focused entrypoint control reaches its supplied command with absent node/proxy sockets and no model-provider files. This is source/entrypoint evidence, not a fresh-database migration or activation drill. Operator instructions explicitly require root/approved sudo for private input traversal and Docker access; runtime UID/GID `10001:10001` receives no daemon privilege.

Controller-only tests were replaced by native custody/readiness and second-controller refusal proof; API/worker mount, secret isolation, parser and producer/worker drain guards are retained. The generated readiness script was exercised through real Settings and the registered typed factory: the material root requires the matching ART scratch setting, which is now supplied from the same derived path. This proof uses a local framed Unix responder and makes no VM or paid-provider claim.

Exact-head implementation review follows this clean tested checkpoint; no passing implementation verdict is claimed here.

The native-hosted image verifier proves both backend SDK images without requiring
the separate ordinary Docker controller artifact. Its closed evidence explicitly
names that scope; full native preflight still owns service/guest/cache readiness.
The Docker artifact proof remains in CI for the existing local agent-loop owner.
The existing wrapper exposes only exact worker stop/start for the public replay
proof. Stop retains the configured warm-drain period; start revalidates private
inputs and both native capabilities before reconciling that one worker container.
Smol HOME limits use filesystem bytes, matching the pinned runtime socket layout.

## Reconciliation

- Current-source reconciliation: start from main `ae788e6a8`; preserve the pinned PR #690 dependency and reconcile main `fcd32057b`, including its current CLI/roadmap changes; consume PR #677 runtime transport without copying it. The main reconciliation has no source conflicts and changes no hosted executable code.
- Next usable boundary: tested hosted Smol configuration, then dependency integration and independent hosted/public qualification.
- Remaining risks: unqualified live model/Flow/AWS behavior and unsupported PRE model custody must remain explicit.

### Public hosted attachment custody

The public journey driver now attaches to the rendered API, Celery worker, Beat,
parser and optional proxy and verifies their exact image, command, environment,
mounts, ports and isolation. It uses a labelled simulated RS256 issuer and
manager-authored fixture policies; it does not qualify setup-agent behavior or
live model-enabled POST. Duplicate delivery is observed through the production
worker's exact task UUID and immutable database/outbox facts. Original intake
expiry is measured against PostgreSQL time without rewriting its deadline.
The existing preparation deadline is exposed consistently to all hosted roles;
its default remains 3400 seconds and the existing Settings constraints remain.

Independent review reproduced an undeclared writable `/app` tmpfs passing the
initial container validator. The corrected validator matches rendered tmpfs
targets and options, rejects that substitution, and also inspects the actual
parser with its declared capabilities and resource limits. The regression fails
against the earlier validator. Nineteen focused attachment/Smol-proof tests pass;
the root independently inspected the repair and reran its five custody cases.
These are fixture and source checks, not a completed hosted journey.

The existing AWS role grants only the approved `workstream/artifacts/sha256/`
object prefix. Qualification reuses that immutable namespace without IAM changes,
using a separate database/release and nonce-bound challenge objects. Existing
same-digest objects remain untouched. Record newly created durable object keys
and their retention separately from disposable container/VM cleanup; do not
claim deletion of the shared namespace or bypass its immutability policy.

### Bounded live model POST qualification

The public hosted model qualification extends the same inspected deployment and
public guide/submission helpers. One exclusive private proof-state file owns one
isolated project and its immutable US$10 lifetime account; a rerun must inspect
that state, not create another paid project or reset its counters. The existing
Terminal Systems `solver_brief_and_extension_disclosure` image rule supplies a
one-call, model-only POST. Manager-authored engineering source and rubric bindings
remain explicit; this is not a setup-agent or real pilot-project rehearsal.

The OpenRouter profile pins `openai/gpt-5.6-terra`, full-context reservation and
conservative tier/cache rates, one call with finite bytes/tokens/deadline, and no
provider tools. Credentials remain solely in the trusted proxy. The user confirmed
that no optional OpenRouter plugins were enabled. The existing Operator profile,
budget and registry routes, separate policy approvals, public claim/start and ZIP
intake lead to a real Submission and durable Celery dispatch. Actual model output
is evaluated without manufactured findings: a pass follows shared automatic
acceptance, a valid work failure follows revision, and ambiguous/infrastructure
outcomes stop further paid qualification.

Exact public replay and duplicate outbox delivery must preserve checker effects,
model slots, ART request/response evidence and account counters. Retain settled
and outstanding reserved amounts within the total cap; conservative ledger
charges are not represented as an external provider invoice. Any later live
model-plus-trial proof must reuse this same project/account and its remaining
headroom. No separate US$10 allowance or automatic paid retry is introduced.

### Hosted fault-supervisor qualification

The hosted proof separates root-owned operator controls from a fixed
`10001:10001` runtime sibling. The existing node configuration remains mode
`0400` on its original inode and is restored without changing ownership or
permissions. Writes reject file substitution, aliases, extra links and foreign
ancestors. A root-owned sticky ancestor is allowed only above the validated
private directory. Runtime inventory commands drop root and supplementary groups;
the runtime cannot read the operator controls or acquire operator authority.

The root independently reviewed the three-file change at `5e28b089e`.
Twenty-five focused supervisor/attachment tests passed, including refusal of a
FIFO, foreign ancestry and substituted configuration. An isolated EC2 custody
probe confirmed the identity split and exact configuration restoration; that
probe preceded the final nonblocking-open addition, which has focused test proof.
The canonical fresh hosted migration also passed after correcting the unused
fixture secrets to the required padded Base64 encoding. Product validation was
unchanged. These results do not establish the pending public hosted journey or
live model result.

The five-file model qualification at `ea49554b7` passed 37 focused tests. Root
review verified the public profile/budget/registry owners, exact model effect
inspection DTO, paid-slot joins, fixed deployment claim and full lifetime budget.
The exclusive claim is synced with its parent directory before public mutations;
changing the input path cannot allocate another paid project. Both evaluation
and completion duplicates are observed through real Celery task identities, with
unchanged model, grant, slot, account and governed-outcome facts required. No
live provider call is established by these tests.

Actual systemd startup then refused `User=10001` with `217/USER` because the
host had no account/group entries for that identity. Bounded controls reproduced
the refusal both without and with numeric KVM supplementary-group selection.
Host preparation now explicitly requires a dedicated locked no-login/no-home
account and primary group at the fixed IDs, with collision refusal and no Docker
or sudo grant. The isolated node provisions only its newly owned service identity;
existing accounts, services and `/etc/workstream` are preserved. This fixes the
missing prerequisite without changing node privileges or execution behavior.

Fresh baseline setup also lacked a usable registry ordering: it expected
registered capabilities before bootstrapping the Operator allowed to register
them. At `9db6d68b1`, the existing setup grants public Operator authority and then
registers exactly the supplied PRE/POST capability identities through the public
registry. Their image comes from the independently validated native cache; typed
receipts must preserve the full spec digest, operation and actor. Root review and
14 focused attachment tests passed, including refusal before mutation for a
missing/ambiguous image and refusal of substituted replies. No hidden owner
operation or second bootstrap was added. The release-image workflow now runs
the attachment and model-qualification guard tests in its frozen backend
environment, without changing existing deployment proof or timeout bounds.
