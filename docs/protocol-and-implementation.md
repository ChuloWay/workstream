# Workstream Protocol And Implementation

Workstream defines a shared protocol for governed work and provides the
software that implements it. People and AI agents can perform work through
Garden or other clients while following the same rules for assignments,
evidence, verification, review, revision, acceptance, and contribution records.

## Shared Protocol

The protocol describes valid lifecycle actions, their authorization and
evidence requirements, and the records they produce. Its core contracts cover
versioned project rules, tasks, immutable submissions, checks, authorized
Reviews, revisions, FinalAcceptance, and ContributionRecords.

Protocol rules describe what makes work and its records valid; an API exposes
those rules to clients. Supporting several API clients alone does not establish
conformance by independent implementations.

## Software Implementation

The current Workstream software enforces those contracts, checks permissions,
stores evidence, and records lifecycle outcomes. It remains the canonical
authority for the work it manages. Garden and other clients cannot bypass its
authorization or write contribution truth directly.

Workstream also evaluates contribution policy into conditional compensation
awards. Fulfillment tracking and payment-provider transfers through the
established adapter boundary are Planned, not live; see
[Current v0.1 Status](roadmap_status.md). Acceptance alone does not release
payment.
This framing does not change award eligibility, finance authority, or receipt
ownership, and does not make a payment provider part of the core protocol.

## Status And Formalization

The protocol framing is the agreed product direction. The existing canonical
specifications and lifecycle implementation provide its starting contracts;
this document does not claim a released standalone interoperability standard,
independent conforming implementations, or an existing conformance suite.

Formalization requires a versioned specification identifying normative
contracts, mandatory invariants, extension boundaries, compatibility rules,
and executable conformance tests. These should be derived from the validated
v0.1 lifecycle. Formalizing them must not expand the current implementation
into federation, consensus, blockchain settlement, or automated routing.

The current [architecture lockdown](architecture_lockdown.md),
[glossary](glossary.md), and [capability ledger](roadmap_status.md) remain
authoritative for implementation scope, stored names, and delivered behavior.
