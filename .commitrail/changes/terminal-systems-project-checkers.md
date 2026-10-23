# Terminal Systems project checkers and real contribution rehearsal

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Implement the source-backed Terminal Systems checker specifications as project-owned images, with the missing generic runtime capabilities explicitly qualified before policy activation.

## Intent

Continue after merged setup PR #651 on main `3ff69e3a8738fc12e7e8bb9d0f37583980409734`.
The original guide and final reviewed setup proposal define two PRE checks, six
model POST checks, two execution POST checks, and two lifecycle requirements.
This is a real guide-driven project, not a fixed task-name fixture. The user
explicitly resumed the minimal budgeted model runtime required by this project;
the prior PILOT-05 hold does not prohibit this authorized scope.

## Bounded change

Allowed paths are `pilots/terminal_systems/checkers/**`, the project README,
affected current roadmap/runbook claims, this record and proportionate test/CI
selection for these project assets. Build a standalone Python standard-library
PRE image implementing the exact package-layout and metadata specifications.
One immutable capability with a closed `check` selector serves two separate
requirement bindings; neither invocation executes submitted commands. Include
the actual generated handoff and its provenance, positive/negative image samples,
and process tests independent of named pilot tasks. Shared Workstream/Rust code,
database, policy authority, guide content and lifecycle outcomes are unchanged
by this first implementation.

`.github/workflows/terminal-systems-checkers.yml` runs the project unit and real
image samples on project/contract/tool changes. It adds no model calls, cloud
credentials, deployment, product test exclusions, or replacement required gates.

The remaining POST runtime contract must be reviewed before implementation:
budgeted, invocation-bound model access with credentials outside the sandbox;
isolated execution of submitted environments; trusted trial and revision input.
No claimed passing checker may replace unavailable evaluation with file presence,
untrusted author claims, fixed answers, or manual reviewer findings. Setup-model
spend integration is not implicitly included. No merge or hosted deployment is
authorized by this record.

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
The trial module publishes a generic typed relay, profile and observation API;
it does not treat relay success as a work verdict. Backend trial
authority/materialization may later extend the existing
selected-POST, TASK and ART owner files only after their exact file list and
typed port contract are added here; it will not add a migration. The bridge must
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

The intended verification for the first slice is exact handoff/rubric parity,
focused project-rule tests, adversarial malformed or unsupported model-output
tests, bounded material-tool tests, and offline composed tests against a fake
proxy. Those tests are development evidence only. A completion claim requires
real composed proxy/transport and isolated-sandbox trials with a controlled
provider, while live spend and the project activation journey remain separately
authorized phases.

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
- Publish only tested content to the selected ECR repository, then separately
  register exact digests and obtain corrected, approved policy bindings.
- Before activation, every required POST capability and its material/runtime
  dependencies must actually be available. Preserve the original guide and
  immutable earlier proposals.
- The final public-API/CLI journey records byte custody, pre-check rejection with
  no Submission, durable post-checking, revision/infrastructure recovery and
  exact governed contribution evidence. Image samples alone are not that proof.

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
