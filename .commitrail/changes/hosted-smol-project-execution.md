# Hosted Smol project execution

- Initiative: `None`
- Durable disposition: `Planned`
- Intended merge outcome: Replace the hosted Docker/runsc project controller with the existing native Smol node for typed trusted intake, ordered non-model PRE checks and authorized model-enabled POST checks.

## Intent

Give the hosted release one explicit Smol execution boundary without a fallback runtime or a second controller. Preserve the existing ART, CHECKERS, MODEL, AUTH and TASK ownership of material, grants, paid effects, immutable evidence and governed outcomes.

## Current behavior

`deploy/hosted/compose.yml` starts a networkless controller container with the host Docker socket. `preflight.py` requires runsc and Docker image-cache inspection. Trusted intake already uses a native Smol service through a separate typed capability. API and worker mount absolute scratch/socket paths; project execution uses the existing typed `ExternalCheckerExecutionAdapter` and factory.

At the initial baseline `fcd32057b`, main rejected Smol model grants. Main `6b55fd450` now includes PR #677 and its guest-native model/trial transport, predecessor material, child VM custody and resource enforcement. This hosted change consumes that implementation and retains its independently scoped qualification evidence.

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
- `README.md`, `docs/decision_0014_external_service_adapter_convention.md`, `docs/architecture_checker_framework.md` and affected `docs/roadmap_status.md` claims: reconcile the intended hosted boundary and explicit evidence limits.
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

- [x] Rendered hosted services contain no checker controller, Docker socket grant or runsc dependency; backend clients use one host Smol socket for the two existing typed capabilities.
- [x] Hosted configuration rejects Docker/runsc selection, missing or substituted Smol binaries/cache assets, unsafe identities, unbounded capacity and incorrect native socket/delegation.
- [x] Readiness uses registered typed adapters, validates exact runtime/image identities and fails closed before launch when the native node is unavailable.
- [x] Provider overlays retain PR #690 credential selection and expose credentials only to the trusted proxy; no provider source behavior changes.
- [x] Ordered non-model PRE remains supported; PRE model selectors remain unsupported and documented. Model-enabled POST is explicitly dependent on PR #677 and PR #690.
- [x] Focused contract tests cover valid composition and identity/credential/runtime substitutions. Relevant existing deployment and adapter checks continue to pass.
- [x] Documentation distinguishes prepared configuration and fixture proof from actual public API/worker, real model, hosted Flow/AWS and interruption qualification. The full public journey remains root-owned evidence.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: architecture/reuse, security, QA/test delta, CI integrity and documentation, routed to the changed boundaries.
- Human review focus: the single native endpoint, preserved absolute paths/UIDs, provider-secret isolation, dependency order and the explicitly unsupported PRE model branch.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Current deployment and typed ownership | Hosted Compose/preflight, existing systemd unit and actual public API/Celery/AWS proof at `6c483ca61` | Both policy branches passed | Fixture identity, not production Flow |
| Provider overlap | PR #690 at `f3f818265`; main `fcd32057b`; scoped OpenRouter continuation at `5ab96251f` | Existing provider owner preserved; one real response settled | Pinned-rate ledger, not provider-invoice reconciliation |
| Smol callback transport | PR #677 controlled composition/direct proofs and three active nested interruption cases; hosted live POST below | Scoped native and hosted proofs passed | No PRE model entitlement or full-project quality claim |
| Rendered topology and refusal paths | `python3 -m unittest scripts.test_hosted_release_config scripts.test_hosted_release_images` | 70 passed, exit 0 | Contract/image fixtures; no native VM or provider execution |
| Generated readiness client | Execute the actual generated script using pinned backend Python, real Settings, registered typed factory and a local framed Unix health server | Passed; exact typed health request observed | The responder is a local protocol fixture, not a Smol node |
| Source hygiene | Ruff, Markdown links, stale wording and `git diff --check` | Passed | Does not replace runtime or independent review |
| Public lifecycle and real model behavior | Public baseline at `6c483ca61`; same-effect live continuation at `5ab96251f` | Human/automatic baseline branches and live model acceptance passed | Synthetic engineering guide/submission; production identity, setup rehearsal and full project remain separate |

## Review findings

The first actual hosted baseline reached the correct failed/passed POST pair and
`review_pending`, then exposed an invalid proof assumption: production
`SafeJsonFormatter` deliberately omits Celery's free-form messages/results, so
the attachment's raw-log duplicate matcher can never observe completion. Repair
only the existing attachment, both duplicate-delivery callers and their focused
tests: subscribe to a private bounded Celery event queue before publishing one
explicit task UUID, observe that exact worker/task's received and successful
duplicate refusal, then retain the existing immutable database/account checks.
Enable task events only for the owned worker and restore its prior state; remove
the obsolete log matcher. No product logging, worker configuration, result
backend, task implementation or paid retry changes are allowed. Verify real
event routing with focused positive/negative controls, rerun the hosted baseline
with retained failure evidence, and independently review the observer before
the live model call.

The replacement subscribes before dispatch and waits for a real heartbeat from
the exact worker, because Redis installs fanout subscriptions during event
draining. It uses separate, finite event and control/publish connections; a real
Redis/Celery control reproduced a missing restoration acknowledgement when those
consumers shared one connection. The corrected control passed with the production
closed formatter, no raw success messages, one exact succeeded task event, and
both owned processes reaped. This synthetic task qualifies the observer mechanism,
not the real OUTBOX or public journey. The combined 29 attachment/model tests
passed, including wrong task/worker/result, reversed ordering, failure, absolute
deadline, prior event state and restoration failure. An in-memory broker fixture
race was removed by finishing its heartbeat producer before queue deletion;
concurrent real heartbeats remain covered by the Redis control. Ruff and independent
source review passed. The failed hosted attempt remains retained; the next
baseline uses a fresh owned database and Redis logical database before any paid
claim.

The second hosted baseline observed the actual duplicate OUTBOX delivery and
verified unchanged retained outcome, then failed while assembling its report:
the hosted branch still referenced the local result-backend task variable. The
report now retains the actual task UUID returned by the scoped event observer;
the local branch retains its result-backend UUID. Its observation label is also
corrected to `scoped_worker_events`. The complete hosted branch, including report
assembly, must pass on fresh owned fixtures; neither partial run is a baseline
PASS and neither made a paid model call. Product services and images are unchanged.

The corrected public hosted baseline passed at `6c483ca61`, including both policy
branches and exact duplicate refusal. Its model qualification then stopped before
materialization or any model effect: the planned 600-second checker needs 720
seconds including the existing ART and cleanup allowances, but the expiry fixture
configured only 360 seconds. The deadline owner correctly refused execution.
The bounded proof repair adds a read-only runtime-window check before claiming a
paid project, compares actual hosted and driver settings, and derives observation
time from the stored policy and existing owner margins. Allowed files remain the
two hosted proof modules, their focused tests and this record. No policy, budget,
claim, Submission or original expiry receipt may be reset or rewritten. Restore
the normal operational ART window only for future leases and use the existing
public Operator recovery for the same failed run/project/account. No new product
retry path or generic resume framework is authorized by this repair.

The repair also shares the existing outcome observer with an explicit recovered
dispatch, checking its original project, task and Submission before observation.
The paid-custody, governed-outcome and replay assertions remain unchanged. All 33
combined attachment/model tests passed; the new pre-claim check fails against
the previous entrypoint. Root and independent runtime review passed the ordering,
locked-policy budget, float-settings conversion and preserved validation tail.
Ruff and diff checks passed. This proof-only repair does not change production
backend, native binaries or checker images; it does not establish a live provider
result or the still-pending active nested recovery cases.

The first read-only continuation preflight then caught a proof-only assumption:
the hosted release does not override the checker socket timeout, so indexing
that optional key failed before opening the claim or dispatching recovery. The
guard now uses the canonical Settings field default when absent and still
requires the driver's resolved setting to agree. A missing-key regression uses
the actual Settings defaults and rejects a divergent driver. The original claim,
account and failed run are unchanged; no provider effect was created.
All 34 combined tests passed; loading the previous guard into the new test
reproduced the exact missing-key error. Independent review and Ruff passed.
The operations guide also explains drained scratch-root replacement when limits
change, preserving the old root and refreshing container and systemd mounts;
independent review confirmed the canonical ART marker and lifecycle ordering.

The same-account recovery reached a prepared model effect, but stopped before
request-evidence binding, budget reservation or provider dispatch. Inspection
identified a missing bootstrap prerequisite: the canonical journey service list
omits `workstream.artifact.checker_output`, required by both checker and setup
model evidence storage. Extend `backend/scripts/provision_local_service_actors.py`
and the focused `backend/tests` checker-output custody regression, using existing
public service-actor provisioning and unchanged authority. Prove denial with no
writer, then verified storage after canonical provisioning on PostgreSQL/MinIO.
No permission, schema, ledger, policy or retained-effect reset is allowed. Any
continuation must use the existing recovery owners and original project account.
The proof must also recognize the owner's supported prepared-effect recovery:
one newly authorized successor grant can reference the same paid slot/effect as
its failed predecessor. Retain the exact predecessor grant/call snapshot before
retry, verify its immutable identity and direct failed-run lineage afterward,
and continue requiring exactly one paid slot and effect. The initial path still
requires one grant; recovery permits exactly that retained predecessor plus the
current grant, with the same request hash and no additional spend opportunity.
The existing model proof module and its focused tests own this bounded check;
production grant, retry and ledger operations remain unchanged.
Both real custody regression variants (Local and MinIO, with PostgreSQL) passed;
the old bootstrap list, substituted only in memory, fails at request-evidence
storage with the expected authority error. Isolated database, role and MinIO
cleanup passed. All 35 combined hosted attachment/model tests passed, and the
previous one-grant proof guard rejects the new supported-recovery test. Root
review passed the canonical bootstrap change; independent review passed the
bounded prior-grant proof. No live provider outcome is established by these
regressions. The failed hosted recovery retains one prepared effect, no ART
request evidence and a zero-reserved/zero-settled account for later exact recovery.

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
- Next usable boundary: consume the qualified native/hosted composition in the separately owned real-project approval and contribution journey.
- Remaining risks: production Flow identity, substantive model-grading quality, the full project journey and unsupported PRE model custody remain explicit.

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

Independent review passed the added CI step and its exact path triggers. Its
first hosted run (`40373193281`) then reproduced an order-sensitive test fixture:
the stalled-admission guard set a broker environment value after settings had
already been cached. The test now scopes that value and clears settings before
worker import and during cleanup; its no-verifier-dispatch assertion is intact.
The exact combined two-module command with the broker environment unset failed
one of 26 tests before `f406310f7` and passed all 26 afterward. Root review, Ruff
and diff checks passed. Product settings and release images are unchanged.


### Live hosted model continuation

Exact deployment source `5ab96251fc08e0c8cd3e8128bc9fb4f4fc8ed2bf`
(tree `3b4f8be16fe3ca7915add5fc24a08f01f1c5dd2c`) rebuilt both backend SDK
images and their fixture-CA derivatives. The unchanged native-hosted image
verifier passed (evidence SHA-256
`05b5dea9a8567f5b0c8331b4fdff4b536ff9574af2bcb9970dd9e314bcae966b`).
Release `20c965fa8cf3d2a45e30ae9bdc78b105db8d62de6231fd8cf0ec525447f0300f`
passed canonical AWS and native/attachment readiness checks. Native service,
guest, launcher and project image pins remained unchanged from the qualified
runtime. Compared with baseline `6c483ca61`, backend changes are exactly the
canonical service bootstrap and its real custody regression; application,
Alembic, dependency and image-recipe trees are identical. Later runtime merges
change only the recovery observer and its documentation.

The canonical public service bootstrap provisioned the missing existing model
output writer. It changed neither the original project account nor its prepared
effect. Read-only inspection passed with receipt SHA-256
`e9d0a6852eeeae6fe297c0581880b048437dcce9496c3265fc7b62cf49e6b60d`.
One explicit public Operator retry then advanced generation 2 to generation 3
on the same immutable Submission. It reused the same paid slot, prepared effect
and exact request hash; the old grant and complete earlier failure history were
retained. No new project, budget allocation, Submission or paid-call identity
was created for the continuation.

The real OpenRouter response graded the disclosed synthetic
`solver_brief_and_extension_disclosure` fixture as passed. The durable worker
and completion delivery reached `accepted`, retaining exactly one Submission,
one FinalAcceptance and one submitter ContributionRecord, with zero Reviews and
zero awards under the unpaid policy. Private request and response ART bindings
and public redacted effect inspection were verified. The ledger settled
16,527,000 nanodollars (US$0.016527), within the authorized US$10 ceiling, and
released the outstanding reservation to zero. This is the ledger's conservative
charge at locked rates, not provider-invoice reconciliation. The earlier
uncertain setup charge remains separately unresolved.
Independent arithmetic confirmed 2,319 uncached input tokens at 5,000
nanodollars and 274 output tokens at 18,000 nanodollars equal the recorded
16,527,000-nanodollar settlement; cached input was zero. The selected provider
and model were `openrouter` and `openai/gpt-5.6-terra`.

Exact public Submission replay and two real duplicate Celery deliveries retained
identical account, effect, grant, slot, outbox and governed-outcome facts. The
native owned-resource inventory was empty and the foreign control remained
present. Full continuation receipt SHA-256:
`bd96a3b0b2b8609cc7f0c298aae0d86721ca5ee4346a613b8e030aa963cd1fd1`, retained at
`/var/tmp/workstream-hosted-smol-20261026/assets/node-control/model-prepared-continuation-receipt.json`.
The root independently rehashed the 15 preparation artifacts and inspected this
receipt; a separate read-only PostgreSQL snapshot confirmed the same completed
effect, current run and zero-reserved account.

The original baseline and failed attempts remain immutable. A private startup
observer used the wrong parser role name and failed after actual startup;
separate exact-role inspection confirmed all five healthy roles without
restarting them or weakening product readiness. The live proof uses simulated
RS256 identity and one synthetic rubric. It does not establish production Flow
identity, a live setup-agent rehearsal, full trial execution in that paid call,
substantive rubric quality, an approved revision journey or the complete Terminal
Systems project owned by #555. PRE model selectors remain unsupported.

The reviewed success-only cleanup then stopped producers, drained the worker,
verified native drain, finalized the supervisor while the proxy remained live,
and stopped the native node and its clients. Cleanup receipt SHA-256
`a0d171fbeee72c7f81d1adf8fffa90936d43e52641497afc029ff22babc6035c`
and independent final inventory SHA-256
`11095053e9b24add353b1cae1aa06fc0e82f94b916fd33eac06b87036ee5f5aa`
confirm stopped owned services/timer, empty VM/lease/cgroup/relay and ART scratch
inventories, and no outstanding reservation. The fixed claim retained inode
4790559 and final SHA-256
`92ae55c5ec91940b64ff934f2b143c24b95796e48d6b613a966150442761a116`.
Database, object-store evidence, original failure history and shared services
were preserved. No global cleanup or additional model call occurred.

### Asset diagnostic review correction

CodeRabbit identified that `_verify_smol_asset` caught its own `PreflightError`
through the generic `RuntimeError` handler, replacing specific refusal reasons
with an unavailable-file message. Preserve explicit path, custody, deadline and
digest/identity diagnostics; continue normalizing underlying filesystem/runtime
errors and refusing launch. Scope is the existing preflight, its hosted-config
tests and this record. No asset acceptance, authorization, runtime or provider
behavior changes. Verify real temporary files for each diagnostic, ordinary
missing-file normalization, the existing readiness tests and a pre-fix control.
The merge from main `6b55fd450` has no source delta beyond the already consumed
PR #677. Roadmap capabilities and remaining gates are unchanged by this
diagnostic-only correction.

Validation: the new diagnostic regression failed against the original handler
for all four explicit refusals, while its missing-file control passed. After
the correction, all 71 hosted configuration/image tests passed. Ruff check,
formatting and diff whitespace checks passed. No paid call or deployment was
needed: the only executable change preserves already-raised error messages.
