# WS-DB-002-PLAN — Plan the UUIDv7 and native-UUID cutover

- Initiative: WS-DB-002
- Durable disposition: Complete
- Intended merge outcome: a reviewed plan for uniform record identities, not an implemented cutover.

## Intent

The human requests planning first, with no preservation of disposable development
data. Current models mix UUID and text identities; writers include v4 and
deterministic v5. The [overview](OVERVIEW.md) records owners, scope and retry risks.

## Bounded change

Allowed: this record, its overview and the initiative index row. Not allowed:
runtime/schema/test/dependency changes, resets, product behavior, external messages
or opening a PR without a further request. This local planning task does not
change current roadmap capability, exposure or product sequencing; no no-op
roadmap edit or spreadsheet export is required.

## Acceptance criteria

- Define generated record IDs versus meaningful natural/external keys.
- Specify native-UUID storage, one v7 generator, deterministic retry replacement
  and a fresh baseline without conversion/compatibility machinery.
- Cover safe reset boundaries, concurrency with product work, enforcement,
  behavioral proof, risks and implementation sequencing.
- Keep all implementation work visibly Planned.

## Risk and review routing

- Risk class: L1 planning; proposed cutover is L0 broad critical work.
- Required reviewers: focused architecture/plan review, including replay safety.
- Human review focus: uniformity scope, fresh-schema reset and realistic review size.

## Evidence

Source inspection: main after PR #436, model registry, owner models, UUID writers,
active baseline, runtime versions and open work. No runtime behavior or performance
has been proved by this planning change. Verify Markdown links, stale wording and
Commitrail record structure. Next usable boundary: inventory and generation
foundation after human direction to implement. Product work remains independent
except explicitly shared paths and environments.
