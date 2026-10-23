# Project-image model calls with bounded spend and durable recovery

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Give policy-bound external POST images controlled model access, with project spend custody, immutable evidence and recovery that cannot silently repeat a paid call.

## Intent

The user explicitly resumed the minimum PILOT-05 runtime needed by the real
Terminal Systems project. Six proposed POST specifications require model review.
The image owns the rubric, prompt and interpretation; Workstream owns authority,
spend and lifecycle. No project-specific rule belongs in the shared Rust runner.

## Current behavior

`selected_post_submit_execution.py` executes locked images over an ART callback.
The Rust service exposes only read-only verified submission material in a
networkless container. There is no model credential, project spend ledger or
provider-call recovery. `execution_coordination.py` creates a successor checker
generation on Operator retry; using that generation as a paid-call key would
permit duplicate charges. ART already defines generated checker output custody
ports, but their production reservation path needs inspection before reuse.

## Bounded change

### Allowed

- CHECKERS model-call contracts, models, repository/service operations and
  selected POST integration; existing AUTH and TASK ports for fresh execution
  authority/currentness and Operator provisioning.
- Existing ART generated checker-output custody to retain bounded private
  request/response evidence, with matching authority and read concealment.
- Typed provider capability under `backend/app/interfaces/`, concrete adapter
  and explicit ADR-0014 composition; fixed settings outside images.
- One linear Alembic continuation with preflight, intermediate upgrade and
  retained-data proof; affected schema snapshots, permission catalogues and MCP
  contracts updated together where changed.
- Shared Rust runner and SDK: invocation-local socket transport only, preserving
  network denial, read-only submission material, cleanup and output budgets.
- Focused PostgreSQL/MinIO, transport, provider and public lifecycle tests;
  affected CI allocation, owner specifications, runbook and roadmap.

### Not allowed

No provider credential or global proxy socket in project images; no contributor
billing, setup-agent billing, alternate checker implementation kind, project
rules in Rust, unrestricted provider/model selection, automatic paid retries
after ambiguous delivery, task/revision spending on infrastructure failures,
or live model spend before the user supplies the rehearsal cap. No merge or
hosted deployment is authorized. Execution trials and prior-revision material
remain separately necessary before the entire project can activate.

## Design and decisions

An immutable project model profile binds the exact registry entry and digest, provider/API/model
snapshot, generation parameters, token/deadline ceilings, one allowed call slot
and immutable integer pricing. Reserve the complete selector triple
`model_profile_id`, `model_profile_version`, `model_profile_digest` in the flat
PM-approved image configuration. A typed exact profile reader checks project,
registry and profile identity during policy compilation, readiness/activation and
runtime. Partial selectors fail; the existing POST policy hash retains this
custody without a new checker kind or TASK lineage column.
An Operator sets a finite project budget; profiles do not
allow images to change that budget or choose a different model. Monetary amounts
use integer USD nanodollars with explicit immutable pricing provenance.

Trusted execution creates a callback-scoped model grant bound to the current
checker lease, exact Submission, requirement, registry/configuration and profile.
Rust exposes only an invocation-local socket. A bounded image request supplies
prompt material; the trusted proxy supplies identity and fixed provider settings.
The global endpoint and opaque grant never enter image input or logs. The backend
verifies a completed call receipt before accepting a model-enabled image verdict.

The paid slot identity is `(project, assignment, submission, submission_version,
requirement, registry_digest, configuration_hash, profile_version, slot_index)`.
Neither worker lease nor checker retry generation belongs in this key. The first
provider request hash is immutable: a later changed prompt conflicts. Successor
checker runs reuse the same cached or recoverable call. An authorized child
attempt is possible only after a proven no-effect outcome, with a new atomic
reservation; the image cannot select its attempt number.

Create or attach the stable slot and verify its request evidence first. Reserve
the worst-case allowed input/output charge just before first dispatch, after
fresh authority/currentness, committing reservation and dispatch intent together
before provider I/O. Preserve
AUTH/TASK-before-CHECKERS custody; budget locks must never lead back to TASK.
Concurrent callers serialize the same slot and project budget. Persist dispatch
intent before create, persist provider identity immediately when returned, and
settle measured usage exactly once. Lost create responses remain uncertain and
retain their reservation; absence of a provider ID is not proof of no effect.
Known provider IDs may be retrieved without another create. Cached completion
is immutable and survives process, lease and Operator retries.

Keep the existing CheckerRun lifecycle. A run may finish `infrastructure_failed`
when its model response is unavailable, while the independent paid call remains
`dispatching` or `uncertain`. Operator retry attaches the same slot; it may only
recover that effect, never create again because a generation changed. A late
response may complete the original call after its run terminalized, allowing the
next current run to consume its cached evidence. Only a proven no-effect child
attempt receives fresh dispatch authority.

Extend the existing ART generated-output custody with a paid-call-stable
reservation for two bounded canonical JSON slots: request before dispatch and
response/usage on known completion. Do not write transcript bytes to PostgreSQL,
Redis or outbox payloads. Ledger rows contain exact content identities and hashes.
Once dispatch intent is committed, the call-effect owner retains narrowly scoped
authority to finish/recover those exact evidence slots independently of the
original worker lease. It cannot start a new effect under that authority. Fresh
current-run authority links verified call evidence to each consuming run; stale
images cannot spend or gain read access to another invocation. This extends the
same ART put/verify/bind lifecycle, not a parallel artifact store.

Explicit service actions separate `checker.model_call.dispatch`,
`checker.model_call.recover` and `checker.model_call.complete` under existing
AUTH grants. Dispatch takes exact current execution facts; recover can only
inspect the existing effect; complete takes immutable call-attempt/effect facts
and may retain late evidence. Operator project budget/profile provisioning and
covered-PM cost reads receive their own exact resource/action contracts.

Implementation order: provider-free profile/slot/budget contracts and PostgreSQL
proof; AUTH and profile approval/readiness; ART evidence custody with MinIO crash
proof; typed fake provider/proxy; invocation-local Rust socket; selected POST
finalization/retry integration; offline project proof; capped live rehearsal.

Provider output and usage must satisfy the locked bounds. Budget exhaustion,
provider outage, invalid provider response and uncertain delivery are
infrastructure outcomes, never contributor-fixable failures. Private evidence
does not appear in contributor findings or exported provider coordinates.

## Acceptance criteria

- One digest-pinned image uses its invocation socket to obtain a bounded model
  response while provider credentials and the global endpoint remain unavailable.
- Two concurrent distinct calls cannot exceed the project budget; duplicate
  requests yield one provider create and one settlement.
- Provider acceptance followed by response loss, process/lease restart and
  Operator checker retry cannot create a second paid call. A generation-keyed
  mutant must fail this regression.
- A changed prompt, substituted project/Submission/profile, stale lease, expired
  grant, PRE invocation or unentitled image cannot spend.
- Request/response evidence, exact pricing and usage survive restart and replay;
  raw content remains under existing private ART custody.
- Budget/provider failure produces infrastructure recovery and no revision
  consumption. The existing non-model image path retains its behavior.
- Real PostgreSQL proves locking, rollback, settlement and linear upgrades;
  MinIO proves evidence custody. Offline provider tests precede capped live calls.

## Risk and review routing

Risk class: L0. Required architecture/plan, authorization/security, database and
QA review, plus CI/docs for affected changes. Human focus: spend authorization,
ambiguous provider effects, immutable policy identity, owner boundaries and
honest separation of local proof from deployed operation.

## Evidence

Initial source inspection and architecture review identified the stable paid
slot and the need to preserve image ownership. This is a design record; no
runtime, budget, provider call or live project completion is established yet.

Plan review found that existing ART output slots are empty and run/lease-bound;
the stable call evidence reservation above is required. It also required exact
profile selection/readiness checks rather than merely hashing opaque config.
The proposed new CheckerRun state was rejected as unnecessary: call-effect
recovery belongs to the durable slot while existing infrastructure outcomes stay
unchanged.

## Reconciliation

The earlier PILOT-05 hold is lifted only for this required runtime scope. The
pending rehearsal spend cap blocks live paid POST calls, not implementation or
offline tests. Review current main and open migrations before allocating a
revision number. Required execution trials and authenticated prior-work context
must still be supplied before final guide activation.
