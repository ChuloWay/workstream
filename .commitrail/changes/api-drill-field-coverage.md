# External API drill field coverage

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Extend client-side authorization and project-role field proof and document the remaining MCP handoff boundary.

## Intent and design

The merged repair passes both existing real-HTTP drills. Successful calls are
not complete API contracts: list cursors, filter combinations and nested
qualification constraints still need explicit probes. Reuse the existing
isolated runner and HTTP client; do not add another framework or infer proof
from OpenAPI presence. Record exact nested equality assertions and successful
request-provenance checks without claiming unexecuted field combinations.

## Bounded scope

Allowed: `backend/scripts/external_api_drill.py`,
`backend/scripts/admin_api_drill.py`, `scripts/test_external_api_drill.py`,
`scripts/test_admin_api_drill.py`, `docs/engineering/external-api-drill.md`,
`docs/engineering/external-api-drill-findings.md`, `docs/roadmap_status.md`,
and this record. Local ignored roadmap exports, if present, follow AGENTS.md.

Prohibited: product code, migrations, permissions, hidden routes, seeded product
SQL writes, disabled guards, production credentials, CI/coverage changes, MCP
implementation, and product-builder files. Newly discovered product defects are
reported with reproductions, not silently accepted or repaired in this scope.

## Plan and acceptance

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

## Risk, review and verification

Risk: L1, authorization evidence integrity; production behavior is unchanged.
Plan feasibility review precedes implementation. Focused security review covers
cursor/resource substitution, unchanged-state proof and secret handling. QA and
test-delta review cover falsifiable assertions; documentation review covers
MCP claims. Related tracks may share a bounded reviewer assignment.

Commands: `backend/.venv/bin/python -m unittest scripts.test_external_api_drill
scripts.test_admin_api_drill`; the two isolated commands in
`docs/engineering/external-api-drill.md`; `python3 scripts/check_commitrail_records.py
--base-ref origin/main`; `python3 scripts/check_markdown_links.py`;
`python3 scripts/check_stale_workstream_wording.py`; applicable Ruff checks.
Full hosted Backend tests and coverage remain authoritative; no full local suite.

Human review focus: distinguish verified client behaviors, missing field probes,
and unavailable flows. Bootstrap remains operator setup, not an MCP endpoint.
No new human design decision is required within these boundaries.
