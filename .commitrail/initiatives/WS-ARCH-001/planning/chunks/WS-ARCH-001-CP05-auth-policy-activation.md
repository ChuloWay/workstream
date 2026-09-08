# Chunk Contract: WS-ARCH-001-CP05 — ContributionPolicy AUTH Activation

Status: proposed non-executable skeleton after merged CP04A/CP04B. Risk: L1.

AUTH integrates exact ContributionPolicy evaluators and activates only the
policy operations proven by CP04. It adds no ProjectGuide, TASK, REV, award,
fulfillment, or provider behavior.

The exact actions are `contribution.policy.read`,
`contribution.policy.create_draft`, `contribution.policy.update_draft`,
`contribution.policy.publish` and `contribution.policy.retire`. Reuse their
existing catalogue identities, canonical permission/role policy and the merged
CON public operation contracts; do not create service authority or infer a
permission from a role name. The implementation manifest must enumerate each
allowed principal/action pair and its concealed denial cases.

Allowed changes are AUTH evaluators/PREP adapters, exact composition and
catalogue/database parity, plus focused AUTH/CON integration tests. CON retains
policy locks, validation and flush-only writes; the caller commits once.
No new policy lifecycle or selector semantics belong to this activation.

Prove all five action deltas, unrelated planned denial, cross-project and
actor/link/grant substitution, publication/retirement races, exact replay after
fresh authorization, conflicting replay denial and complete rollback of policy
and decision evidence. Reuse CP04 publication/quantity/binding invariants rather
than replacing them with AUTH-only fixtures. Review architecture, security,
product/operations and QA, plus affected CI/test changes. Human focus: exact
activation of existing behavior without broadening Finance or service powers.

## Merge state

- Outcome on merge: `planned`
