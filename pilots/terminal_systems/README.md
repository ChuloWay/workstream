# Terminal Systems project setup

Start with [the contributor guide](guide.md) and [one illustrative task](task-example.md).
These are original project inputs for a fresh onboarding run. They are not a
checker implementation, an approved policy or a record of completed work.

## Files to use

- `guide.md`: upload the original Markdown bytes as the project document.
- `guide-request.json`: guide metadata and the illustrative task text in the
  existing public creation schema. Its document declaration does not upload bytes.
- `tasks.json`: five authoring briefs in the existing task-import format, for
  import after the project is configured. They are work to assign, not completed
  submission packages or a checker allowlist.

## Onboard through the public product flow

1. The PM creates the project and guide with its example and uploads the declared
   document through the supported API or CLI. Committing the last declared
   document upload automatically queues setup; there is no separate start command.
2. Setup reads those actual inputs and the available registered capabilities.
   Inspect its source-backed requirement inventory, proposed PRE/POST bindings
   and missing-capability suggestions. Do not substitute a prepared result.
3. Engineering receives the uncovered requirements, intended stage, expected
   findings and execution needs. Build and test the required external checker
   images against the existing request/result contract. Project logic belongs
   in those images, not in project-named branches of Workstream or its shared
   runner. Reuse a registered implementation only if it really covers the need.
4. Register the exact immutable image/configuration capabilities through the
   authorized Operator operation. Rerun setup or use the supported correction
   path so the proposal binds those entries; registration alone does not repair
   an earlier proposal or approve a policy.
5. The PM inspects and approves the separate PRE and POST policies and sets the
   review and revision policies. Finance supplies the published contribution
   policy. Activate only when required capabilities and all policy prerequisites
   are satisfied. A suggestion or a green image build is not activation.
6. Import the five briefs, screen them against the activated guide, and release
   eligible tasks. A contributor then claims and starts a task and submits real
   work through the public ZIP intake.
7. Observe the complete journey: default/PRE feedback before Submission, durable
   POST execution after Submission, and the actual governed outcome. Include a
   correction and an infrastructure interruption without fabricating evidence or
   editing product rows. Record exact source, guide, policy, image and outcome IDs.

## Current boundary

No checker is claimed to implement this guide yet. In particular, the previous
fixed five-task sample is not an implementation of these requirements. Required
semantic judgments, metadata tooling, environment support and execution needs
must appear in setup's capability assessment; do not weaken the guide to hide a
gap. A missing required capability blocks activation until engineering supplies
it and the proposal is approved. Human-review requirements cannot be silently
converted into automated acceptance.

This preparation does not choose compensation, review mode, revision cap or
revision window for the PM. Those are separate governed policy operations.
Nor does it authorize live model spend, registry publication or deployment.

The work remains tracked by [project preparation #576](https://github.com/Flow-Research/workstream/issues/576)
and [the connected journey #555](https://github.com/Flow-Research/workstream/issues/555).
The first milestone here is usable guide/example/task input; readiness requires
the real setup and contribution journey, not predetermined fixture outcomes.
