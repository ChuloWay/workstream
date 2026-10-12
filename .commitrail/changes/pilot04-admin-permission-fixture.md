# [PILOT-04] Reconcile the administrative permission read fixture

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Administrative read coverage expects the two selected PRE permissions already owned by the current AUTH catalogue.

## Intent and scope

The hosted administrative read test still expects 78 permissions, while the
selected PRE execute/finalize contract makes the exact public total 80.
Allowed files are this record and
`backend/tests/authorization/admin_access/test_admin_reads_postgresql.py`.
Change only the expected permission total. Preserve role definitions, authority,
observation and response assertions. No production, migration, workflow, policy,
test selection or catalogue implementation changes are permitted.

## Acceptance and verification

Both parameterized administrative catalogue reads pass against real PostgreSQL.
The old permission expectation fails against the same public response. Run Ruff
and whitespace checks. This is a low-risk fixture reconciliation within PR #538;
the lead reviews the exact diff and native evidence. Human review should confirm
the total corresponds to the selected PRE permissions and no assertion is lost.

## Roadmap

No capability changes: this corrects a fixture for the existing selected AUTH
contract, so no additional roadmap edit is needed.
