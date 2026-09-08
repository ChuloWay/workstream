# WS-AUTH-001 — Workstream authorization service

Current change: [WS-AUTH-001-12B2](WS-AUTH-001-12B2.md).

Historical pre-cutover work records: [`STATUS.md`](pre-cutover/STATUS.md),
[`CHUNK_MAP.md`](pre-cutover/CHUNK_MAP.md), and
[`planning/chunk contracts`](pre-cutover/chunks/).

- Disposition: Planned
- Intent: provide deny-default, project-scoped authority with canonical human
  and service identities and attributable audit evidence.
- Current boundary: hidden projections and atomic setup finalization have exact
  request-local authority through AUTH-12J and AUTH-12B2.
- Next usable boundary: POL-04B live setup cutover; later AUTH-12F4 activates
  approval only after the corresponding policy owners are proven.
- Governing source: `docs/spec_authorization_service.md`, authorization code,
  migrations, and tests.
- Preserve: Flow token verification only, no Workstream login/session system,
  exact action/permission catalogues, prepared mutation protocol, and
  fail-closed action availability.

## Delivered

- Flow-token verification, canonical actors/identity links, request and rate
  controls, audit/idempotency, project grants, bootstrap administration,
  fixed-service admission, controlled provisioning, and project read/mutation
  authorization are merged.
- Project-guide compilation request, recovery, fixed setup execution, and
  exact deterministic-projection authority are merged through `12J`; hidden
  POL projection ports exist through POL-04A3.
- AUTH-12B2 activates only fixed setup-service finalization of exact locked
  facts, with current lifecycle checks, immutable receipt binding, and exact
  historical replay. Its explicit adapter remains outside live HTTP/Celery wiring.

## Remaining v0.1 sequence

1. POL-04B connects the complete hidden finalization and exact AUTH-12B2 adapter
   to live setup execution.
2. `12F4`, `12G`, and `12H`: activate stored pre-submit/post-submit and final
   guide behavior only after their owner implementations and CON CP05-CP07.
3. Reframe `13`-`16` against then-current TASK, checker, cleanup, and
   conformance behavior; do not execute the obsolete broad `14` design.
