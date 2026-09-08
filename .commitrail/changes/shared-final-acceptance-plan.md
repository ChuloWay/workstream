# Shared final acceptance — two triggers, one outcome

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: reconcile existing acceptance owner contracts and add inspect-and-reuse-first guidance; no product runtime change.

## Intent

The human requires one acceptance operation, not separate human and automated
acceptance systems. PR386 delivered the versioned ReviewPolicy boolean, but
false guide activation still fails closed. Existing owner specifications still
require a Review for every FinalAcceptance, contradicting the accepted false
branch. Resolve that planning ambiguity before implementation.

## Bounded change

Allowed: AGENTS.md; current acceptance, authorization, data-model and contribution
specifications; adopted REV/CON/ARCH handoffs and capability ledger.
Prohibited: backend, migrations, CI, product-builder worktree changes, archive
rewrites, new workflow engines, adjudication, enabling false at runtime.

## Design and decisions

Reuse the existing locked ReviewPolicy, REV-owned FinalAcceptance, TASK effects
and CON submitter participant. Human accept and authorized successful-check
routing invoke one REV-owned shared operation with injected public ports and
one caller commit. Record which trigger was used; only actual human Reviews
earn reviewer contributions. The canonical source and transaction
contract lives in `docs/spec_review_lifecycle.md`, not a second planning schema.
Rejected: synthetic Reviews, a second acceptance entity, eventual contribution
creation, and enabling false before its shared transaction is proven. Publish
the existing TASK manifest schema before its REV FK; pull the existing shared
fence/ordinal foundation before acceptance. Neither foundation depends on live
human review. AUTH's existing proposed routing action owns guarded derived
effects, not a new materialization action or generic contribution permission.

## Acceptance criteria

- Both triggers have explicit source, authority and immutable policy lineage.
- One commit covers task completion, acceptance, submitter contribution,
  conditional awards and audit/outbox; no reviewer record on false.
- Dependencies permit false without live human queues or leases, but require
  the real shared acceptance/CON and AUTH foundations.
- Current owner contracts agree; historical archives remain unchanged.
- AGENTS.md requires inspection and reuse without a new permission gate.

## Risk and review routing

- Risk: L1 planning across lifecycle, authorization and compensation boundaries.
- Review: architecture/security/reuse and product/operations/documentation.
- Human focus: one operation, locked boolean, no synthetic reviewer or partial
  acceptance, and no claim that this plan enables runtime behavior.

## Evidence

Validate Markdown links, stale wording, Commitrail structure and scoped diff.
Review contract feasibility and negative source/rollback cases independently;
future implementation tests are requirements, not executed runtime evidence.
The next product work remains in its existing owner sequence; this change does
not alter CP05 policy activation or start product implementation.
