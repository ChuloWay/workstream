# Terminal Systems project checkers and real contribution rehearsal

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Implement the source-backed Terminal Systems checker specifications as project-owned images, with the missing generic runtime capabilities explicitly qualified before policy activation.

## Intent and source

Continue after merged setup PR #651 on main `3ff69e3a8738fc12e7e8bb9d0f37583980409734`.
The original guide and final reviewed setup proposal define two PRE checks, six
model POST checks, two execution POST checks, and two lifecycle requirements.
This is a real guide-driven project, not a fixed task-name fixture. The user
explicitly resumed the minimal budgeted model runtime required by this project;
the prior PILOT-05 hold does not prohibit this authorized scope.

## First bounded implementation

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

## Acceptance and verification

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

Risk class: L1. Required focused reviews: architecture/plan, security and QA/test
delta; CI review only for changes to CI selection. Human focus: real rule coverage,
generic runtime boundaries, exact cost/custody, and honest qualification limits.

## Plan review

Architecture inspection confirmed that policy duplicate rejection includes
requirement identity. The same registered capability can safely serve the two
requirements with distinct locked configurations and separately counted budgets.
The initial PRE plan has no architecture blocker. Generic POST prerequisites
remain under design review; missing runtime support blocks activation.
