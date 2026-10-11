# PILOT-10B — Fixed-membership contribution export pages

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Existing authorized contribution exports traverse more than 1,000 records with signed, expiring cursors and fixed contribution membership.

## Intent

Finance, PMs and contributors must export their complete authorized contribution
selection without narrowing filters merely to stay under one response bound.

## Current behavior

PILOT-10A exposes JSON/CSV reads through the canonical CON projection and fresh
AUTH in a repeatable-read response transaction. The repository refuses selections
above 1,000 contributions. AUTH's existing signed timestamp/UUID keyset codec
protects other reads; it does not freeze export membership across transactions.

## Bounded change

### Allowed

- CON API/read facts, repository, projection, owner-local export cursor codec and
  record model; explicit CON composition and existing export REST dependencies/routes.
- Read indexes for existing CON actor/project ordering and private membership ordering.
- One sole-author native migration and corresponding schema/reset registration,
  after coordination with the existing migration owner; no guessed revision.
- Focused contribution projection/cursor/native public-API regression tests,
  affected public schema capture, additive CI ownership and current export docs.

### Not allowed

- Economic recognition, award definitions, policy custody, acceptance/routing,
  fulfillment, new roles/actions, weakening authority or immutable source evidence.
- Importing AUTH-private codec code into CON; parallel old/new export readers;
  native migration authored by anyone except the coordinated migration owner.
- Automatic mutation retry, removed CI checks, deployment or merge.

## Design and decisions

Extend the existing read operation with bounded page_size and cursor. Each page
retains its complete awards and fresh canonical authority through serialization
and commit. Sign actor, audience, project, normalized filters, format, page size,
original membership snapshot and last timestamp/UUID boundary with the existing
configured pagination secret. Expire cursors after 15 minutes and reject invalid
or cross-query continuation without disclosing facts. JSON exposes next_cursor;
CSV uses X-Workstream-Next-Cursor and X-Workstream-Exported-At headers.

Native membership uses two CON-private expiring tables: a header bound to actor,
normalized query and a 15-minute export instant, and immutable contribution IDs
with their recorded-time ordering keys. First-page membership capture uses the
same fresh-authorized repeatable-read transaction as canonical projection.
The complete selection is bounded at 100,000 contributions; each page at 1,000.
Headers are sealed before commit; member additions after sealing are refused.
Expired headers/members alone may be removed, in batches of at most 100 during
reads; retained contribution and award records are never changed or deleted.

A timestamp/UUID watermark does not exclude late commits. Native xid8 snapshot
filtering would also require provenance metadata on economic rows, cutover rules
and cluster/restore identity handling. Focused peer design review selected the
explicit membership list because ordinary native FK-backed data preserves the
selection through restart and logical restore without that extra subsystem.
CLI is a separate bounded PR.

## Acceptance criteria

- [ ] Multi-page traversal returns each originally visible selected contribution
  once, in timestamp/UUID order, with its complete exact award set.
- [ ] Delayed commits, later/backdated inserts and savepoints do not change membership.
- [ ] Retained data remains readable; new metadata cannot be forged or mutated.
- [ ] Forged/expired/cross-actor/query cursors fail; revoked authority conceals every page.
- [ ] JSON and CSV share identical page membership and stable exported_at.

## Risk and review routing

- Risk class: L1
- Required reviewers: architecture, security, QA, test_delta, documentation.
- Human review focus: native visibility/restore semantics, fresh authority and exact evidence.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Current implementation | Inspect canonical CON read and AUTH keyset owner | Existing read extended; peer selected expiring native membership | Installed native implementation pending |
| Membership/authority | Real PostgreSQL installed-schema public reads, delayed commit and revocation controls | Planned | No native runtime claim yet |
| Cursor/projection validation | Focused cursor, exact projection, CSV and canonical-only model discovery | 68 pass; independent scope/expiry mutants fail intended assertions | No native membership claim |
| Required repository checks | CI lane catalogue and behavior ownership tests; Ruff; changed Markdown links | 203 pass after additive registration repair; lint and links pass | Full hosted/native proof pending; no readiness claim |

## Review findings

Focused peer plan review selected private expiring membership over cluster-local
transaction-ID coupling. Source review reproduced missing canonical-only model
registration in a fresh process. Membership declarations now live in CON's
existing registered records/models.py; the separate declaration module was
removed, with a fresh-process regression preserving native FK compilation.
Implementation still requires installed-schema proof.

## Reconciliation

- Current-source reconciliation: starts from main d47ee1e, including merged PILOT-10A.
- Next usable boundary: separate CLI export PR and the pilot closing drill.
- Remaining risks: native membership mechanism and restore binding not yet frozen.
