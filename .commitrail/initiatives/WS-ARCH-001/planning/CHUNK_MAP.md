# WS-ARCH-001 — Current remaining change map

The [current plan](PLAN.md#first-complete-contributor-milestone) owns the first
contributor journey. Hidden ART/TASK Submission creation, CHECKERS execution,
[04E2-B authorized outcomes](../WS-ARCH-001-04E2B.md),
[04F2 checker remediation](../WS-ARCH-001-04F2.md),
[04F3 replacement](../WS-ARCH-001-04F3.md) and
[04F4 Operator retry](../WS-ARCH-001-04F4.md) are delivered.
[PILOT-04](../../../changes/pilot04-external-checker-runtime.md) registers
selected production request/completion delivery with the Workstream default
and digest-pinned external PRE/POST images; the old executable catalogues are
removed. [ARCH-02I-B](../WS-ARCH-001-02IB.md) exposes public admission-backed
entry for initial work and exact checker remediation. [ARCH-04E3-B](../WS-ARCH-001-04E3B.md)
admits complete false-policy guides with supported approved checks and corrects
REV's selected-production manifest. New false/pass effects require an
Operator-authorized LIVE REV generation; a known pre-effect non-live refusal
retries only within the existing OUTBOX attempt budget. Exhaustion dead-letters
without automatic reopen. The default-true `review_pending` branch remains.
A realistic public API/durable-worker drill remains. Human review/revision and
payment fulfillment remain later work. Current production classification has
no `task_setup_blocked` path, so a manager-visible setup-fault hold is future
safety work rather than a prerequisite. Configuration faults must never become
contributor penalties or rewrite a submitted task's locked rules.

The [pre-cutover map](../pre-cutover/CHUNK_MAP.md) preserves completed historical
accounting; the rows below describe owner boundaries and current dependencies.

| Boundary | Owner outcome | Risk | Current dependency |
|---|---|---|---|
| [WS-ARCH-001-03B1](../WS-ARCH-001-03B1.md) | Detached TaskService project/guide display through the existing PROJECTS port | L1 | Complete; 03B2 ready queue facts delivered; projections through 03B8 complete; hidden invalidation delivered by 03B9; 03C1 exact feature authority complete; producer/registration complete in 03C2 |
| [WS-ARCH-001-03B2](../WS-ARCH-001-03B2.md) | Hidden project-scoped contributor ready queue facts with bounded live pagination | L1 | Complete; exact AUTH and public exposure delivered by 03C4 |
| [WS-ARCH-001-03B3](../WS-ARCH-001-03B3.md) | Hidden all-state management and status-only operational task queues | L1 | Complete; task audit evidence delivered by 03B8; exact AUTH/public queue access delivered by 03C4 |
| [WS-ARCH-001-03B4](../WS-ARCH-001-03B4.md) | Hidden contributor and management task detail with fixed fields and exact project/assignment visibility | L1 | Complete; task audit evidence delivered by 03B8; public detail access delivered by 03C5 |
| [WS-ARCH-001-03B5](../WS-ARCH-001-03B5.md) | Replace existing contributor/manager work context with current projections and complete locked policy identities | L1 | Complete; existing authority retained; 03B8 audit evidence delivered; 03B9 hidden invalidation complete; public activation delivered through 03C7 |
| [WS-ARCH-001-03B6](../WS-ARCH-001-03B6.md) | Distinct management, operational and audit locked-context projections using one historical resolver | L1 | Complete; distinct projections publicly exposed by 03C6 |
| [WS-ARCH-001-03B7](../WS-ARCH-001-03B7.md) | Immutable contributor and management requirements through one historical translator and scoped lock | L1 | Complete; exact Contributor and Manager requirements authority/public access delivered by 03C5 |
| [WS-ARCH-001-03B8](../WS-ARCH-001-03B8.md) | Bounded immutable task audit evidence with atomic project scope and exact transition references | L1 | Complete; Audit Authority/public activation delivered by 03C7; assignment hidden invalidation delivered by 03B9; 03C1 exact feature authority complete; producer/registration complete in 03C2 |
| [WS-ARCH-001-03B9](../WS-ARCH-001-03B9.md) | Hidden exact-assignment authority invalidation with committed cause, chronology and same-transaction delivery fence | L1 | Complete; 03C1 authority and 03C2 atomic publication/registration delivered |
| [WS-ARCH-001-02I-B](../WS-ARCH-001-02IB.md) | Public admission-backed Submission entry through canonical ART/TASK owners | L1 | Public ZIP preparation, ready-admission recovery, initial and exact checker-remediation POST, immutable reads and focused owner proof delivered; complete public/worker drill remains. Human-review revisions follow their own live boundary |
| [WS-ARCH-001-CP05](../WS-ARCH-001-CP05.md) | AUTH exact ContributionPolicy activation | L1 | Complete; exact policy authority delivered in PR #387 |
| [WS-ARCH-001-CP06](../WS-ARCH-001-CP06.md) | CON guide-activation/revision policy-validation port | L1 | Complete; explicit version/purpose validation and shared current resource fences |
| [WS-ARCH-001-CP07](../WS-ARCH-001-CP07.md) | PROJECTS hidden activation/binding and replacement readiness guard | L1 | Complete; AUTH-12H authority and AUTH-18 public manager activation/context delivered |
| [WS-ARCH-001-CP08](chunks/WS-ARCH-001-CP08-task-attempt-policy-lineage.md) | TASK/Assignment/Submission policy-lineage schema, public facts and minimal existing writers | L1 | Complete; schema and minimal writers delivered together; public TASK authority delivered through 03C7 |
| [WS-ARCH-001-CP09](chunks/WS-ARCH-001-CP09-legacy-economic-removal.md) | Historical economic-path cleanup coordination | L1 | Superseded by migration 0023 and the completed bounded cleanup; no pending removal or public 02I prerequisite |
| [WS-ARCH-001-03A](chunks/WS-ARCH-001-03A-project-current-generation-api.md) | PROJECT current approved unified-generation public facts | L1 | Complete; active/frozen context reuses activation custody; CP08 lineage and public TASK consumers delivered |
| [WS-ARCH-001-03B](chunks/WS-ARCH-001-03B-task-assignment-api.md) | TASK readiness, claim, assignment and locked-context public commands/facts | L1 | Complete through 03B9; public TASK authority and exposure delivered through 03C7 |
| [WS-ARCH-001-03C1](../WS-ARCH-001-03C1.md) | Exact fixed-service assignment reconciliation authority and decision-bound receipts | L1 | Complete; no producer or production handler registration |
| [WS-ARCH-001-03C2](../WS-ARCH-001-03C2.md) | Atomic originating producer publication and first handler registration | L1 | Complete; enforced prefork topology; no retained-event backfill |
| [WS-ARCH-001-03C3](../WS-ARCH-001-03C3.md) | Exact-authorized manager task create, screen and release | L1 | Complete; atomic replay and locked guide lineage; queues and remaining projections stay separate |
| [WS-ARCH-001-03C4](../WS-ARCH-001-03C4.md) | Exact-authorized public task queues | L1 | Complete; contributor, manager and operational projections with signed pagination |
| [WS-ARCH-001-03C5](../WS-ARCH-001-03C5.md) | Exact-authorized Contributor and Manager detail and requirements | L1 | Complete; canonical projections, historical policy custody and atomic read evidence |
| [WS-ARCH-001-03C6](../WS-ARCH-001-03C6.md) | Distinct exact-authorized locked-context reads | L1 | Complete; bounded Audit Authority history access delivered by 03C7 |
| [WS-ARCH-001-03C7](../WS-ARCH-001-03C7.md) | Exact-authorized bounded task history | L1 | Complete; AUTH-18 public guide activation, ARCH-03D hidden approved-guide intake, hidden exact post-submit materialization, ARCH-04B2 output custody, ARCH-04C execution, ARCH-04D1/04D2 custody/authority and ARCH-04E1A source-only facts/types delivered |
| [WS-ARCH-001-03C](chunks/WS-ARCH-001-03C-auth-task-readiness.md) | Exact task/assignment public activation and integrated readiness proof | L1 | Complete through 03C7 audit history, 03C4 queues, 03C5 detail/requirements and 03C6 locked-context reads; AUTH-18 public guide activation and ARCH-03D hidden intake are delivered; ARCH-02I-B exposes public initial/remediation intake |
| [WS-ARCH-001-04A](../WS-ARCH-001-04A.md) | CHECKER post-submit contract and registered evaluator conformance | L1 | Complete canonical catalogue, phase facts and structural conformance; consumed by delivered POL-04B and POL-07B |
| [WS-ARCH-001-04B](../WS-ARCH-001-04B.md) | ART exact verified Submission materialization | L1 | Complete hidden verified input with async scoped reads; exact input authority delivered by 04D2 |
| [WS-ARCH-001-04B2](../WS-ARCH-001-04B2.md) | ART checker-output custody and verified binding | L1 | Complete hidden typed store, byte-free recovery and flush-only binding; production authority deny-only |
| [WS-ARCH-001-04C](chunks/WS-ARCH-001-04C-checker-current-result.md) | CHECKER hidden durable current output and supersession behavior | L1 | Complete hidden request/lease/result custody with exact empty-output support and atomic completion; exact service authority delivered by 04D2 |
| [WS-ARCH-001-04D1](../WS-ARCH-001-04D1.md) | Canonical terminal ART material custody | L1 | Complete; valid retained history preserved; invalid upgrades refused |
| [WS-ARCH-001-04D2](../WS-ARCH-001-04D2.md) | AUTH exact fixed-service post-submit activation (replaces XINT-06B) | L1 | Complete: exact input, execute and finalize authority; output write/bind remains unavailable |
| [WS-ARCH-001-04E1A](../WS-ARCH-001-04E1A.md) | Route-neutral immutable source schema and shared accepted-effects types | L1 | Complete; REV-04C uses a bounded exact-source verifier, with no general routing publication writer/reader, routing authority or current pointer; its hidden effects participant does not make false routing available |
| [WS-ARCH-001-04E](chunks/WS-ARCH-001-04E-canonical-allow-review.md) | TASK current routing: true to canonical `allow_review`, false/pass to shared acceptance | L1 | 04E1A/04D2/OUTBOX-02, reservation, AUTH preparation, exact source, verified ZIP metadata, checked packet custody, bounded content, atomic Submission/dispatch, request delivery, authorized outcomes and completion delivery are delivered. PILOT-04 registers selected production delivery. ARCH-04E3-B admits supported false guides and corrects REV's manifest; false/pass still needs LIVE REV at execution. True has no CON/REV prerequisite. Complete public/worker drill remains |
| [WS-ARCH-001-03D](../WS-ARCH-001-03D.md) | Exact activated historical guide through hidden durable intake; obsolete lookup removed | L1 | Complete; hidden exact post-submit materialization, ARCH-04B2 output custody, ARCH-04C execution, ARCH-04D1/04D2 custody/authority and ARCH-04E1A source-only facts/types delivered; ARCH-02I-B public initial/remediation entry is delivered |
| [WS-ARCH-001-04F1](../WS-ARCH-001-04F1.md) | Verified completed failure evidence through the existing CHECKERS port | L1 | Complete; no TASK remediation mutation, replacement intake or recovery authority |
| [WS-ARCH-001-04F2](../WS-ARCH-001-04F2.md) | Exact current checker-remediation handoff through existing TASK/AUTH outcome owners | L1 | Hidden policy-independent `needs_revision` transition with exact manifest/receipt custody and no REV/CON effect; this record supplied no replacement intake, recovery, production registration or public API; 04F3/04F4 and PILOT-04 later supplied those hidden paths |
| [WS-ARCH-001-04F3](../WS-ARCH-001-04F3.md) | Exact-cause checker-remediation replacement through existing ART/TASK/AUTH owners | L1 | Hidden changed-ZIP intake and atomic successor Submission/request under both policy modes; uncaused revision runtime removed, retained unprovable rows refuse migration; no public activation in that record |
| [WS-ARCH-001-04F4](../WS-ARCH-001-04F4.md) | Hidden Operator retry of exact terminal infrastructure failure | L1 | Complete: reason-bound system-Operator AUTH, immutable source and successor receipts, shared request event and historical replay; no public route from this record; PILOT-04 later registers selected production delivery |
| [WS-ARCH-001-04F](chunks/WS-ARCH-001-04F-checker-remediation.md) | Contributor-correctable failures and exact-cause replacement Submission | L1 | 04F1–04F4 are delivered. A future setup-fault hold needs a supported result classifier and must retain locked rules without contributor penalty; it does not block the first-layer connections |

CP09 coordination is superseded by the completed physical cleanup. 04E and 04F
remain coordination parents, not permission for multi-owner PRs.
04F is outside the `allow_review` critical path; 04E's children
deliver that boundary. Each remaining implementation
expands its current child contract into one existing-initiative change record
with exact paths, schema head, proof commands and impact-routed reviewers.
That expansion belongs to its implementation PR, not an extra approval loop.
No new product implementation starts automatically on merge of this plan.
