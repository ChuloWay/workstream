# Product Brief

## Product Name

Workstream

## One-Sentence Description

Workstream defines a shared protocol for governed work and provides the
software that implements it for humans, AI agents, or both. It turns
project-defined tasks, immutable submissions, policy-governed checks, and
policy-governed acceptance into trusted `ContributionRecord` facts that applications,
organizations, and economic systems can consume.

The protocol defines shared rules; the implementation enforces them. A
standalone versioned specification and conformance tests remain to be
formalized from the validated lifecycle. See
[Protocol And Implementation](protocol-and-implementation.md).

## Durable Outcome

Workstream establishes an attributable statement about governed work:

> This authorized actor completed this task under this locked version of the
> project rules, submitted this exact artifact, passed these checks, received
> the authorized decision required by the project policy, and achieved this recorded outcome.

On the human-review branch, every valid Review creates the reviewer's immutable `completed_review`
`ContributionRecord`. An `accept` decision additionally creates
`FinalAcceptance` and the submitter's immutable `accepted_submission`
`ContributionRecord`. Compensation, points, reputation, reporting, datasets,
model training, and other systems consume these records; they cannot create or
rewrite them.

## Problem

High-quality task work fails for operational reasons more often than technical reasons:

- rules are scattered across chats, markdown, and reviewer memory
- submissions reach reviewers before basic checks pass
- revision feedback is not replayed carefully
- compensation fulfillment status is tracked manually and inconsistently
- reviewers disagree because the project guide is not encoded into the workflow
- operators cannot see the true state of the pipeline

This creates wasted effort, delayed payments, repeated mistakes, and low trust.

## Insight

Across serious task projects, the surface language changes but the lifecycle is stable:

```text
Guide -> Task -> Pre-Submission Intake -> Submission -> Post-Submission Evaluation
-> Policy-Governed Decision (Human Review When Required) -> Revision/Acceptance
-> Contribution -> Conditional Compensation Award -> Fulfillment
```

Workstream makes that lifecycle explicit and configurable.

Pre-submission intake assesses package fitness before a Submission exists.
Post-submission evaluation assesses the immutable work against locked project
requirements and produces review-eligibility evidence. Evaluation can use
deterministic rules or supported model-based checkers; the stage does not
promise deterministic judgments. Neither stage independently authorizes
acceptance. The versioned `human_review_required: true`
in the existing locked ReviewPolicy may be set false for authorized automated
acceptance, without reviewer contribution. REV-04C supplies the shared
FinalAcceptance/TASK/CON transaction participant, and ARCH-04E2-B supplies the
complete authorized outcome over it. Selected request and completion handlers are
registered in production composition. A complete supported false guide can
activate when its approved inventory contains no `human_review` disposition; new
false/pass effects require an Operator-authorized live REV generation. ARCH-02I-B exposes public ZIP preparation and admission-backed
initial/checker-remediation Submission creation. The bounded local public API
and Celery service drill starts from public guide inputs with recorded inference.
See the [checker framework](architecture_checker_framework.md) and
[current capability ledger](roadmap_status.md) for supported boundaries.

The system is source-agnostic without becoming source-adapter-first. A task
created manually, imported from Markdown or CSV, or later received from an
external origin normalizes into the same Workstream task contract. The source
retains its own experience and operating model; Workstream governs task,
artifact, check, review, and contribution truth underneath.

## Target Users

### Primary User: Contributor

The person who claims assigned work, packages submissions, submits evidence,
monitors their contribution status, and resolves revisions under an
exact-project Submitter grant.

Needs:

- know what to do next
- avoid missing project rules
- package submissions correctly
- track task decisions, contributions, compensation awards, and fulfillment

### Secondary User: Reviewer

The person who checks whether work satisfies the project guide and acceptance criteria.

Needs:

- see only review-ready submissions
- apply a consistent checklist
- issue actionable revision feedback
- avoid reviewing broken packages

### Project Manager And Operator

The covered Project Manager configures project rules and tasks. The Operator
inspects runtime health and performs registered recovery. Actor/grant,
finance, and audit duties remain separate authorities.

Needs:

- create covered project templates
- configure project statuses and checkers
- inspect permission-appropriate review evidence
- track throughput and compensation-award exposure

## MVP Boundary

The first version includes:

- project guide records
- task queue
- task detail
- task contract screening
- submission packet records
- checker framework
- human review workflow
- revision replay
- contribution records
- compensation awards, fulfillment receipts, and status projections
- contribution evidence for a future reputation projection
- status dashboard

## First Operator Value

The first version must make a small operator team better immediately:

- fewer missed project rules before submission
- fewer avoidable needs-revision cycles
- faster review readiness because broken packets are blocked early
- clearer reviewer feedback because findings are structured
- cleaner compensation tracking because contribution, award, and fulfillment
  are separate states
- less dependency on scattered chat memory

If the product does not reduce repeat mistakes and status confusion in the first pilot, it is not yet working.

## v0.1 Task Intake

The only v0.1 intake paths are:

- manual task creation in the app
- import from a controlled markdown or CSV template

External source adapters, origin onboarding, webhook drop notifications,
automated routing, owner-agent execution workspace, and on-chain settlement are
later work. This keeps v0.1 focused on proving the internal lifecycle instead
of integrating every possible source or settlement rail.

The first version excludes:

- built-in AI workspace
- on-chain settlement
- public marketplace
- external client portal
- fully autonomous task routing
- agent identity protocols
- complex dispute arbitration

## Product Promise

Workstream makes governed work independently verifiable and reusable. It tells
source applications and downstream systems what work occurred, which exact
artifact and rules governed it, who was authorized to submit and review it, and
which immutable contribution facts resulted.

Flow Identity is the current v0.1 authentication provider. It verifies external
identity; local Workstream grants and lifecycle guards determine authority.
That implementation choice does not make Workstream Flow-specific.

## Future Research Hypothesis: Accountable Orchestration

After v0.1 is proven, Workstream can test one bounded hypothesis: an external,
provider-neutral orchestration adapter can propose task dependencies and
contributor matches for complex work without creating a second lifecycle or
weakening Workstream's contribution-truth boundary.

The hypothesis reuses the existing lifecycle:

- a source application submits one authorized, bounded outcome and optional
  project-specific budget or compensation constraints;
- an orchestration adapter proposes task inputs, explicit dependencies, and an
  evidence-backed contributor shortlist;
- the existing Task screening and Authorization services validate every task,
  assignment, authority, conflict, policy, and release transition;
- Garden or another external execution host coordinates people, agents, tools,
  and deliverable integration;
- Harnessy-compatible capability/runtime providers supply executable
  capability and readiness evidence without choosing business priority;
- Workstream binds canonical tasks, assignments, submissions, artifacts,
  checks, Reviews, revisions, FinalAcceptance, and contribution facts;
- Jarvis-compatible export may carry portable policy, consent, session, and
  evidence references without becoming a second Workstream authority;
- separately approved downstream projections may interpret contribution and
  delayed-outcome evidence without rewriting canonical facts.

Workstream does not validate that money has been collected, custody funds, infer
payment availability, execute tools or agents, integrate deliverables, or own a
universal capability registry. Where a source contract requires funding, the
source provides a typed budget or funding assertion and its authority; project
ContributionPolicyVersion and CompensationAward rules remain the source of
conditional compensation behavior inside Workstream.

Every valid human Review creates the reviewer's `completed_review`
`ContributionRecord`. FinalAcceptance comes only from an `accept` Review or,
where the locked ReviewPolicy sets `human_review_required: false`, an
authorized automated acceptance decision. Only FinalAcceptance can source the
submitter's `accepted_submission` `ContributionRecord`. Orchestration output
never creates either fact.

### Smallest experiment

The first commercial orchestration experiment is a configuration of the
existing lifecycle for one enterprise software or quality-assurance issue. A
human supplies the issue and acceptance rubric; an adapter suggests a plan and
candidate; a Project Manager or other exact future grant approves Workstream
task and assignment inputs; one external host performs the work; deterministic
checks produce a review-ready packet; and the canonical Review lifecycle makes
the decision.

This is distinct from the v0.1 internal proof surface below. The internal pilot
proves lifecycle truth across familiar task programs; the later commercial
experiment asks whether a planning suggestion reduces coordination effort.

The experiment measures reviewed work outcomes completed per hour of human
coordination. A reviewed work outcome begins at authorized task release and
ends at one canonical Review decision; human coordination includes documented
planning, assignment, exception handling, integration coordination, and review
time. Quality, unauthorized actions, revision rate, evidence completeness,
appeals, opportunity distribution, effective earnings, privacy, concentration,
and full delivery economics are hard gates.

### Roles and authority

| Future responsibility | Authority boundary |
| --- | --- |
| Requester/source | Defines the bounded outcome and supplies optional commercial constraints; cannot bypass Workstream screening or authorization |
| Orchestration adviser | Proposes task/dependency inputs and contributor candidates; has no assignment, acceptance, payment, reputation, or appeal authority |
| Project Manager | Uses explicit project-scoped grants to create, screen, and release tasks under existing services; does not inherit authority from an AI recommendation |
| Contributor/submitter | Accepts or declines an offered assignment and submits governed work; declining has no reputation penalty |
| Execution host/integrator | Coordinates tools, agents, people, and deliverable integration outside Workstream; submits artifacts and integration evidence into the governed lifecycle |
| Reviewer | Uses the canonical Review lease and decision contract; remains independent from submitter and disallowed conflicts |
| Operator/Audit | Observes and recovers registered runtime behavior under existing permissions; does not become a general work allocator |
| Downstream projection owner | Interprets facts under a separately versioned policy; cannot rewrite Workstream records or apply retroactive economic or reputation consequences |

### Evidence and human control

Future contributor matching first applies task-specific eligibility and conflict
rules, then returns an explainable shortlist from verified comparable outcomes,
recency, uncertainty, authorized tools and data, availability, and concentration.
Capability, authority, reputation, availability, price, and conflicts remain
separate. No global score determines human or agent worth.

Protected attributes, where lawfully collected for fairness auditing, remain
access-separated from production matching features. Proxy and intersectional
audits precede any expansion of automated influence. Participants may inspect
and correct relevant evidence, decline a suggestion without penalty, and seek
independent review of a consequential allocation.

Adjudication for any paid pilot must be outside the original assignment,
Review, and account-management chain. Its policy defines a response deadline,
evidence access, a default remedy for missed deadlines, no delay to undisputed
or vested compensation, and correction propagation into downstream projections
or models. Filing an appeal cannot reduce opportunity access or reputation.

Runtime reputation projection remains unavailable. No existing or future
ContributionRecord may receive retroactive reputation or economic consequences
without a separately approved, prospective, versioned projection policy.

### Maturity sequence

Future orchestration remains explicitly outside v0.1:

1. prove governed contribution facts;
2. record task requirements, capability evidence, manual routing, and outcomes;
3. evaluate single-task planning and matching proposals in shadow mode;
4. let authorized humans approve proposed task/dependency inputs and candidates;
5. automate only low-risk, reproducibly verifiable routing under fixed caps;
6. consider persistent dependency graphs, adaptive matching, or distributed
   execution only when repeated paid work proves they are necessary.

Before stages 3–5 advance, each vertical needs a versioned control policy with
thresholds and owners for opportunity and earnings disparity, buyer/reviewer/
principal concentration, newcomer access, reassignment and appeal/overturn
rates, reviewer rubber-stamping, payment latency, privacy and authority
incidents, rollback response, and participant-record repair.

## v0.1 Internal Proof Surface

The first operational pilot serves the existing Flow Research community through
a bounded selection of useful internal work and suitable partner-funded
projects. Engineering, research, documentation, learning materials, and
operations are eligible categories when the task has a named beneficiary,
clear acceptance criteria, and an approved funding basis. Start with a small
batch that fits existing project guides and supported intake; mixed priorities
do not require implementing every possible task category.

Before offering paid work, identify the commissioner, contracting entity,
funder, delivery operator, compensation obligor, payment owner, independent
reviewer, and artifact steward. Verify available funds and restrictions, scope,
contribution and reuse terms, capacity, and the baseline workflow. The first
pilot pays for agreed creation, review, maintenance, or adaptation. Points,
royalties, tokens, and equity are not prerequisites or implied entitlements.

Existing tools and manual coordination can establish usefulness and earnings
while engineering proceeds. Such delivery is not evidence that unfinished
Workstream behavior is implemented. Product proof still requires the secured
v0.1 lifecycle and its release gates. This strategy does not expand intake beyond
manual creation and controlled Markdown/CSV import or authorize new adapters,
agent workspaces, autonomous routing, or settlement mechanisms.

Contributor agreements complement applicable employment, contractor, stipend,
and project terms. Agreements determine ownership, permissions, and payment
obligations. A community label is not an authority grant; a customer sign-off
is not automatically canonical Review or FinalAcceptance.

## Success Metrics

### Operational usefulness and earnings

Agree targets against the existing-workflow baseline before evaluation. Track:

- whether the intended beneficiary actually uses the result;
- turnaround, human coordination, review effort, rework, and post-acceptance defects;
- contributor effective earnings and agreed payment timeliness;
- recurring delivery, review, stewardship, and support costs, with development
  expenditure recorded separately;
- available funds for the next cycle, distinguishing internal subsidy, earned
  revenue, and renewed sponsorship;
- repeat funded need and reuse benefit after adaptation and maintenance costs.

Acceptance does not prove usefulness or payment. Reviewers earn contribution
records for every valid Review, including needs_revision and reject; submitters
receive accepted_submission records only upon acceptance. Awards and fulfillment
follow their own approved terms. Do not require artificial revisions in paid
work. Pause or narrow new commitments when funding is insufficient while
honoring existing obligations. External demand and independent interoperability
remain separate later tests.

### Engineering coverage and lifecycle invariants

The existing pilot counts below are controlled coverage targets, not sufficient
proof of community usefulness or a requirement to manufacture paid rework:

- 3 project templates configured
- 20 tasks entered
- 10 submissions created
- 5 review decisions recorded across accept, needs_revision, and reject
- 3 needs-revision loops completed in controlled validation
- 100 percent of submissions have checker results
- 100 percent of valid human reviews have reviewer contribution records
- 100 percent of accepted tasks have evidence and submitter contribution records
- 100 percent of payable contributions have immutable CompensationAwards and
  fulfillment projections
- status dashboard reconciles with manual records
