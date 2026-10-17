# schema-fingerprint-task-status — Restore the schema guard after the task status constraint

- Initiative: None
- Durable disposition: `Planned`
- Intended merge outcome: PostgreSQL tests on `main` pass the public schema
  fingerprint guard again with `ck_workstream_tasks_status` in place.

## Intent

PILOT-READ-2 (#577) added `ck_workstream_tasks_status` to migration
`0050_contributor_reads` in its last push, and merged before CI ran on that
head. `EXPECTED_PUBLIC_SCHEMA_SHA256` still describes the schema without the
constraint, so every PostgreSQL test on `main` fails at fixture setup with
`unexpected public schema object fingerprint`.

## Current behavior

`backend/tests/conftest.py` pins
`fb6752c0bb1e0f4d518d385a72b58c695f529b68225471680899fe8addd9afec`; the
migrated PostgreSQL 16 schema hashes to
`03d9123a0f605c721c26f28b63da6736b9032923a3934e211f6a5f5491535156`.

## Bounded change

### Allowed

- Replace the pinned fingerprint in `backend/tests/conftest.py`.

### Not allowed

- Any change to product code, models, migrations or other tests.

## Design and decisions

The constraint is intended (it enforces the closed task-status vocabulary the
contributor reads project; see `pilot-read-contributor.md`), so the guard is
updated rather than the constraint reverted.

## Acceptance criteria

- [x] PostgreSQL tests on `main` plus this change pass the fingerprint guard
      on PostgreSQL 16.
- [ ] Hosted Backend lanes pass on this PR.

## Risk and review routing

- Risk class: `L0` (test guard constant).
- Required reviewers: none beyond CI; the value is reproducible by migrating
  to head on PostgreSQL 16.
- Human review focus: that the new value comes from the merged schema only.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Guard failure on `main` | isolated run of `tests/contributor_reads/test_consistency.py` at `d5bac1313`, PostgreSQL 16 | fingerprint error with the value above | None |
| Guard restored | same runner with this change: consistency, projection subsets and the status-constraint parity test | 16 passed | Hosted lanes |

## Review findings

None.

## Reconciliation

- Roadmap: no impact; the capability and constraint are already merged.
- Next usable boundary: unchanged.
