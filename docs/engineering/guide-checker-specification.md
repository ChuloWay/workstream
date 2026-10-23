# Guide setup: PRE and POST specification contract

Setup translates the assigned guide and task examples into check specifications.
It does not recommend review mode, revision caps or windows, deadlines, assignments,
compensation or routing. The PM configures those through the existing policy paths.
Administrative guide clauses are outside the checker inventory.

## Inputs and authority

| Input | Meaning |
| --- | --- |
| Document manifest | Exact authorized originals, opaque read handles and evidence identities. The agent must actually read them. |
| Task examples | Illustrations of the project, never a task allowlist or completed submission. |
| Capability snapshot | Exact registered checker versions and configurations available for selection. |
| Correction and prior proposal | The requested correction and immutable earlier result; neither can change tool authority or scope. |
| Instructions | Snapshotted scope, format, complete synthetic output example and constraints. |

Only assigned originals are accessible. Missing required checker support is a staged
capability gap, not permission to invent an implementation or ask a human to replace it.
Missing PM policy choices do not block specification. A guide with no additional
checkable work obligations does not need fabricated requirements; source coverage
and guide sufficiency still require validation.

## PRE and POST

PRE is structural or other bounded work that reliably fits 60 seconds, before
Submission creation. POST is background evaluation of an immutable Submission;
model judgments always belong here. Split file presence from semantic content,
and documentary assessment from actual execution. A model reading a claimed run
cannot prove that the run happened. Declare every unavailable input/runtime need.

The Workstream default remains independent: ZIP safety, verified bytes/manifest,
high-confidence secrets and unchanged-work detection. Unspecified project upload
limits stay null; the platform ceilings still apply. Summary and attestation remain
warning-only. The agent cannot change those defaults.

## Exact output

One JSON object, with no surrounding prose or Markdown, duplicate keys, unknown
fields, nonfinite numbers or omitted schema-required members. There is no free-form
notes field in inference output.

| Field | Purpose |
| --- | --- |
| `status`, `findings` | Whether the guide is sufficient to specify checks; source-linked blockers or warnings. |
| `submission_artifact_policy` | Guide-derived artifact requirements and explicit size overrides, or null for a blocked guide. |
| `requirements` | PRE/POST checks with complete specifications; exact default coverage or check-definition blockers are supporting facts. |
| `pre_submit_bindings`, `post_submit_bindings` | Exact available registered capabilities, with matching configuration. |
| `capability_suggestions` | One same-stage engineering request per missing check. |
| `agent_name`, `agent_version`, `schema_version` | Exact protocol and supplied runtime identity. |

A check specification states its method, stage/duration, inputs, ordered checks,
observable pass/fail conditions, findings, positive/negative cases, dependencies
and infrastructure outcomes. Infrastructure failure is never a contributor failure.
A sufficient guide with missing capabilities remains a warning-ready proposal;
activation still waits for registered implementations and approved bindings.

The complete [synthetic example](../../backend/app/interfaces/project_guide_example.py)
contains a static report-file PRE check and a POST model review of whether report
conclusions follow its observations. Neither capability is registered in the
hypothetical example, so each has a gap specification and suggestion, with empty
binding lists. Its identities and requirements must never be copied into a real
project. Tests validate the example against the exact provider schema and canonical
checks; the serialized example is part of the instruction snapshot/hash.

## Rejection and correction

Both private drafting and independent source review enforce the restricted schema
and canonical/context rules. Known invalid completed output receives bounded paths
and closed error codes and may be corrected at most twice across the whole attempt.
The agent returns a complete replacement, not a patch. No rejected values or raw
exception messages are put in feedback. Unknown provider failures are not replayed
as format errors. Corrections do not reset time, turn/tool budgets, source access,
circuit admission or cleanup. Exhaustion returns invalid output without a proposal.

The successful review phase must independently reopen the assigned originals.
Schema validity cannot prove that every natural-language assertion is correct;
source review and PM review remain necessary. Historical stored proposals are not
rewritten. Explicit manager-authored rules retain their distinct existing input
contract and do not acquire new authority through this inference restriction.
