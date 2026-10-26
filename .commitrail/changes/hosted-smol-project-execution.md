# Hosted Smol project execution

- Initiative: `None`
- Durable disposition: `Planned`
- Intended merge outcome: Replace the hosted Docker/runsc project controller with the existing native Smol node for typed trusted intake, ordered non-model PRE checks and authorized model-enabled POST checks.

## Intent

Give the hosted release one explicit Smol execution boundary without a fallback runtime or a second controller. Preserve the existing ART, CHECKERS, MODEL, AUTH and TASK ownership of material, grants, paid effects, immutable evidence and governed outcomes.

## Current behavior

`deploy/hosted/compose.yml` starts a networkless controller container with the host Docker socket. `preflight.py` requires runsc and Docker image-cache inspection. Trusted intake already uses a native Smol service through a separate typed capability. API and worker mount absolute scratch/socket paths; project execution uses the existing typed `ExternalCheckerExecutionAdapter` and factory.

Merged main `ae788e6a8` rejects Smol model grants. The pending runtime change in PR #677 owns guest-native model/trial transport, predecessor material, child VM custody and resource enforcement. This hosted change consumes that implementation and cannot establish its qualification independently.

PR #690 at `f3f818265` owns provider selection and replacement credential overlays. Its pinned branch is an explicit integration dependency so this change can preserve those overlays rather than create another provider-selection path. It must land before this change is ready. Provider source behavior remains outside this change.

PRE model access is unsupported: `configured_model_profile_selector` rejects model selectors outside `post_submit`; `ModelAwareExternalExecution` and `model_execution_facts` require durable POST lineage. Selected PRE currently invokes the ordinary execution adapter without a model grant. This change preserves that rejection and does not claim PRE model support.

## Bounded change

### Allowed

- `deploy/hosted/compose.py`, `compose.yml`, selected provider overlays, `compose.trials.yml`, `preflight.py`, `checker-service.example.json`, `release.env.example` and `README.md`: replace the controller topology, validate native-node identity/readiness and preserve credential isolation.
- `external_checkers/deploy/workstream-checker.service` and `external_checkers/README.md`: align the existing native service configuration and document operator-managed provisioning and shutdown.
- `scripts/test_hosted_release_config.py` and existing focused deployment tests: exercise the rendered topology and meaningful refusal paths.
- `docs/decision_0014_external_service_adapter_convention.md`, `docs/architecture_checker_framework.md` and affected `docs/roadmap_status.md` claims: reconcile the intended hosted boundary and explicit evidence limits.
- This combined change record.

### Not allowed

- No runtime implementation changes in the PR #677 worktree, duplicate guest transport, fallback controller or provider implementation changes.
- No new adapter convention, service locator, backend business policy, schema migration, auth/payment authority, PRE model entitlement or paid retry.
- No EC2 mutation, shared service restart, `/etc/workstream` change, publication, activation, global cleanup or merge.
- Do not weaken existing credential, identity, material, deadline, cleanup or evidence checks to make a deployment fixture pass.

## Design and decisions

1. Use the existing delegated systemd/cgroup Smol service as the sole hosted node. Both typed intake and project execution clients use `/var/lib/workstream/checker-runtime/checker.sock`; their closed protocols and pinned image identities remain distinct.
2. Remove the Compose checker controller and its Docker socket/group grants. API and worker retain the same absolute scratch path and read-only node socket-directory mount. The native process runs as the same numeric UID/GID as the ART grant issuer.
3. Keep model credentials exclusively in the existing trusted model proxy. The native node forwards only invocation-bound guest capability traffic through the PR #677 transport; the project image receives neither global sockets nor credentials.
4. Replace runsc/image-inspection readiness with the existing typed project-execution health capability plus typed trusted-intake health. Validate configured Smol binary/guest/archive identities, native delegation and socket metadata without introducing a deployment controller. Configuration-only mode remains explicitly weaker than live readiness.
5. One trusted `WORKSTREAM_DEPLOYMENT_ROOT` selector derives identical absolute data/socket/model/parser paths on host and clients, defaulting to `/var/lib/workstream`. The root must be canonical, private and owned by the exact service identity; config, provider credentials and executable/cache assets stay outside it. `WORKSTREAM_CHECKER_SERVICE_BINARY` selects one absolute native service artifact under its required digest. This supports independently owned deployments without a test-only controller or validation bypass.
6. Operator provisioning and service lifecycle remain explicit. Compose startup validates the already-running native node; Compose shutdown drains producers/workers but does not stop an unrelated systemd unit. No command in this PR mutates the live proof node.

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
| Provider overlap | Read PR #690 and its exact head `f3f818265` | Inspected | Dependency is not merged |
| Smol callback transport | PR #677 implementation and qualification | Required dependency | Pending runtime integration and root-owned qualification |
| Rendered topology and refusal paths | `python3 -m unittest scripts.test_hosted_release_config scripts.test_hosted_release_images` | 64 passed, exit 0 | Contract/image fixtures; no native VM or provider execution |
| Generated readiness client | Execute the actual generated script using pinned backend Python, real Settings, registered typed factory and a local framed Unix health server | Passed; exact typed health request observed | The responder is a local protocol fixture, not a Smol node |
| Source hygiene | Ruff, Markdown links, stale wording and `git diff --check` | Passed | Does not replace runtime or independent review |
| Public lifecycle and real model behavior | Root-owned public API/Celery journey and scoped live proof | Required before support claims | No EC2 or paid model work performed by this change |

## Review findings

Root plan review of `e07f28b4a`: PASS WITH LOW RISKS for implementation only. The review required exact numeric identity, native/Compose path parity in both directions, native health before API/worker release and explicit drain ordering. Runtime signoff remains separate. The root subsequently approved one trusted deployment-root selector and explicit pinned native binary path because fixed production paths prevented an isolated rendered-topology proof without touching shared resources. Exact UID/GID and live health requirements remain unchanged.

Cold-start inspection found a schema/activation/proxy/node cycle: the proxy reads the activated ART namespace, the native node requires its model socket, and API normally applies migrations. The fixed `migrate`, AWS `proof` and exact proxy-only `up -d model-proxy` stages therefore validate static custody while releasing no application producer/worker; full `up` still requires both typed native health checks. AWS proof itself uses DB/AWS directly and retains its exact existing credential-separated observations.

The actual `docker/backend/release-entrypoint.sh` API role only loads its four role secrets and executes the supplied command; it performs no application startup, activation or readiness call. `backend/alembic/env.py` loads settings and model declarations, then runs migrations against PostgreSQL. A focused entrypoint control reaches its supplied command with absent node/proxy sockets and no model-provider files. This is source/entrypoint evidence, not a fresh-database migration or activation drill. Operator instructions explicitly require root/approved sudo for private input traversal and Docker access; runtime UID/GID `10001:10001` receives no daemon privilege.

Controller-only tests were replaced by native custody/readiness and second-controller refusal proof; API/worker mount, secret isolation, parser and producer/worker drain guards are retained. The generated readiness script was exercised through real Settings and the registered typed factory: the material root requires the matching ART scratch setting, which is now supplied from the same derived path. This proof uses a local framed Unix responder and makes no VM or paid-provider claim.

Exact-head implementation review follows this clean tested checkpoint; no passing implementation verdict is claimed here.

## Reconciliation

- Current-source reconciliation: start from main `ae788e6a8`; integrate the pinned PR #690 dependency before changing its hosted overlays; consume PR #677 runtime transport without copying it.
- Next usable boundary: tested hosted Smol configuration, then dependency integration and independent hosted/public qualification.
- Remaining risks: unqualified live model/Flow/AWS behavior and unsupported PRE model custody must remain explicit.
