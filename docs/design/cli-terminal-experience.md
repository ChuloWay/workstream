# Workstream terminal experience — implemented first slice and proposed extensions

Status: WS-CLI-001-48 implements the bounded contributor read slice;
WS-CLI-001-49 extends it with findings and verified guide downloads below;
the broader workspace and mutation experience remains proposed. This is not a
new product/API contract. The opt-in `workstream tui` shares the existing Go
binary and public client. Explicit commands in [the CLI reference](../../cli/README.md)
remain the non-interactive interface for humans and agents. Implementation is
not a claim of deployment, completed native verification or public distribution.

Source reconciliation: public operations below were checked against `main`
`7f6a71a69` on 2026-10-23. The release automation from
[WS-CLI-001-44](https://github.com/Flow-Research/workstream/blob/47760fa9dacf3d2000a073ee41c275c7c8b43ba6/.commitrail/initiatives/WS-CLI-001/WS-CLI-001-44.md)
is merged; no public binary publication is established. The project catalogue
in [PR #665](https://github.com/Flow-Research/workstream/pull/665) is merged and
available to the explicit CLI, but is not used by this contributor workbench.
The first slice is reconciled with main `2e6cee003`; recheck merged
owners before implementing any later slice.

## Product shape

The terminal should feel like a precise control room: quiet dark slate, a cyan
focus line, peach for a deliberate action, and enough negative space to read the
work. The useful sequence is **browse → inspect → act → observe**. It is not a
simulation of system health, a second policy engine, or a dashboard of invented
scores. Show a fact only when a public response supplies it; label the time and
scope of each observation. No animation, percentage, or “complete” badge should
suggest that an asynchronous check, Review, acceptance, award, or fulfillment
has happened before the matching backend fact is observed.

One launch opens the contributor workbench. Project selection comes from
`workstream me projects`, which lists projects where this actor has an exact
grant; it is not a public project directory. Within a selected project, `Ready`
uses `workstream task ready PROJECT_ID`, while `Mine` and `Submissions` use the
actor-owned collections filtered to that project. A person can change workspace
to Manager, Finance, Operator, or Audit explicitly. Each workspace uses its own
public routes and server-selected disclosure; a displayed role, permission or
`next_action` is never local authority to execute a later operation. If a
workspace's read is denied, show the denial, not an empty queue or a substitute
projection. An administrator with covering authority may not have an exact
project grant in `me projects`; Manager, Finance, Operator, and Audit therefore
also offer **Open exact project ID**. They do not pretend that recent local IDs
or `me projects` are a complete administrative project catalogue. There is no
contributor-wide project directory. Merged PR #665
provides `GET /api/v1/projects` and `workstream project list`: one authorized
page of project ID, name and status, available only to current system-scoped
Project Manager, Operator, Finance Authority or Audit Authority readers. An
Access Administrator alone, exact-project administrative grants and contributor
grants do not enumerate this catalogue. This is the backing API for a later
system-reader picker, not a replacement for `me projects`
or a grant to read a guide or mutate a project. Exact-project managers/finance/
audit readers still need selection through separately held contributor membership,
if any, or **Open exact project ID**; their administrative grant alone does not
populate `me projects`. A catalogue denial must never trigger a hidden fallback
request. System-reader
catalogue pages follow the same explicit pagination and error rules below.

The TUI opens only on an interactive terminal; non-TTY use receives a bounded
error pointing to ordinary `workstream --help` and `--output json`. It uses the
same supplied `WORKSTREAM_API_URL` and `WORKSTREAM_TOKEN` contract as the CLI;
there is no Workstream login, token acquisition, keychain, browser callback or
credential store. It never prints a bearer. A project or resource ID may be
carried internally from a selected row to a detail/write request, eliminating
UUID transcription; that ID remains visible in the detail and confirmation.

### Information architecture

| Workspace | First surface | Inspect | Candidate deliberate action |
|---|---|---|---|
| Contributor | Exact-grant project picker; within it Ready, Mine, Submissions | Contributor-safe task detail, work context, locked guide and intake requirements; own preparation, Submission and checker evidence | Claim, start, prepare ZIP, then separately create Submission from a ready admission |
| Manager | Selected project's task queue and summary | Guide status/readiness, task/context, preparation counts, Submission/checker history | Create/screen/release a task; guide, import, grants or revision repair stay explicit CLI handoffs until their exact forms are designed |
| Finance | Selected project's current and retained ContributionPolicy versions | Exact policy rules and contribution evidence/earned award facts | Draft/update/publish/retire only through explicit reviewed forms; no payout control |
| Operator | Project-scoped checker retry sources, uncertain deliveries, and task/custody diagnostics | Exact source run/event/job and locked references | Explicit reasoned retry or reconciliation; no inferred recovery from a list |
| Audit | Exact project/task selector | Locked context and paged lifecycle evidence | Read only |

This is navigation, not a promise that every candidate action ships in the
first TUI slice. The overall goal is the connected contributor and management
journeys below. The smallest first slice is the read-only contributor workbench
specified under Implementation fit; later slices add one reviewed operation
at a time until that journey can be performed without an implicit write chain.
Administrative actor/grant writes stay in the explicit CLI until separately
designed; there is no global actor picker or generic raw-HTTP console. Genuine
human Review decisions are not part of the current CLI inventory and must not
be pictured as working TUI actions.

## Main screen, 120 × 40

Illustrative values and local observation time below are not current system
claims. `Ready` and `Mine` are distinct server projections; opening a row makes
a fresh exact-resource read. The 21-row drawing reaches at most 98 cells inside
a 120×40 terminal, leaving room for margins and long task text; the lower rows
become scrollable detail rather than decorative filler.

```text
 WORKSTREAM  /  CONTRIBUTE                 Project: Aster Research  v             14:02 observed
 ────────────────────────────────────────────────────────────────────────────────────────────────
 Ready  03       Mine  02       Submissions  01       Evidence                 / filter   ? keys

  READY IN THIS PROJECT (page 1)              │  SELECTED TASK
  >  Evaluate source evidence    ready        │  Evaluate source evidence
     Trace failure modes         ready        │  Status: ready     Est: 45 min
     Test intake package         ready        │  Skills: analysis, testing
                                            │
  Your active work                         │  Produce attributable findings for the
     Draft result matrix       in_progress   │  supplied evidence. [more ↓]
     Revise benchmark notes    needs_revision│
                                            │  Locked terms: unpaid / exact awards
                                            │  shown from the task's policy version
                                            │
                                            │  NEXT  Inspect task  ↵
                                            │        Claim…         a
                                            │
 ────────────────────────────────────────────────────────────────────────────────────────────────
 ↑↓ select   ↵ inspect   a actions   g project   w workspace   r refresh   c CLI   ? help   q quit
 Ready: observed 14:02 · page 1 · more available   │  A read is not a reservation or authority
```

The left column is a worklist, not a merged cross-project feed. Counts on the
top line refer only to the currently fetched page or to separately labelled
summary facts; do not present page length as a project-wide count. If a list is
paged, show `page 1 · more available` and let `n` fetch the next page with the
same project, filters, limit and opaque cursor. Never decode a cursor, silently
walk pages, or mix cursor families. Before exact detail loads, the right pane
says “Open to inspect”; ready summaries do not contain full instructions.

Inside detail, use a short vertical sequence rather than modal nesting:
`Overview → Instructions → Locked context → Intake → History`. Long contents
scroll in one viewport. The locked guide's document labels, media types, sizes
and hashes are displayed from task context after an active assignment; download
is an explicit action to an existing directory, with no automatic PDF open or
pre-download integrity claim. The existing CLI verifies bytes during download.

## Compact screen, 80 × 24

At narrow width, list and detail are sequential views, not cramped columns.
The same selection and exact project survive the transition. No essential state
is encoded by color or truncated-only text. This 18-row drawing's longest line
is 68 cells inside an 80×24 terminal.

```text
 WORKSTREAM / CONTRIBUTE           Aster Research     observed 14:02
 ────────────────────────────────────────────────────────────────
 Ready   Mine   Submissions   Evidence             / filter  ?

 READY · page 1 · more available
 > Evaluate source evidence                 ready
   Trace failure modes                      ready
   Test intake package                      ready

   Estimated: 45 min · analysis, testing
   Locked terms: see task detail

 ↵ inspect selected task
 a actions · g project · w workspace · n next page

 ────────────────────────────────────────────────────────────────
 ↑↓ select   r refresh   c CLI   ? help   q quit
 A ready row is not reserved; claim is decided by Workstream.
```

Below roughly 70 columns or 20 rows, use a single plain list/detail view with
wrapped labels and vertical scrolling. If even the help/confirmation cannot be
displayed legibly, stop before any write and give the exact command path. Resize
must retain the selected resource but may reflow content; it must not commit an
action. Alternate-screen rendering, cursor keys, Enter, Tab, Esc, `?`, letters,
and Ctrl+C must work across supported Linux, macOS and Windows terminals without
Unix signals, shell-specific bindings, mouse, clipboard, or Unicode glyphs as
requirements. Mouse support may be additive only.

## Keyboard drill and action contract

1. `workstream tui` checks terminal/configuration and loads the actor's exact-grant
   projects. `g` opens the project picker; `↑/↓`, type-to-filter fetched names,
   and `Enter` choose one. Filtering is local to fetched rows and is labelled
   so it cannot imply server-wide search. `w` changes workspace; a change never
   executes a privileged call by virtue of a cached role.
2. `↑/↓` selects a row, `Enter` opens a fresh detail, `Tab` advances the
   detail sections, `Esc` returns. `r` refreshes the current view and clears
   stale cursor continuation. `/` filters the current fetched page, `n` loads
   the next authorized page, and `?` shows all current keys. No rapid navigation
   key invokes a write.
3. `a` opens only actions with a designed flow for the selected resource. A
   server `next_action` may help label a candidate, but never proves eligibility.
   `Enter` opens a review sheet containing action verb, exact project/task and
   assignment, relevant locked policy/admission/revision identifiers, packet
   fields or file selection, and the expected meaning of a successful receipt.
   Before Claim, the sheet also shows the exact ContributionPolicyVersion and
   both accepted-submission and completed-review terms from the fresh
   contributor-safe task detail: each is either `unpaid` or the returned
   instrument, unit and decimal-string quantity rows. If that detail refresh
   is stale, denied, incomplete or failed, Claim cannot be confirmed. These
   are potential earned terms, not a promise of acceptance or fulfillment.
   `y` sends exactly one request **only while the confirmation itself has focus**;
   pasted text and keys typed into a field cannot commit it. `Esc` is the
   default cancellation. Once sent, disable duplicate dispatch from repeated
   keys, resize events or network callbacks until the result is classified.
   No action chains
   claim → start, preparation → Submission, guide approvals → activation, or
   checker result → acceptance.
4. After a known receipt, show its exact result and a separate `r` to observe
   the current resource. After a canonical denial, show the server code and
   correlation ID if present. After an uncertain write, freeze the action
   context on a recovery sheet; do not auto-retry or offer a fresh key as the
   primary action. The observation link is explicitly not rollback proof.
5. `c` displays an inert argv recipe for the equivalent existing CLI command,
   with selected IDs as separate arguments. An optional copyable rendering may
   use only an explicitly chosen and tested POSIX-shell or PowerShell quoting
   mode; never assume that one quoted string works across platforms, especially
   for packet text or paths. It does not launch a shell, place credentials in a
   command, assume OS clipboard access, or imply that a TUI-only action exists
   in the explicit CLI. If exact recovery inputs are not available, it says so
   rather than fabricating a command.

The footer uses a fixed key vocabulary. `q` warns before exit when a write is
unresolved; Ctrl+C always permits exit and preserves the private receipt. Neither
resolves or replays it. For a TUI write to
ship, a bounded private operation receipt must be committed **before** sending
the one request. It binds the API origin, current actor identity, action, exact
project/resource selectors, key or admission, packet/reason/revision inputs,
and a digest/fingerprint of any source file; it excludes the Flow bearer and
raw ZIP bytes. A source file must still be present and verified unchanged for
manual preparation replay. The receipt is app-private per operating-system
user (restrictive POSIX mode or Windows ACL), atomic against interruption,
bounded in count/size, and safe under concurrent TUI processes. Startup offers
an explicit recovery list only for the same origin and actor; it never sends a
write while reconciling. Expired receipts need a deliberate resolution or
privacy-preserving purge flow, not silent deletion or a new key. Exact storage
format, lifetime, path, filesystem protections, and source-fingerprint
semantics are an implementation decision gate to be reviewed before a mutation
slice. This is **TUI-only** state; the non-interactive CLI must remain stateless
and must not gain implicit files. Do not create a generic all-POST journal or
declare a history read sufficient for recovery. An interruption just before or
after sending is uncertain until an exact replay receipt or adequate
authoritative evidence establishes the outcome.

### Contributor walkthrough and truth labels

| Screen/step | Public owner and exact CLI path | Truthful label |
|---|---|---|
| Project and ready work | `me projects`; `task ready PROJECT_ID`; `task show TASK_ID` | “Available to inspect”, never “reserved” |
| Active assignment | `me assignments --project PROJECT_ID`; `task context TASK_ID`; `task requirements TASK_ID` | “Your current assignment”; fresh read may change |
| Claim/start | `task claim TASK_ID --idempotency-key UUID`; separate `task start TASK_ID --idempotency-key UUID` | “Claim recorded” / “Start recorded”, only after complete receipt |
| Locked instructions | `task context TASK_ID`; `task guide TASK_ID [--download DIR]` | “Locked guide”; bytes verified only after successful explicit download |
| Intake | `task prepare TASK_ID --assignment UUID --file ZIP --idempotency-key UUID` plus exact packet/revision flags | “Preparation”; `ready` receipt supplies admission; no Submission yet |
| Immutable attempt | `task submit TASK_ID --assignment UUID --admission UUID` plus the same packet | “Submission created”; not acceptance or a Review |
| Evaluation and outcome | `task preparations TASK_ID`, `task submissions TASK_ID`, `submission show SUBMISSION_ID`, `submission findings SUBMISSION_ID` | Checker findings are evidence; `accepted`, `needs_revision`, `rejected` and `review_pending` appear only from public stored outcome |
| Contribution evidence | `contributions --project PROJECT_ID` | Earned immutable facts and exact award terms, not proof of fulfillment |

Preparation's packet is the exact assignment, optional predecessor, summary and
attestation, with an exact revision preparation ID/digest acknowledgement when
required. A `ready` admission can be used for the separate Submission request
with the same packet. Other preparation states are not success or permission to
submit; show their bounded status/findings and an observational read. A failed
intake does not create a Submission. For checker-requested revision, show the
current `revision_context` and exact parent pair, and warn that human Review
revision is not yet a delivered CLI journey. After submission, `review_pending`
means pending human review under the locked policy; passing checks do not make
the checker an acceptor. Under a supported false ReviewPolicy, required checks
can invoke the shared authorized FinalAcceptance, but the UI waits for the
stored outcome and ContributionRecord rather than predicting it.

Unknown-response language must be operation-specific. Claim/start and most
keyed writes retain action, resource, reason/inputs and caller-owned key for
manual unchanged replay; a later read does not prove rollback. Preparation
requires the same task, assignment, ZIP bytes, packet, revision acknowledgement
and preparation key. Submission replay instead uses the exact admission and
packet—not a generic idempotency key. Preparation and Submission history do not
expose all original replay inputs, so their mere presence/absence cannot clear
an uncertain receipt. An expired/revoked Flow bearer or grant
can make even an exact replay fail; the TUI never treats a prior read or receipt
as authority. An observed `needs_revision` is not a prompt to silently submit a
new ZIP; the contributor inspects the current context and requirements first.

Checker evidence is a separate view from outcome. Show each returned finding's
`check_id`, severity/status, message and suggested fix, and its optional
`path:line` only when present; do not synthesize a failed check from a missing
field. Distinguish blocking, warning and `coverage_incomplete` counts. A
coverage gap may route to `needs_revision` under a false ReviewPolicy rather
than acceptance; display the stored Submission outcome/reason, not a TUI verdict.

### Management walkthrough and bounded handoffs

Management is a connected setup → release → observation → diagnosis experience,
not a mixed-role dashboard. Workspace choice changes navigation only; a manager
cannot enter Finance or Operator by reusing a manager response. Until a step's
forms and exact recovery are implemented, `c` presents the existing command's
inert argv/input-file recipe and makes the handoff explicit. It never executes
that command or claims the whole flow is already a TUI capability.

| Step | Existing public CLI operation | Screen or handoff boundary |
|---|---|---|
| Select and inspect | Exact-grant `me projects` or exact-ID entry; `project show`, `project access PROJECT_ID`; pending system catalogue as above | Current project identity and safe projection; access is observation, not a write grant |
| Declare and prepare guide | `project create`; `project guide create`, `edit`, `upload`, `setup`, `proposal`, `post-policy` | Exact project/guide/compilation/policy forms remain CLI handoffs; setup proposals are not runtime checker implementations |
| Lock approved rules | `project guide set-review-policy`, `set-revision-policy`, `approve-pre`, `approve-post`, `readiness`, `activate` | Separate operations and confirmations; retain default human review and explicit false-policy branch; readiness is not activation |
| Resolve guide feedback | `project guide sufficiency create`, `acknowledge-warnings`, `correct`, `correct-post`, `dispatch-correction` | Diagnostics/warnings are not approvals; correction dispatch needs its saved exact receipt, not a new generic key |
| Set contribution terms | Finance `project contribution-policy current`, `list`, `show`, `create`, `update`, `publish`, `retire` | Separate Finance workspace; publication is not guide binding, earning or fulfillment |
| Admit contributors and work | `project role-grant list`, `show`, `candidates`, `issue`, `revoke`; `project task create`, `screen`, `release`; `project task-batch` commands | Grants/import remain CLI handoffs; task release is separate from create/screen and locks the backend-owned context |
| Observe attempts | `project tasks`, `task`, `summary`, `assignments`, `preparations`, `submissions`, `submission`, `checker-runs` | Manager projections, not contributor-shaped substitutes; show exact locked contexts/requirements through their separate manager commands |
| Recover or audit | Operator `operations checker retry-sources`, `retry`, `operations delivery list`, `reconcile`, `operations artifact` commands; Audit `audit task locked-context`, `evidence` | Distinct authorized queues and exact-resource reads; no fabricated human Review or provider/payout controls |

The remaining current guide/artifact-policy and revision-repair commands stay
available in the explicit CLI; listing a family here does not authorize a
generic JSON editor or imply every command is eligible for a TUI form. Human
Review/assignment and its revision journey, compensation fulfillment, and
runtime reputation remain separate product gaps, not empty working screens.

For future Manager/Finance writes, retain exact action, project and resource
selectors, unchanged input contents/reason, and original caller key before
dispatch. Preserve `If-Match` on guide policy edits and any operation-specific
digest/lineage acknowledgement; a policy/detail read does not replace them.
Guide correction dispatch is different: use the saved correction receipt and
its exact project/guide/compilation, never synthesize an idempotency key. Operator
checker retry binds the exact terminal source run, project, reason and key;
delivery reconciliation binds the exact UNKNOWN event, project, reason and
key; artifact retry also binds the expected source-job CAS and task/optional
Submission selectors. None is interchangeable with another recovery action.
Before exposing each write, inspect its typed client and public schema and prove
the specific unknown-response path; no family-wide receipt shortcut is allowed.

## Failure and accessibility states

The status line distinguishes `Loading…`, `Observed HH:MM`, `Stale: refresh
failed`, and `Outcome unknown: recover deliberately`. Use a static ellipsis,
not a synthetic progress meter. Keep visible-screen read polling bounded and
explicit: initial load, user refresh, or a short documented observational
interval only on a visible pending preparation/evaluation screen; never poll
background project queues or mutate on a timer. Apply capped backoff after
transient failures and cancel obsolete reads on navigation. Tag each request
with a screen generation, actor, API origin and selected resource; discard late
responses that no longer match. A refresh does not overlap duplicate writes.
For the proposed foreground observation, start no sooner than five seconds
after the last completed read, then space subsequent pending-state reads at
10, 20 and at most 30 seconds; stop after two minutes on that screen and offer
manual `r`. Keep at most one read in flight. A transient failure uses the next
delay rather than a tight retry; a definitive denial stops polling immediately.
The implementation must validate this budget against the existing transport
timeouts and server limits before shipping.

When a transient read fails, previously rendered data may remain only with a
prominent stale label and direct actions disabled until fresh inspection. On
401, 403 or a concealed 404, immediately clear protected detail and cached
pages for the affected scope and disable actions; do not leave prior private
content visible as if still authorized. A denied or concealed resource is not
a zero-item success. Show the error code/correlation ID when safe, without
echoing paths, token, raw network details or untrusted control bytes. For a
missing/rejected bearer, say “Save the recovery receipt if needed, exit, renew
the token in your existing environment, then relaunch.” A child process cannot
see environment changes made later in its parent shell; `r` alone cannot load
a renewed token. Do not offer login or claim to distinguish expiration from
other 401 causes unless the public error actually does. An actual local ZIP
read/upload can show bytes transferred against known file size, but reaching
100% is not server verification, ready admission or Submission creation; label
those as pending until their exact receipts/readbacks arrive. Do not invent
percentages for backend intake or post-submit evaluation.

Use textual state words alongside color. Never blink. Respect `NO_COLOR`,
monochrome and low-color terminals; truecolor is a polish layer, not a
requirement. Suggested dark palette: slate canvas `#101923`, lighter panel
`#192632`, primary text `#EAF2F4`, muted text `#A9BAC3`, cyan focus `#69D7E3`,
peach action `#F2AE91`, amber caution `#E9C37B`, red error `#ED8991`. Select
light-background and ANSI-16 equivalents by terminal capability; all selection
and severity survive as ASCII marker plus label. Avoid half-width decorative
glyphs, terminal hyperlinks, inaccessible dim-only metadata, and color-as-status.
Untrusted project/task text is escaped, wrapped, and never interpreted as ANSI,
OSC links, shell commands, filesystem paths, or control sequences. A plain
single-column mode should be available for screen readers and troublesome
terminal emulators; it keeps the same keys, action confirmation and exact
failure wording, and does not fall back to a different authorization path.

## Implementation fit and explicit gaps

The existing Go binary has Cobra commands and a typed public client under
`cli/internal/api`; the TUI should call that client through the same validated
operations, not shell out to `workstream`, parse human text, introduce private
backend routes, or copy policy decisions. This is a candidate integration
boundary, not authorization to refactor the client. Official upstream
[Bubble Tea](https://github.com/charmbracelet/bubbletea/blob/main/README.md)
documents an event/model/update/view terminal architecture;
[Bubbles](https://github.com/charmbracelet/bubbles/blob/main/README.md) provides
list, viewport, help, and file-picker primitives;
[Lip Gloss](https://github.com/charmbracelet/lipgloss/blob/main/README.md)
supports terminal color-profile downsampling. The first slice selects Bubble
Tea 2.0.10, Bubbles 2.2.1 and Lip Gloss 2.0.6, with resolved modules in the CLI
lockfiles. Native terminal verification remains required on all four supported
targets; accessibility certification is not implied.

### Original first slice (WS-CLI-001-48)

The opt-in **read-only contributor workbench** in the existing Go binary provides:
launch/terminal guard → actor binding → `me projects` page → selected project's
Ready/active Mine/Submissions page → fresh task or owned Submission detail.
This first slice uses exactly nine existing typed client reads: `Profile`,
`MyProjects`, `ReadyTasks`, `MyAssignments`, `MySubmissions`, `ContributorTask`,
`WorkContext`, `SubmissionRequirements` and `Submission`, as bounded in
[WS-CLI-001-48](../../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-48.md).
Ready opens contributor-safe task detail and both locked contribution terms;
active Mine additionally offers explicit context/intake sections. This is a UI
scope cut, not a claim that the backend context/requirements endpoints require
assignment. Guide document disclosure remains backend-owned; no guide bytes
are fetched. Owned Submission detail shows stored outcome and finding counts.
Detailed checker findings and contribution Evidence are clearly labelled
manual CLI handoffs only, not in-TUI evidence browsers or automatic reads.

This slice includes explicit pagination, scoped refresh, stale/denied states,
local filtering labels, safe terminal text, 120×40/80×24 reflow, plain/no-color
mode, keyboard help and inert CLI handoff. No background polling is necessary
in this slice. It excludes all API writes, downloads/local export, automatic
token refresh, recovery files, new management forms, and the pending catalogue.
Use the existing actor profile read to bind the current actor; that GET may
perform the backend's existing admission/last-seen/audit effects, so “read-only”
does not mean an unaudited or side-effect-free backend. No explicit CLI output,
exit status, flags, help for existing commands, or implicit local state changes.

The first slice makes no `cli/internal/api/` changes. A later in-TUI
contribution Evidence slice needs one bounded client prerequisite: a typed
single-page contribution read that returns validated records and the opaque
continuation. The current exported `Contributions(..., io.Writer)` walks up to
100 pages and discards the continuation in its merged output; it cannot back
explicit `n` navigation. Extend the existing client owner using its transport
and record validators, and let the existing complete-export CLI retain its
current behavior. Do not parse stdout, silently traverse pages in the TUI or
implement a duplicate endpoint client. Evidence stays an explicit manual CLI
handoff in the first slice; only a later slice implements and tests this port.
In that later slice, a page with a continuation must
produce exactly one request until the user asks for the next page. Retain the
existing multipage CLI export regression alongside that new proof.

The first slice's bounded implementation record must select exact dependencies
and allowed files and name focused interaction, hostile-response, denial,
resize and terminal-teardown tests. It must not add the deferred typed-page
port or detailed-findings decoder. A later Evidence record must include only
that narrowly scoped shared typed-page prerequisite, not a general client refactor.
Proof must include a built TUI/public-API journey and unchanged explicit CLI
text/JSON/non-TTY behavior; render snapshots alone are not runtime proof.
This proposal is not authorization to begin that next change automatically.

### Guide and findings extension (WS-CLI-001-49)

[The bounded extension](../../.commitrail/initiatives/WS-CLI-001/WS-CLI-001-49.md)
adds Guide after Overview/Context/Intake in Mine detail. Opening Guide fetches
fresh assignment-sensitive WorkContext. Arrows select a document in server
order; `d` enters an existing destination directory, Enter shows exact target
confirmation, and `y` starts the verified download. Metadata is not a verified
byte claim. Private staged bytes become a final UUID-named file only after
verification and receipt by the still-current screen; abort/quit cleanup does
not rely on a late response being rendered. Existing files are never replaced.
No automatic viewer, markdown execution or task examples are added.

Submission detail Tab opens Findings using the existing validated checker-run
read. One page is loaded; `n` requests its explicit continuation and `r` resets
the findings read. Every run retains its identity/current flag and every finding
its status, severity, check ID, path/line, message and suggested fix when supplied.
Successful checks are not acceptance. Contribution Evidence remains a CLI
handoff. There are still no product writes, polling or operation journals.

The shared API now returns the already-validated findings page/exact-run shape
alongside Raw; existing CLI output keeps Raw unchanged. The shared download
owner serves both explicit commands and TUI, preserving directory binding,
private staging, verified bytes and atomic no-overwrite publication.

### Dependency map to the end-to-end experience

| Boundary | Dependency and next usable result |
|---|---|
| Contributor read-only workbench foundation (-48) | Nine existing typed reads and merged backend guards → project/Ready/active Mine/Submissions browse/inspect with explicit pagination; extended by the guide/findings slice below; no catalogue dependency |
| Guide/findings extension | Existing WorkContext and verified document reader plus typed existing checker-run result → ordered guide selection, confirmed download and findings pagination; no backend changes or product writes |
| Later in-TUI contribution Evidence | Narrow shared typed single-page contribution port and preserved complete-export regressions → explicit per-page evidence browsing; not a first-slice prerequisite |
| Claim/start | Read workbench + reviewed per-operation private receipt and exact-key recovery → separate claim and start confirmations |
| Prepare/submit | Claim/start + ZIP source integrity + distinct preparation/admission replay receipts → separate intake and immutable Submission, then stored evaluation/outcome/contribution evidence |
| System workspace project picker | Merged #665 supplies the public API and explicit CLI; later TUI integration uses the four-role system catalogue only, retaining exact-grant/exact-ID entry for actors outside that scope |
| Management read workspaces | Existing Manager/Finance/Operator/Audit typed reads + explicit project selection → scoped queues, details and CLI handoffs; not blocked on catalogue if exact ID is known |
| Management writes | Each read workspace + that operation's reviewed form/authority/recovery proof → setup/release/policy/recovery actions individually, not an all-POST engine |
| Human Review or fulfillment | Stable public contracts and tested lifecycle guards for those specific journeys → separate design/implementation; not enabled by TUI or catalogue work |
| Public binary delivery | Merged #664 automation + protected first publication and independent install proof → distributable binary; neither prerequisite nor proof of local TUI correctness |

The main mutation gate is implementing and proving the private,
operation-specific receipt boundary above for one-shot writes across TUI
crash/terminal loss. Do not expose a mutating action until that exact
operation's unchanged inputs and privacy boundaries are proven.
Other implementation gates: later TUI integration of the existing backend-owned
four-role project catalogue; real API-backed detail/denial tests, narrow terminal
layout snapshots at 120×40 and 80×24, keyboard-only and no-color checks on all
supported platforms, and proof that the explicit CLI/help/JSON behavior remains
unchanged. A TUI is an interface over currently local/backend capability, not
proof of hosted deployment, binary publication, human Review, or payout.
