# Restore retained audit evidence under PostgreSQL's empty search path

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: Standard PostgreSQL backup restoration validates retained authorization audit rows without relying on the restoring session's search path.

## Intent

The hosted drill for #555/#582 restored its retained database snapshot into a network-isolated PostgreSQL 16 container. Standard `pg_restore --exit-on-error --no-owner --no-privileges` failed while loading `audit_events`: `authority_event_facts_are_safe` could not resolve `authority_facts_are_safe`. The function and its grant-facts helper use unqualified sibling calls and do not pin their own search paths. `pg_restore` deliberately clears the session search path.

An isolated diagnostic restored schema first, pinned those two functions to `pg_catalog, public, pg_temp`, and then restored data and post-data successfully. All 121 public tables restored; the source database and retained snapshot were unchanged. This is a proposed-repair probe, not a claim that the original snapshot restores unmodified or that the full contribution journey has passed.

## Bounded change

Allowed files:

- `backend/alembic/versions/0060_audit_restore_path.py` and `backend/alembic/env.py`.
- `backend/tests/conftest.py` schema fingerprint and `backend/tests/test_alembic.py` predecessor, function-custody and downgrade proofs.
- `backend/tests/migrations/test_project_role_schema.py` focused PostgreSQL audit-helper/COPY proofs.
- This record and `deploy/hosted/README.md` restore guidance.

Prohibited changes:

- No disabled audit checks or triggers, weaker privacy rules, evidence deletion, rewriting retained rows, downgrade support, new authentication path, CI workflow/lane additions or general database refactor.
- Do not alter another agent's model-runtime migration. Reconcile the linear chain against merged main before publication.

## Plan

1. Review the proposed two-function path correction against audit call sites and existing migration ownership.
2. Add a forward migration preserving function bodies and existing immutable data; preserve established downgrade refusal.
3. Prove the defect with valid facts under the same empty search path used by `pg_restore`, then prove repaired valid and invalid controls. Exercise ordinary dump/restore with representative audit evidence in an isolated PostgreSQL database.
4. Run affected migration/schema checks and reviews; leave deployment and fresh live backup/restore for the reviewed merged candidate.

## Plan review

Security/architecture plan review: PASS WITH LOW RISKS. The two helper paths cover the reproduced failure. Existing pre-fix backups still require isolated schema-first repair or replacement with a fresh post-upgrade backup; this change does not silently rewrite old backups.

## Acceptance criteria

- Valid retained audit facts validate with an empty session search path.
- Invalid private/role facts remain rejected.
- Temporary objects cannot replace the canonical helper resolution.
- Existing database upgrade preserves audit identities and contents; ordinary backup restore succeeds after the schema correction.
- Removing the function-path repair makes the focused regression fail for missing helper resolution.
- Exactly one migration head, correct fingerprint, unchanged test selection and forward-only migration behavior.

## Risk and review routing

Risk: L1, authorization audit storage and restore reliability.
Required review: security, architecture, QA/test-delta; CI integrity if schema fingerprint or test allocation metadata changes; docs for affected claims.
Human focus: the repair changes name resolution only, preserves validation semantics, and proves restore without bypassing constraints.

## Roadmap impact

This closes a discovered restore prerequisite under #582; it does not activate a new product capability or complete the hosted journey. Assess the current release-gate wording with the final candidate.

## Evidence

- Final focused PostgreSQL run: ten passed, including four COPY/direct-helper cases, existing role-vocabulary proof, single-head graph, immediate-predecessor upgrade with exact function body/identity preservation, two one-revision downgrade refusals and the canonical schema/reset guard.
- Isolated restore diagnostic: after correcting the two function paths, a fresh ordinary dump restored without schema interception. All 121 table row counts/digests matched. Owned containers were removed. This does not prove future task/submission/acceptance recovery; those records do not yet exist in this drill.
- Canonical schema fingerprint regenerated from the migrated PostgreSQL schema; no test selection or CI workflow changed.
- Roadmap assessment: #582 already retains restore as an outstanding release prerequisite. The repair changes no capability exposure, completion claim or next dependency, so no roadmap edit is needed. Full hosted journey evidence remains outstanding.
