# Terminal Systems project POST checkers and isolated trial runtime

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Implement source-backed Terminal Systems POST checker images and the generic bounded model/trial capabilities they actually need, then hand exact image/runtime evidence to the separately owned live-project journey.

## Intent

Resume issue #493 from reconciled main `7f6a71a69daf563742b72c706e6d09aa742ac25e`.
Merged PR #656 already supplies the standalone PRE image. The retained setup
handoff identifies two PRE checks, six model POST suggestions, two execution
POST suggestions and two obsolete lifecycle classifications; it is engineering
reference, not current policy. The unchanged guide and a fresh PRE/POST-only
proposal remain the sources to reconcile. This is a real guide-driven project,
not a fixed task-name fixture. Shared model access now covers both POST agents
and setup under #492's one project account; this change consumes that contract
without owning its ledger, migrations or provider credentials.

## Bounded change

Allowed project paths are `pilots/terminal_systems/checkers/**`, the project
README, affected current roadmap/runbook claims, this record and proportionate
test/CI selection for these project assets. Preserve and reuse the delivered
Python PRE image, its exact handoff provenance, samples and recorded evidence.
New project code implements POST rubrics and bounded agent orchestration
independently of named tasks. Shared runtime changes remain generic and are
listed separately below. Database schema, policy authority, guide content and
lifecycle outcomes are unchanged by this change.

`.github/workflows/terminal-systems-checkers.yml` runs the project unit and real
image samples on project/contract/tool changes. It adds no model calls, cloud
credentials, deployment, product test exclusions, or replacement required gates.

The remaining POST runtime contract must be reviewed before implementation:
budgeted, invocation-bound model access with credentials outside the sandbox;
isolated execution of submitted environments; trusted trial and revision input.
No claimed passing checker may replace unavailable evaluation with file presence,
untrusted author claims, fixed answers, or manual reviewer findings. Setup-model
budget/effect integration remains owned by #492. No merge, live model spend,
image publication/registration, activation or hosted deployment is authorized
by this record.

### Resumed POST boundary

The retained setup handoff is source-bound engineering input, not current
approved policy. It identifies six model-evaluation and two isolated-execution
POST suggestions from the unchanged guide, but it predates the PRE/POST-only
setup restriction. Engineering preserves those source rules while project setup
obtains a fresh correction; neither the count nor the retained proposal is made
an activation authority by this change.

The first safe POST slice is limited to
`pilots/terminal_systems/checkers/post/**`, this checker README, the existing
Terminal Systems checker workflow, this record, and affected Terminal Systems or
current roadmap claims. It may define source-linked rubrics, bounded project
material tools, strict model-output validation, project image behavior and
offline test doubles. It must consume the generic invocation-local model proxy
contract owned by the concurrent model-runtime change; it must not invent a
second transport, a global bearer token, a provider SDK, provider credentials,
budget storage or a paid-effect ledger. Exact proxy fields are not frozen here
until that owner publishes the typed contract.

Generic isolated build/trial support owns the new
`external_checkers/workstream-checker-service/src/trial_relay.rs` module after
coordination with the model-runtime owner. That owner retains the coupled
`main.rs` invocation-capability assembly, `model_relay.rs`, budget/profile
owners and every migration; this change does not edit `main.rs` concurrently.
`external_checkers/workstream-checker-service/tests/trial_relay.rs` compiles
that otherwise unconnected module and exercises its fake-engine protocol,
identity, bounds, cancellation and cleanup contracts before shared composition.
The concrete generic offline implementation is isolated in
`external_checkers/workstream-checker-service/src/trial_engine.rs` with focused
`external_checkers/workstream-checker-service/tests/trial_engine.rs` launch,
classification, resource, role-projection and cleanup tests. It consumes only
trusted digest-pinned engine inputs and the relay's generic plan; it contains no
Terminal Systems paths, task names, commands or findings.
The trial module publishes a generic typed relay, profile and observation API;
it does not treat relay success as a work verdict. Backend trial authority starts
in `backend/app/modules/checkers/api/trial_profiles.py`,
`backend/app/interfaces/trial_execution.py`, and
`backend/tests/checkers/external/test_trial_profiles.py`. These define a
distinct digest-pinned trusted service-config reader and do not reuse the
monetary model profile. Later selected-POST, TASK and ART owner files require
their exact file list and typed port contract to be added here before edits;
this change owns no migration. The bridge must
keep Docker authority and
prepared offline material outside the untrusted project image, expose only
invocation-local bounded tools, and prove aggregate time, CPU, memory, PID and
scratch-disk limits, cancellation, cleanup, no network or host socket in the
nested workload, and trusted infrastructure-versus-work classification. It must
produce authenticated trial evidence rather than accepting contributor-authored
claims. Revision checks additionally require an owner-supplied typed first-versus-
revision context, exact prior material identity and feedback. Missing owner ports
remain explicit infrastructure gaps; project code does not read product tables.

Prohibited changes are migrations, project-named rules in shared Rust, task-name
allowlists, restoration of the removed private continuation, guide/policy
approval or activation, task import, lifecycle outcome rehearsal, live model
calls, image publication or registration, deployment, and work in the separate
human review/revision initiative. The existing PRE image and its recorded
publication evidence are reused without rebuilding merely to repeat proof.

The intended verification starts with exact handoff/rubric parity, focused
project-rule tests, adversarial malformed or unsupported model-output tests,
bounded material-tool tests and offline fakes. Those are development evidence
only. The reviewable outcome requires the actual generic trial tool plus composed
#492 model flow to produce substantive project findings, including negative,
resource, cancellation, cleanup and replay/substitution controls. Controlled
provider qualification follows the approved shared runtime; live spend and the
project activation/contribution journey remain separately authorized phases.

This shared-boundary change also owns `external_checkers/README.md`,
`docs/architecture_checker_framework.md`, `docs/architecture_lockdown.md` and
`docs/decision_0014_external_service_adapter_convention.md`. Before the relay is
composed, those canonical documents and ADR distinguish the typed,
profile-authorized invocation tool from the retired image-output continuation.
An image may submit bounded workload argv, relative selectors and opaque
project-profile roles through `/work/execution.sock`; it may not return a
private plan as its outer result, select a host path, Docker flag, mount,
runtime, image, credential, network or resource enlargement. Shared Rust knows
no Terminal Systems filename, task, trial label or command allowlist. Preserve
the regression that `project_private_plan.v1` outer output is invalid.

## Acceptance criteria

- PRE layout checks required regular files and directories at the package root,
  accepting arbitrary task subjects and additional useful directories.
- Metadata implements the documented types, path containment, command argument
  arrays, positive integer allowances, platform and extension rules; it never
  runs commands or invents guide size limits.
- Findings identify the documented rule and safe relative location. Resource,
  material or implementation failures remain infrastructure outcomes.
- Use the existing generic image command for real networkless, non-root,
  read-only positive/negative sample execution and exact result identity checks.
  Local Docker evidence is labelled `docker-dev`, never gVisor qualification.
- Produce immutable build and configuration metadata for tested POST images,
  without publishing, registering or activating them in this change.
- Every claimed POST pass must use actual model/trial evidence through the
  supported generic capabilities. Preserve the original guide and immutable
  earlier proposals; keep unsupported revision/prior-work dependencies explicit.
- Hand exact image/runtime evidence and remaining dependencies to #555's owner.
  The live public API/CLI activation and contribution journey are not this
  change's acceptance criterion, and image samples alone are not that proof.

## Risk and review routing

Risk class: L1. Required focused reviews: architecture/plan, security and QA/test
delta; CI review only for changes to CI selection. Human focus: real rule coverage,
generic runtime boundaries, exact cost/custody, and honest qualification limits.

## Plan review

Architecture inspection confirmed that policy duplicate rejection includes
requirement identity. The same registered capability can safely serve the two
requirements with distinct locked configurations and separately counted budgets.
The initial PRE plan has no architecture blocker. Generic POST prerequisites
remain under design review; missing runtime support blocks activation.

## Evidence

Independent review identified noncanonical metadata path aliases and undeclared
fields in the four fixed metadata tables. Two regression cases reproduced eight
incorrect passes before repair. Paths now preserve exact manifest spelling and
supplementary metadata belongs under `extensions`; arbitrary nested extension
data remains supported. The image sample suite includes both rejection cases.
The affected roadmap and project documentation distinguish the retained ten
unbound suggestions, implemented PRE rules, and remaining eight POST rules.

Seventeen rule tests and seven actual networkless Docker samples pass. The
publisher pushed the reviewed image to ECR, verified the immutable manifest,
pulled it back and reran all seven samples. The exact image was registered through
the local Operator CLI. Publication and registry facts are in the checker README;
these do not establish gVisor, policy approval or a completed contribution journey.
