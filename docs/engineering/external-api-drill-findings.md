# External API drill: repair handoff

## Purpose and sequence

This is the human-requested handoff of observed defects, not a finished API
catalogue or an MCP readiness report. Another agent should repair these issues
together in a bounded change, with coordination around the product builder's
owned files. Then the orchestrator reruns the real HTTP drill on the merged
repair and completes the remaining field checks. Only then is the verified
endpoint-and-field list handed to the MCP adapter agent.

Human-confirmed v0.1 project roles are **submitter** and **reviewer**.
Adjudication is deferred. Do not implement adjudicator functionality, widen an
audit allowlist to support it, or introduce a compatibility path to make the
old advertised role pass.

## Evidence boundary

- Product source: `b4b3d1d95d302011839f6f9dff3e2cb7c06c2124` (merged PR 390).
- Clean drill target `430c14d7547990c81eb6fe975b1757135d6aaf7f` reproduced the
  three oversized-field failures and the adjudicator grant failure.
- The subsequent `319f4ece509d645f7536b98da653921ac50a93cd` drill adds null-content,
  same-key recovery and forbidden-side-effect checks. Its raw evidence belongs
  to that exact target, not to later edits of this handoff or the drill.
  That run completed 226 cases: 109 successful calls, 112 expected denials and
  the five failures below. The final exit was nonzero. Its field audit remains
  incomplete; those counts are cases, not fully verified endpoints.
- Real loopback Uvicorn/FastAPI, normal Flow token verification with a fresh
  test-only issuer, and a fresh migrated PostgreSQL 17 database were used.
  The supported initial Access Administrator bootstrap CLI was setup only;
  subsequent product mutations used HTTP.
- No direct product-state inserts, disabled triggers, authentication overrides,
  old API-drill imports, fake model execution or production credentials.
- Artifact storage and automatic setup execution were disabled. Storage/model
  dependent flows and unavailable public activation are not positive evidence.

Local raw run evidence is under `/tmp/workstream-api-fields.TXbSNQ/`:
`run2.json`, `run3.json`, `run4.json`, matching `db*.json`, and the private
PostgreSQL log. These are temporary local artifacts, not durable shared links;
the reproductions and repair criteria below must remain sufficient without them.
Do not commit credentials, raw HTTP bodies, database connection strings or logs.

## Confirmed repair items

### API-DRILL-001: oversized project name becomes a service failure

- Route: `POST /api/v1/projects`, authorized system Project Manager, valid
  `Idempotency-Key`.
- Reproduce: `name` is 201 ASCII characters; `slug` is a fresh ordinary value.
- Observed: HTTP **503**, `error.code=service_unavailable`.
- Positive control: 200-character name succeeds and reads back unchanged.
- Cause: `ProjectCreate.name` is an unrestricted string, while `Project.name`
  is `varchar(200)`. PostgreSQL reported the exact length violation.
- Required repair: align public validation/OpenAPI with the existing 200-character
  persistence limit. Reject oversize input with 422 before attempting the write;
  retain legitimate Unicode and exact-limit behavior.
- Retest: `project_maximum_lengths`, `project_maximum_readback`, `overflow_name`,
  `overflow_name_retry_after_rollback`; add focused product regression coverage.

### API-DRILL-002: oversized project slug becomes a service failure

- Route and authority: same as API-DRILL-001.
- Reproduce: fresh `slug` is 121 ASCII characters; `name` is an ordinary value.
- Observed: HTTP **503**, `error.code=service_unavailable`.
- Positive control: 120-character slug succeeds and reads back unchanged.
- Cause: unrestricted `ProjectCreate.slug` versus `Project.slug varchar(120)`.
- Required repair: enforce the existing 120-character bound at the public
  boundary. Preserve duplicate-slug 409 behavior and idempotent replay/conflict.
- Retest: `overflow_slug`, `overflow_slug_retry_after_rollback`,
  `project_maximum_lengths`, `project_duplicate_slug`, `replay_project`,
  `conflicting_project_replay`.

### API-DRILL-003: oversized guide version becomes a service failure

- Route: `POST /api/v1/projects/{project_id}/guides`, authorized Project Manager,
  existing draft project, fresh UUID idempotency key.
- Reproduce: `version` is 51 ASCII characters and `content_markdown` is ordinary
  non-null guide text.
- Observed: HTTP **503**, `error.code=service_unavailable`.
- Positive control: a 50-character version succeeds.
- Cause: unrestricted `ProjectGuideCreate.version` versus
  `ProjectGuide.version varchar(50)`.
- Required repair: public/OpenAPI maximum of 50 characters; oversize input
  rejects with 422. Preserve version uniqueness, authorization and replay.
- Retest: `guide_maximum_version`, `overflow_version`,
  `overflow_version_retry_after_rollback`, `guide_current_state_after_overflow`.

### API-DRILL-004: nullable guide edit contradicts stored content

- Route: `PATCH /api/v1/projects/{project_id}/guides/{guide_id}`, authorized
  manager, existing draft guide with no source snapshot, fresh idempotency key.
- Reproduce: `{"content_markdown": null}`.
- The update schema admits null and the service assigns it to the stored guide;
  PostgreSQL then reports a `content_markdown` NOT NULL violation.
- Observed: HTTP **503**, `error.code=service_unavailable`. A fresh authorized
  current-state check confirmed that the original content remained intact.
- Required repair: distinguish omission from explicit null. Omitted content
  preserves existing content; explicit null rejects with 422. Do not make the
  stored guide nullable or silently reinterpret null as a successful edit.
  Preserve independently nullable `change_summary`.
- Retest: `guide_null_content`, `guide_null_content_unchanged`, valid content
  replacement, omission, nullable summary, unauthorized edit and unchanged
  current-state checks. Verify a rejected edit does not advance guide/replay state.

### API-DRILL-005: deferred adjudicator role is exposed as an input option

- Route: `POST /api/v1/projects/{project_id}/role-grants`.
- Reproduce: authorized manager, active human target, `role="adjudicator"`,
  valid qualification evidence and reason, fresh UUID idempotency key. The same
  request shape succeeds for submitter and reviewer.
- Observed: HTTP **503**, `error.code=service_unavailable`; PostgreSQL rejects
  the grant's audit event under `ck_audit_events_fact_bounds`.
- Current mismatch: the public `ProjectRole` enum, grant/qualification database
  checks and some current documentation admit adjudicator. The baseline's
  `authority_facts_are_safe` role allowlist omits it, although the event-specific
  project-grant rule includes it.
- Human resolution: this is **an unsupported-role exposure to remove**, not a
  request to make adjudicator issuance succeed. The public contract should offer
  only submitter/reviewer; adjudicator input should reject with 422, create no
  grant and confer no access.
- Reconcile affected request/response/filter schemas, authoritative role
  vocabulary, persistence and audit contracts, tests and current documentation
  consistently. Inspect actual dependencies before removing symbols; do not
  mechanically delete unrelated future-adjudication discussion or weaken audit
  checks. Follow the repository's current fresh-baseline/migration procedure.
- Retest: `unsupported_adjudicator_rejected`,
  `unsupported_adjudicator_no_active_grant`, `unsupported_adjudicator_no_access`,
  and all submitter/reviewer issuance, read, authority-context and revocation cases.
  Earlier raw runs tested the then-advertised enum with expected 201; the drill
  now expects 422 following the human scope clarification. Do not relabel the
  earlier execution as a run of that changed assertion.

The clean run also confirmed corrected same-key project/guide requests succeed
after the length failures; denied foreign edits preserve the original guide;
and the failed adjudicator request leaves no active grant or project access.
These checks bound the observed damage but do not make the incorrect 503s
acceptable. Database and restricted-role cleanup completed successfully; the
owned PostgreSQL server was stopped after the run.

## Repair owners and source locations

- [Project API schemas](../../backend/app/modules/projects/schemas.py):
  `ProjectCreate`, `ProjectGuideCreate`, `ProjectGuideUpdate`.
- [Project persistence](../../backend/app/modules/projects/models.py):
  `Project`, `ProjectGuide`.
- [Project creation](../../backend/app/modules/projects/create_service.py) and
  [guide mutations](../../backend/app/modules/projects/guide_mutation_service.py).
- [AUTH role vocabulary](../../backend/app/modules/authorization/schemas.py),
  [project-role request schemas](../../backend/app/modules/authorization/project_role_schemas.py),
  [AUTH persistence](../../backend/app/modules/authorization/models.py) and
  [grant service](../../backend/app/modules/authorization/project_role_service.py).
- [Canonical database baseline](../../backend/alembic/baseline/v01_schema.sql):
  `authority_facts_are_safe`, `authority_event_facts_are_safe`, role constraints.
- Current role wording in [AUTH specification](../spec_authorization_service.md),
  [glossary](../glossary.md), [architecture](../architecture_lockdown.md) and
  [review lifecycle](../spec_review_lifecycle.md) needs reconciliation with the
  human's two-role scope; assess the [roadmap](../roadmap_status.md) in the repair PR.

## Bounded repair implementation

The [repair change record](../../.commitrail/changes/api-drill-defect-repair.md)
covers the five fixes and their additional regression proof. Request validation
uses the existing 200/120/50 character limits; guide PATCH distinguishes omitted
content from explicit null; current project roles are submitter and reviewer.
The incremental role migration refuses incompatible retained authority history
without deleting or relabeling it. These repair statements do not reattribute
the historical executions above or complete the remaining API audit.

## Drill integrity fixes already made

These are harness repairs, not additional product defects for the other agent:

- A later successful call cannot erase an earlier failure.
- Collected independent failures keep the final CLI exit nonzero.
- Response equality checks nested types strictly: `true` cannot pass as `1`.
- A denied foreign guide edit is followed by a fresh authorized read of that
  same guide through a no-op PATCH, rather than a cached idempotent response.
- Policy-state preservation uses a fresh selector-bound update; cached replay
  alone is not claimed as proof of current state.
- Request pacing retains the server's existing mutation limits.

## Retest and handoff criteria

Use the [new external-client drill](external-api-drill.md), not the older seeded
API drill. Keep the failures above red until product repairs actually satisfy
them. Run the applicable full hosted tests and coverage for the repair; this
drill supplements those tests rather than replacing them.

After the repair merges, run against that exact main head with a fresh isolated
database, actual HTTP and verifier, and unchanged guards. Verify both successful
field behavior and failure-side-effect checks. Continue the remaining endpoint,
field, permission, pagination, policy and reachable lifecycle checks: fixing
these five items alone does not finish the all-field audit. Separate untested or
prerequisite-blocked operations from verified ones before the MCP handoff.
