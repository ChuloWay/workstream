# WS-CLI-001 — First-class Workstream CLI

- Disposition: Planned
- Intent: Give humans and agents an installable terminal interface to public
  Workstream operations without creating another identity, authority, or product
  lifecycle implementation.
- Delivered boundary: [WS-CLI-001-01](WS-CLI-001-01.md), caller-owned profile and
  exact-project authorization context; [WS-CLI-001-02](WS-CLI-001-02.md), human
  self-profile editing through the public REST API; [WS-CLI-001-03](WS-CLI-001-03.md),
  exact-project inspection with server-owned full/minimal disclosure;
  [WS-CLI-001-04](WS-CLI-001-04.md), public manager task pagination and detail;
  [WS-CLI-001-05](WS-CLI-001-05.md), contributor ready-task discovery and instructions;
  [WS-CLI-001-06](WS-CLI-001-06.md), public contributor claim/start with explicit retry keys;
  [WS-CLI-001-07](WS-CLI-001-07.md), contributor governing context and locked intake requirements;
  [WS-CLI-001-08](WS-CLI-001-08.md), draft project shell creation with explicit caller-owned replay;
  [WS-CLI-001-09](WS-CLI-001-09.md), guide declaration, illustrative tasks and document upload selectors;
  [WS-CLI-001-10](WS-CLI-001-10.md), declared-original upload with hash/size-bound storage receipts;
  [WS-CLI-001-11](WS-CLI-001-11.md), latest exact-guide setup diagnostics and compilation lineage;
  [WS-CLI-001-12](WS-CLI-001-12.md), exact finalized-proposal findings and policy inspection;
  [WS-CLI-001-13](WS-CLI-001-13.md), deliberate exact pre-submission approval and manual replay;
  [WS-CLI-001-14](WS-CLI-001-14.md), exact derived evaluation-policy and retained correction inspection;
  [WS-CLI-001-15](WS-CLI-001-15.md), deliberate exact evaluation-policy approval and manual replay;
  [WS-CLI-001-16](WS-CLI-001-16.md), deliberate evaluation-policy correction with one saved unified successor;
  [WS-CLI-001-17](WS-CLI-001-17.md), exact guide-proposal correction and explicit saved-successor dispatch;
  [WS-CLI-001-18](WS-CLI-001-18.md), separate exact complete-guide activation and immutable receipt replay;
  [WS-CLI-001-19](WS-CLI-001-19.md), separate manager draft creation, screening and release;
  [WS-CLI-001-20](WS-CLI-001-20.md), explicit exact-project Submitter/Reviewer issuance and revocation;
  [WS-CLI-001-21](WS-CLI-001-21.md), filtered grant browsing and exact qualification/revocation history;
  [WS-CLI-001-22](WS-CLI-001-22.md), Finance current policy discovery and exact retained-version inspection;
  [WS-CLI-001-23](WS-CLI-001-23.md), Finance draft creation, rule replacement, publication and retirement;
  [WS-CLI-001-24](WS-CLI-001-24.md), self/project contribution evidence and exact private CSV export;
  [WS-CLI-001-25](WS-CLI-001-25.md), explicit public ZIP preparation, Submission replay/history and contributor checker findings;
  [WS-CLI-001-28](WS-CLI-001-28.md), privileged actor, identity-link, grant-history and catalogue reads;
  [PILOT-13](../../changes/pilot13-assigned-task-guide-documents.md), assigned-task locked-guide listing/download;
  [PILOT-02](../../changes/pilot02-bulk-transitions-cli.md), explicit CSV conversion,
  source custody, atomic import, batch status and whole-batch screen/release.

## Current boundary

[WS-CLI-001-28](WS-CLI-001-28.md) adds six existing privileged public reads:
exact actor profile/identity-link inspection, explicitly scoped actor/admin grant
history pages, and permission/role-definition catalogues. These commands remain
separate from self-profile operations, preserve opaque cursors and backend
disclosure, and never treat observed grants as local authorization.

Current public-only completion plan (inventory at main `51b868071`): FastAPI
OpenAPI declared 125 non-health method/path operations, of which 69 had CLI
coverage before #606. Counts are an inventory, not a runtime certification or
a coverage target. Contributor `me` browsing, preparation reads, manager work browsing,
guide list/show/readiness/document reads and contribution-policy listing are
also delivered by the merged PILOT read work; reuse those owners.

The original remaining 56 operations are grouped below; #606's six reads are
delivered by this PR, leaving 50 in the listed boundaries. Each issue is a
bounded client outcome, implemented in its own worktree/PR; split an issue if its
concrete diff would be unreviewable. Delivered rows are identified below; the
other boundaries remain planned.
[WS-CLI-001-30](WS-CLI-001-30.md) delivers #499's history/current
revision-context presentation correction.

| Issue | Public-client boundary | Operations |
|---|---|---:|
| [#599](https://github.com/Flow-Research/workstream/issues/599) | Guide edit and review/revision policy configuration | 3 |
| [#600](https://github.com/Flow-Research/workstream/issues/600) | Active guide, sufficiency and intake policy inspection | 7 |
| [#601](https://github.com/Flow-Research/workstream/issues/601) | Governed sufficiency/manual artifact-policy writes | 4 |
| [#602](https://github.com/Flow-Research/workstream/issues/602) | Manager task context and submission/checker evidence | 7 |
| [#603](https://github.com/Flow-Research/workstream/issues/603) | Exact revision-context repair | 1 |
| [#604](https://github.com/Flow-Research/workstream/issues/604) | Contributor-candidate discovery | 1 |
| [#605](https://github.com/Flow-Research/workstream/issues/605) | Retained task-import source download | 1 |
| [#606](https://github.com/Flow-Research/workstream/issues/606) | Actor/admin authority inspection — delivered by [WS-CLI-001-28](WS-CLI-001-28.md) | 6 |
| [#607](https://github.com/Flow-Research/workstream/issues/607) | Actor/identity lifecycle and administrative writes | 8 |
| [#608](https://github.com/Flow-Research/workstream/issues/608) | External-checker registry and explicit retry | 4 |
| [#609](https://github.com/Flow-Research/workstream/issues/609) | Operator task inspection/start override | 3 |
| [#610](https://github.com/Flow-Research/workstream/issues/610) | Task audit context/evidence | 2 |
| [#611](https://github.com/Flow-Research/workstream/issues/611) | Artifact operator inspection/recovery | 9 |

Continue independent guide configuration, manager evidence and checker
operations. Inspection informs subsequent manual mutations and repair; each
PR must still build independently or declare its exact stacked
dependency. Root registrations are additive; shared transport changes have one
owner and are reused rather than copied. Each PR reconciles its own README and
roadmap claims, while the lead coordinates overview/index changes. No generic
raw-HTTP executor, private backend path, new business rules or eager TUI is needed.
No material product decision is missing for these existing-contract clients.

The backend exposes `GET /api/v1/actors/me` and
`GET /api/v1/actors/me/authorization-context` in
`backend/app/api/routes/auth.py`. The selected 29-operation
[external-client drill](../../../docs/engineering/external-api-drill.md) covers
those operations, but is not a certification of every public or hidden route.
The independent [MCP adapter](../../../mcp_server/README.md) forwards caller
bearers to the same API; it is not a CLI client library. The independent Go
package under `cli/` implements `whoami`, `project access PROJECT_ID`, and
`profile update` for caller-owned human display fields. `project show PROJECT_ID`
reads only the existing public project's server-selected disclosure shape.
`project tasks PROJECT_ID` and `project task PROJECT_ID TASK_ID` add the public
manager queue/detail journey with server-owned authority on each page.
`task ready PROJECT_ID` and `task show TASK_ID` add the contributor projection
with exact Submitter authority and server-owned assignment visibility.
`task claim TASK_ID --idempotency-key UUID` and `task start` add the public
contributor writes, with server-owned fresh authority, assignment and lineage.
Exact caller keys support manual replay; uncertainty never triggers automatic retries.
`task context TASK_ID` and `task requirements TASK_ID` read governing guide,
policy selectors, server action hints and locked intake rules. Hints are not
authority; intake uses the separate public `task prepare` and `task submit`
commands. Submission history and checker findings have separate bounded reads.
`project create --name TEXT --slug TEXT --idempotency-key UUID` creates a draft
shell through the public POST. The API owns system-scoped creation authority
and committed recovery; guide upload, approval and activation are not added.
`project guide create PROJECT_ID --input FILE --idempotency-key UUID` declares
a draft guide, task examples and document targets; setup awaits document upload.
This is a stored creation receipt, not live readiness. The API reauthorizes
guide creation replay, unlike project-shell committed recovery.
`project guide upload PROJECT_ID GUIDE_ID DOCUMENT_ID --file FILE --media-type
MIME --idempotency-key UUID` streams one declared original through the public
binary POST and rechecks the open original's size, modification time and full hash
before success. Its exact-byte receipt establishes storage only, not setup readiness,
approval or activation; unconfirmed outcomes require deliberate unchanged-input
replay. `task guide TASK_ID [--download DIR]` lists or downloads the assigned
task's locked originals with verified byte identity; setup examples stay private.
`project guide setup PROJECT_ID GUIDE_ID` reads the latest exact-guide setup
and compilation lineage through one public GET. It does not poll, execute setup,
approve policies or activate the guide; successful reading is not readiness.
`project guide proposal PROJECT_ID GUIDE_ID COMPILATION_ID` reads the explicit
finalized proposal, complete findings, requirements and intake/evaluation
bindings, without selecting latest, approving, correcting or activating it.
`project guide approve-pre PROJECT_ID GUIDE_ID COMPILATION_ID --input FILE
--idempotency-key UUID` commits the separately prepared intake decision. It
never acknowledges warnings automatically or refetches latest. Backend authority
and currentness apply on replay; an immutable receipt does not establish
post-policy approval, post-policy job delivery or guide activation.
`project guide post-policy PROJECT_ID GUIDE_ID COMPILATION_ID POLICY_ID` reads
the exact canonical evaluation policy, unified findings, activation selectors
and saved correction. Compiled, approved and superseded/non-current packages
remain readable observations; no decision, dispatch or readiness rule is added.
`project guide approve-post PROJECT_ID GUIDE_ID COMPILATION_ID POLICY_ID --input
FILE --idempotency-key UUID` commits a separate evaluation-policy decision using
the inspected exact target. A validated receipt is not guide activation; fresh
backend authority applies on manual replay and uncertain writes are not retried.
`project guide correct-post PROJECT_ID GUIDE_ID COMPILATION_ID POLICY_ID --input
FILE --idempotency-key UUID` requests a unified setup successor for an inspected
policy with explicit manager feedback. A validated correction receipt identifies
saved successor intent, not dispatch, inference, policy replacement or activation.
`project guide correct PROJECT_ID GUIDE_ID COMPILATION_ID --input FILE
--idempotency-key UUID` saves feedback for the exact proposal.
`project guide dispatch-correction PROJECT_ID GUIDE_ID COMPILATION_ID --input FILE`
explicitly dispatches the successor selected by the saved correction receipt.
It observes backend diagnostic status, not completion, approval or activation.
`project guide activate PROJECT_ID GUIDE_ID --input FILE --idempotency-key UUID`
separately submits exact approved policy selections and validates the immutable
activation receipt. It does not publish contribution policy, approve missing
inputs or infer readiness; the backend owns authority and supersession.
`project task create PROJECT_ID --input FILE --idempotency-key UUID`,
`project task screen PROJECT_ID TASK_ID --idempotency-key UUID [--reason TEXT]`
and `project task release PROJECT_ID TASK_ID --idempotency-key UUID --reason TEXT`
prepare individual work through three deliberate public writes. Workstream owns
active-guide locking, readiness, lifecycle and fresh-authority replay; management
receipts do not enlarge contributor disclosure.
`project role-grant issue PROJECT_ID --input FILE --idempotency-key UUID` and
`project role-grant revoke PROJECT_ID GRANT_ID --input FILE --idempotency-key UUID`
submit caller-prepared contributor-role decisions to public AUTH. Qualification
capture, exact-project manager authority and fresh-authorized replay stay backend
owned; no role cache, automatic grant or AdminRole command is added.
`project role-grant list PROJECT_ID` observes one filtered count-free page with
explicit opaque continuation; `project role-grant show PROJECT_ID GRANT_ID`
observes exact public qualification, provenance and revocation history. Neither
read grants authority or verifies permission for a later write.
`project contribution-policy current PROJECT_ID` and
`project contribution-policy show PROJECT_ID POLICY_ID [--version UUID]` expose
the complete authorized Finance policy graph and current selectors. The backend
selects the published version ahead of an open draft unless explicitly overridden
by a version selector; current Finance authority governs historical reads too.
PM-only authority does not suffice. These reads never publish, retire or pay.
`project contribution-policy create`, `update`, `publish` and `retire` provide
separate public Finance mutations with exact selectors and explicit retry keys.
Original event receipts survive later lifecycle changes, with current authority
required on replay. Guide activation remains a separate manager operation.
`project task-batch` provides PILOT-02's separate local CSV conversion, source
declaration/upload/status, atomic DRAFT import, batch status and explicit atomic
screen/release. It shares this binary and public API client, not a second CLI.
Batch writes use their own bounded request budget; ordinary contribution reads
retain their existing read deadline. `contributions` and `project contributions`
read existing authorized evidence and optionally save exact private server CSV;
neither requires batch-origin Tasks or activates a lifecycle writer.
All have text/JSON
output and built-binary integration proof. Mutations preserve omitted/null
semantics and explicitly report uncertain outcomes without automatic retries.
Further public workflows
and binary distribution remain proposed below.

## Design

Use one independently built Go `workstream` command. Commands call only public
REST operations; Workstream verifies the caller's Flow-issued bearer and owns
admission, authorization, policy, evidence, and all writes. The CLI does not
verify JWTs, call Flow Identity, import backend internals, cache roles, or infer
authority from a prior read. A human bearer used by an AI-driven CLI remains
that human's credential, not a registered agent identity.

Make every operation complete without a terminal: stable JSON output, safe
errors, exit status, and no required prompts. Add optional terminal assistance
only where it improves an actual workflow. A future `workstream ui` can browse
public queues and evidence when enough of that lifecycle is ready; it must use
the same client operations and never become a second state machine. Prefer
purposeful commands over generating a flag mirror of every OpenAPI route.

Go is the chosen implementation language. Cobra owns command parsing/help and
completion. Bubble Tea is a candidate for a later, bounded TUI change, not a
dependency of the foundation. Do not add Python, TypeScript, or Rust duplicate
CLIs. Keep the package independent of backend and MCP runtime dependencies.

## Delivered and later boundaries

1. **WS-CLI-001-01:** Independent Go package, safe caller-token transport, exact
   self-profile and project-authorization reads, human/JSON output, built-binary
   integration proof, package CI, and documentation. `GET /actors/me` can cause server-owned first
   admission and last-seen updates; the CLI must not describe it as side-effect
   free.
2. **WS-CLI-001-02:** Human profile editing through the existing public PATCH,
   with explicit omission/null and uncertain-mutation behavior. It changes no
   identity, authority or backend policy.
3. **WS-CLI-001-03:** Inspect a known project alongside its current authority,
   through the public project read. Preserve administrative/contributor response
   boundaries; do not invent a public project-list contract.
4. **WS-CLI-001-04:** Browse a manager task page and open its exact project/task
   detail, passing opaque continuation unchanged without automatic pagination.
5. **WS-CLI-001-05:** Discover one ready-task page and inspect contributor
   instructions through public reads, without management metadata or task writes.
6. **WS-CLI-001-06:** Claim ready work and start the caller's assignment through
   public POSTs with caller-supplied keys, exact response validation and explicit
   uncertain outcomes. No local authority decisions or operator override.
7. **WS-CLI-001-07:** Inspect contributor work context and exact submission
   requirements through public reads. Preserve historical selectors, server
   hints and contributor disclosure without fetching files or evaluating policy.
8. **WS-CLI-001-08:** Create a draft project shell through the public POST with
   explicit caller-supplied keys, exact 201/full-response validation and unknown
   outcomes. Reuse project inspection parsing/output; no guide activation.
9. **WS-CLI-001-09:** Declare a guide, required illustrative tasks and source
   document targets through public POST using an exact bounded JSON file.
   Setup awaits actual original upload.
10. **WS-CLI-001-10:** Upload one declared PDF/DOCX/PPTX or UTF-8 Markdown (`.md`)
   original through public binary POST; validate storage receipt against local bytes and preserve manual
   replay custody. Approval and activation remain.
11. **WS-CLI-001-11:** Inspect latest exact-guide setup and compilation lineage
    through the public diagnostic read. No polling, local readiness rules,
    execution, approval or activation.
12. **WS-CLI-001-12:** Inspect an explicitly selected finalized proposal through
    its public GET, retaining complete display findings and distinct intake and
    evaluation proposals without making a decision or substituting latest.
13. **WS-CLI-001-13:** Approve an explicitly selected intake proposal through the
    public POST with caller-prepared target/warning/prior selectors and exact
    manual replay custody. No post-policy decision or guide activation.
14. **WS-CLI-001-14:** Inspect the explicitly selected derived evaluation policy,
    upstream proposal/findings, activation selectors and saved correction through
    one public GET; preserve historical observations without local decisions.
15. **WS-CLI-001-15:** Separately approve an explicitly selected evaluation policy
    through public POST, using the caller's inspected target and exact manual
    replay custody; validate the complete immutable receipt without activation.
16. **WS-CLI-001-16:** Request correction of an explicitly selected evaluation
    policy through public POST with caller-prepared feedback/target and exact
    manual replay; validate one saved successor without dispatch or activation.
17. **WS-CLI-001-17:** Save an exact guide-proposal correction and explicitly
    dispatch its retained successor through public POSTs, binding the diagnostic
    response to the saved receipt without automatic replay or activation.
18. **WS-CLI-001-18:** Activate explicitly selected, separately approved guide
    policies through the public POST. Validate the immutable command/receipt
    binding; leave readiness, authorization and supersession to the backend.
19. **WS-CLI-001-19:** Prepare individual tasks through separate manager draft
    create, screen and release calls. Validate full management receipts and
    explicit replay; do not import, automatically release or choose policies.
20. **WS-CLI-001-20:** Explicit Submitter/Reviewer issuance and revocation with
    supplied qualifications/reasons, full receipt binding and fresh-authorized
    replay. No grant discovery or automatic eligibility.
21. **WS-CLI-001-21:** Filtered project-grant pagination and exact grant history
   through public GETs, complete qualification/provenance disclosure and fresh
   authority on each call. No actor discovery or automatic decisions.
22. **WS-CLI-001-22:** Current Finance policy discovery and backend-selected or
   exact retained-version inspection, including empty drafts and complete award
   definitions. No Finance mutation, publication or local readiness decisions.
23. **WS-CLI-001-23:** Finance draft creation, complete rule replacement,
   publication and retirement through existing public operations, with explicit
   caller keys, immutable event receipts and no automatic retries.
24. **WS-CLI-001-24:** Self and authorized project contribution-evidence reads,
   exact decimals, recorded-time/type filters and private server CSV export.
   No local recognition, payment decision or lifecycle activation.
   Remaining commands are selected only from currently public, usable API
   contracts not already owned by another initiative. PILOT-02 batch CLI is
   delivered in this package; reuse it rather than duplicate it.
25. **WS-CLI-001-25 / PILOT-12:** Public ZIP preparation with exact caller key,
   separate admission-backed creation/replay, and bounded submission/checker
   history. No automatic retry/polling or inferred acceptance. Revision-change
   summaries are available through current task context, not historical rows;
   [WS-CLI-001-30](WS-CLI-001-30.md) corrects the remaining text. The separate
   #552 public setup/worker drill is delivered; full native CLI journey proof remains.
   Unfinished human review/revision is not current CLI implementation scope.
26. **Optional TUI:** Add a focused public queue/evidence view after its API
   workflow is complete. Never require a TUI for agents or scripts.

## Risks and proof

The highest risks are bearer leakage, an unsafe configurable destination,
redirect/proxy credential forwarding, reporting stale authorization as current,
API shape drift, and falsely advertising hidden lifecycle work as live. Keep
tokens out of arguments, URLs, config files, output, logs, and error text;
reject non-loopback plaintext HTTP; fail closed on redirects and malformed
responses. Prove the first boundary through two built-binary, process-level
integration suites: one against an isolated real Workstream API for admission,
exact response parity, project authority and denial; one against an adversarial
HTTP fixture for credential/destination safety, malformed responses and
noninteractive output. The fixture is not a substitute for the real API.
Avoid function-level tests, coverage targets and duplicated assertions for
this CLI slice. Add a focused case only for a distinct observable contract or
reproduced failure. The shipped CLI calls only the named public API routes;
test setup may use the documented local bootstrap to arrange authority but
cannot create a private CLI dependency.

The CLI is a separate client package, not an ADR 0014 backend adapter. It does
not change backend authority or deploy an external provider. A release process,
installer/signing, and a full contribution journey remain future boundaries;
source build and CI are not claims of public distribution.
