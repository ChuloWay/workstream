# ARCH-04E1B-B2 — Exact routing source preparation

- Initiative: `WS-ARCH-001`
- Durable disposition: `Complete`
- Intended merge outcome: hidden TASK source preparation joins the existing reserved routing identity to exact current CHECKERS material and historical PROJECTS policy, without publishing a source or applying effects.

## Intent and current behavior

After 04E1B-B1, reservation and current reads retain TASK-before-CHECKERS custody.
`TaskRoutingRequests.stage` reserves a future manifest identity but receives only
an integer from `require_current_completion`. TASK cannot assemble its source
without reaching into CHECKERS/PROJECTS private tables. The existing PROJECTS
locked-policy port already resolves historical policy bodies and activation
custody. Reuse it; extend the existing CHECKERS completion projection.

This is the next bounded part of 04E1B-B, not completion of its handlers.

## Bounded change

Allowed files: CHECKERS `api/execution.py`, `execution_coordination.py`;
TASK `api/post_submit_routing.py`, `api/__init__.py`,
`post_submit_routing/requests.py`, `post_submit_routing/source.py`;
`adapters/tasks/__init__.py`; directly affected TASK/CHECKERS contract and
PostgreSQL tests, their existing fixture helpers, lane/ownership registrations;
this record, current ARCH overview/plan/chunk map/parent 04E contract, INDEX,
README, roadmap and canonical checker/TASK specifications where claims change.

Prohibited: migrations, AUTH action activation or synthetic allows, new source
storage or INSERT, routing pointers/status changes, REV/CON effects, outbox
registration/publication, live workers/routes, guide activation changes,
compatibility aliases, retained-data deletion or weakened tests/checks.

## Design

1. Replace the version-only completion return with closed detached verified
   completion facts; update all affected callers. CHECKERS retains the same
   currentness/phase-receipt/material checks and root transaction requirement.
2. TASK prepares semantic source facts without a fabricated creation timestamp.
   The existing persisted manifest facts retain their mandatory database time
   and share the same semantic fields. This distinguishes a proposal from a
   stored record, not parallel implementations.
3. In the caller root transaction, lock exact TASK/Assignment/Submission scope,
   resolve the historical PROJECTS context before acquiring CHECKERS custody,
   reserve/recover the existing route identity and construct the exact proposal.
   Compare complete activation and Submission lineage, including review boolean,
   contribution-policy identity and material facts. No current project policy
   can replace locked policy. Return detached facts, never ORM rows.
4. Exact replay reuses the existing reservation. Caller rollback removes newly
   staged requests; preparation never commits or creates another owner effect.

The future false handler must acquire the joint REV lifecycle fence before
TASK, then revalidate the policy under TASK custody. It must not call shared
acceptance for the first time after holding TASK/CHECKERS. True admission stays
independent of the shared acceptance fence. Full handler/receipt/publication
composition remains separately required by 04E1B-B/04E2-B/04E3.

## Acceptance criteria and proof

- Real PostgreSQL completed-source fixture returns the exact reserved identity,
  Submission/predecessor/contributor, locked policies, checker references/phase
  receipts and canonical ART material, with no private storage coordinates.
- Same request replays identically; root rollback removes new reservations.
- Foreign valid source substitutions, stale generation and changed lineage deny;
  no source, status, REV/CON, audit or outbox effects are introduced.
- Independent sessions prove preparation retains TASK custody and a successor
  that wins first makes the old completion unavailable.
- Managed/raw savepoints remain rejected through the existing root guard.
- False policy remains pure value-contract proof only: guide activation and
  genuine false runtime authority remain unavailable. No fake allow or guide
  activation is evidence for this chunk. The current hidden intake leaves TASK
  in_progress; focused tests explicitly seed the future dispatch-owned
  evaluation_pending precondition and separately prove earlier-state denial.
  The ART fixture also seeds assignments directly; these tests explicitly set
  its missing accepted_at claim precondition after proving that absence denies.
  They do not claim authorized claim or initial dispatch proof.

## Risk and review routing

Risk: L1. Required focused architecture/reuse, security, QA/test-delta,
CI integrity and documentation review. Human focus: historical policy versus
current policy; currentness lock lifetime; proposal versus persisted source;
no premature runtime/authority claim. The plan review identified absent REV
admission and initial dispatch composition plus the false-handler fence order;
this bounded preparation does not fabricate those dependencies.

## Evidence and reconciliation

Run affected pure contracts, real PostgreSQL source preparation/currentness,
module boundaries, Ruff, lane inventory, stale wording, links and Commitrail;
then full hosted CI and exact-head internal review. The four new PostgreSQL preparation cases passed, including exact full-value
comparison, replay/rollback, historical guide preservation, mixed valid source
rejection and retained locks followed by stale-generation rejection. Expanded
root-transaction and cross-project probes and full hosted evidence are tracked
in the PR. Main reconciled at `31ac857b`; #476 supplies lock repair.
No local spreadsheet export has yet been assumed present.

Next usable boundary: remaining hidden request/completion handlers, mandatory
AUTH receipt/database/audit/outbox closure, then live composition and remediation.


The final ownership inventory admits only the new source module and rejects
an adjacent activation module. No migration or database schema changed. Local
spreadsheet exports are absent. Plan review retained evaluation_pending and
accepted-assignment guards; older ART-only fixture setup is explicitly arranged
in these new mechanical tests rather than relaxing the production requirements.
