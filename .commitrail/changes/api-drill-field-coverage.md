# External API drill field coverage

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Extend client-side field proof, repair qualification request admission, and document the remaining MCP handoff boundary.

## Intent

The merged repair passes both existing real-HTTP drills. Successful calls are
not complete API contracts: list cursors, filter combinations and nested
qualification constraints still need explicit probes. Reuse the existing
isolated runner and HTTP client; do not add another framework or infer proof
from OpenAPI presence. Record exact nested equality assertions and successful
request-provenance checks without claiming unexecuted field combinations.

## Bounded change

Allowed: `backend/scripts/external_api_drill.py`,
`backend/scripts/admin_api_drill.py`, `scripts/test_external_api_drill.py`,
`scripts/test_admin_api_drill.py`, `docs/engineering/external-api-drill.md`,
`docs/engineering/external-api-drill-findings.md`, `docs/roadmap_status.md`,
and this record. The human expanded this same PR to repair API-DRILL-006:
`backend/app/modules/authorization/schemas.py`, existing
`backend/tests/test_api_drill_repairs.py`, and
`docs/spec_authorization_service.md` are also allowed for request admission,
regression proof and its documented bound. Local ignored roadmap exports, if
present, follow AGENTS.md.

Prohibited: other product code, migrations, permissions, hidden routes, seeded product
SQL writes, disabled guards, production credentials, CI/coverage changes, MCP
implementation, and product-builder files. Other newly discovered product defects
are communicated with a recommendation to repair in scope or hand off; no silent
expansion or weakening of probe expectations.

## Acceptance criteria

1. Inspect pagination/filter owners and qualification schemas; place scenarios
   where HTTP-created fixtures have the necessary live authority and rows.
2. Traverse populated pages, compare identities with independently established
   expected rows, reject duplicates/missing rows and bound traversal. Exercise
   tampered and wrong-scope/filter cursors, valid filters and invalid limits.
3. Exercise qualification omission/null/type/boundary/cross-field inputs with
   valid controls and unchanged grant readback after denials. Retain existing
   success, replay, revocation and unsupported-role probes.
4. Index nested fields only after real equality assertions pass; distinguish
   value assertions from shape checks and avoid granting array-item evidence
   for empty arrays. Preserve failed-case status and private report contents.
5. Run helper regressions, both clean-candidate real HTTP/PostgreSQL drills,
   focused review and hosted checks. Reconcile documentation with actual proof;
   do not advertise complete field certification or untested product flows.
6. Preserve the existing bounded public qualification fields and the 2,048-byte
   canonical limit for other authority mutations. Admit the full permitted
   project-role issuance envelope with a narrowly typed finite bound. Prove
   both roles' maximum reference collections through public validation,
   canonical/prepared admission, database persistence and exact replay; retain
   malformed, unauthorized, idempotency-conflict and safe-error rejection.

## Risk and review routing

Risk: L1, authorization evidence integrity and bounded request-admission repair.
Plan feasibility review precedes implementation. Focused security review covers
cursor/resource substitution, unchanged-state proof and secret handling. QA and
test-delta review cover falsifiable assertions; documentation review covers
MCP claims. Architecture review additionally checks consistency across public,
canonical/prepared and stored/audit owners. Related tracks may share a bounded
reviewer assignment.

## Evidence

Commands: `backend/.venv/bin/python -m unittest scripts.test_external_api_drill
scripts.test_admin_api_drill`; the two isolated commands in
`docs/engineering/external-api-drill.md`; `python3 scripts/check_commitrail_records.py
--base-ref origin/main`; `python3 scripts/check_markdown_links.py`;
`python3 scripts/check_stale_workstream_wording.py`; applicable Ruff checks.
Full hosted Backend tests and coverage remain authoritative; no full local suite.

Human review focus: distinguish verified client behaviors, missing field probes,
and unavailable flows. Bootstrap remains operator setup, not an MCP endpoint.
No new human design decision is required within these boundaries.

## Review findings

Plan review distinguished unsigned administrative position cursors from signed
project query cursors. Internal review found that active-only readback could
miss a forbidden revoked row; qualification denials now read unfiltered history.
It also found old response annotations flowing into the newly separated request
index; those call sites are corrected and invalid annotation prefixes fail closed.
Failed combined-boundary controls now also verify unchanged history and denied
project access. Expected pagination identities reject duplicate response IDs
before insertion, so one logical grant cannot silently overwrite another.

## Product finding

The combined qualification-bound control exposed API-DRILL-006: public validation
accepts inputs whose canonical request exceeds the internal 2,048-byte admission
limit, producing 500 rather than a successful valid grant. Expected 201 remains
unchanged and failure remains in the report. Independent smaller positive/replay/
revocation cases continue. The human subsequently authorized repairing this
narrow product defect in the same PR, followed by both complete drills. Extend
only the validated project-role issuance envelope: a global size increase or
reducing advertised qualification limits would change unrelated boundaries or
the client contract. The findings document preserves the original reproduction.
