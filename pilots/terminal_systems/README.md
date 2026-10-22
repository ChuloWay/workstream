# Terminal Systems project setup

Start with [the contributor guide](guide.md) and [one illustrative task](task-example.md).
These are original project inputs for a fresh onboarding run. They are not a
checker implementation, an approved policy or a record of completed work.

## Files to use

- `guide.md`: upload the original Markdown bytes as the project document.
- `guide-request.json`: guide metadata and the illustrative task text in the
  existing public creation schema. Its document declaration does not upload bytes.
- `task-metadata.example.toml`: a copy of the shape example embedded in the
  guide, for authors to replace with their real values. It is not a working
  environment or a measured resource profile.
- `tasks/`: readable versions of the five initial briefs listed below. Their
  complete text is also carried in `tasks.json`.
- `tasks.json`: five authoring briefs in the existing task-import format, for
  import after the project is configured. They are work to assign, not completed
  submission packages or a checker allowlist.

The guide is self-contained when uploaded: its metadata table and example are
included in `guide.md`, without depending on a repository-relative attachment.
`task-example.md` is the queue-recovery brief, also embedded in the guide creation
request. Keep these copies synchronized when editing the inputs.

The guide does not repeat Workstream's platform upload limits. Setup leaves
project size overrides null unless the guide explicitly adds a restriction;
platform upload, archive-safety and storage-admission enforcement always applies.

## Initial work

| Brief | Main behavior the author develops into a solver task |
|---|---|
| [Queue recovery](tasks/queue-recovery.md) | Preserve completed effects and recover interrupted work without duplicating results. |
| [Snapshot restore](tasks/snapshot-restore.md) | Validate snapshot contents and publish a restored tree without damaging the prior destination on failure. |
| [Incremental build](tasks/incremental-build.md) | Rebuild affected dependencies and preserve correct output across failed steps. |
| [Database upgrade](tasks/schema-upgrade.md) | Convert retained records atomically and handle interruption, replay and unsupported versions. |
| [Event correlation](tasks/event-correlation.md) | Produce correct summaries despite duplicates, ties, timezone differences and shuffled records. |

These are original authoring assignments, not five finished benchmark packages.
Contributors must specify the exact interfaces and supply the starting code,
reference and verification. New subjects and identifiers can be added through
normal task creation; no runtime change or checker allowlist is implied.

## Onboard through the public product flow

1. The PM creates the project and guide with its example and uploads the declared
   document through the supported API or CLI. Committing the last declared
   document upload automatically queues setup; there is no separate start command.
   The manager needs a role grant on this exact project for setup and proposal
   reads; system-level project-creation authority alone is insufficient.
2. Setup reads those actual inputs and the available registered capabilities.
   Inspect its source-backed requirement inventory, proposed PRE/POST bindings
   and missing-capability suggestions. Do not substitute a prepared result.
3. Engineering receives the uncovered requirements, intended stage, expected
   findings and execution needs. Build and test the required external checker
   images against the existing request/result contract. Project logic belongs
   in those images, not in project-named branches of Workstream or its shared
   runner. Reuse a registered implementation only if it really covers the need.
   Use the merged [image command](../../docs/engineering/checker-images.md) for
   each project-owned implementation. Its default ECR destination names are
   `workstream-checker-pre-terminal-systems` and
   `workstream-checker-post-terminal-systems` in `eu-north-1`, once the operator
   has created the selected repositories. A name in this document is not proof
   that the repository or image exists. Keep implementations in the project's
   own source directory; do not add rules to the shared Rust service.
4. Register the exact immutable image/configuration capabilities through the
   authorized Operator operation. A Project Manager with authority on this
   project creates and explicitly dispatches a correction successor, or creates
   a new guide version, so a fresh proposal can bind the registered entries.
   A finalized setup run cannot be rerun. Registration alone does not repair an
   earlier proposal or approve a policy.
   Provision the exact digest and generated cache entry on the execution host;
   the current service reads its cache configuration at startup. The publisher
   does not deploy images to that host or enable a policy.
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

For this guide-driven rehearsal, configure the inference setup runtime to derive
requirements from the original guide and example. Main also supports an explicit
[manager-authored rules runtime](../../docs/operations_project_operating_manual.md#manager-authored-guide-rules).
That alternative reads supplied rules without inference; it does not discover
checks from prose. Its proposal correction operation is unsupported, so follow
its documented fresh-guide procedure when replacing rules. This input package
does not supply a prewritten rules result or select that alternative.


No checker is claimed to implement this guide yet. In particular, the previous
fixed five-task sample is not an implementation of these requirements. Required
semantic judgments, metadata tooling, environment support and execution needs
must appear in setup's capability assessment; do not weaken the guide to hide a
gap. A missing required capability blocks activation until engineering supplies
it and the proposal is approved. Human-review requirements cannot be silently
converted into automated acceptance.

Before upload, confirm that this guide describes the desired project. The PM
still chooses compensation, review mode, revision cap and revision window through
the separate governed policy operations. The input version label does not
publish or replace any existing guide in a live project.
Nor does it authorize live model spend, registry publication or deployment.

For the first setup run, retain the actual requirements and capability suggestions
with their guide references. An engineering handoff should identify each uncovered
requirement, proposed execution stage, inputs, expected findings, dependency needs
and representative positive/negative cases. Do not handwrite that result in
advance or classify a required semantic judgment as enforced merely because a
file exists. Building submitted environments offline and checking reference/test
quality need explicit implementations and proof. When the configured runtime
cannot provide them, keep that gap visible and the guide inactive.

The work remains tracked by [project preparation #576](https://github.com/Flow-Research/workstream/issues/576)
and [the connected journey #555](https://github.com/Flow-Research/workstream/issues/555).
The first milestone here is usable guide/example/task input; readiness requires
the real setup and contribution journey, not predetermined fixture outcomes.
