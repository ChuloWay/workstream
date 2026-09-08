# Chunk Contract: WS-ARCH-001-CP07 — Project Guide Policy Binding

Status: proposed non-executable skeleton after CP06. Risk: L1.

Preserve the ReviewPolicy setting change's activation guard:
`human_review_required=false` may exist in draft, but activation must fail
until the authorized automated FinalAcceptance/CON path is proven and
available. Validate the exact guide-bound policy, never silently change it
to true. True does not depend on automated acceptance. This is the same
requirement as the existing activation path, not a second policy mechanism.

PROJECTS builds hidden, deny-by-default guide-activation behavior to call the CON public
validation capability and persist the returned exact version as non-null
`ProjectGuide.contribution_policy_version_id`. PROJECTS owns the guide write and
single transaction; it imports no CON models/repositories and performs no
policy selection itself.

The owner command validates and binds the exact explicitly selected policy
version during the eventual activation transaction, not on sufficiency or
claim. It does not activate a route or action. AUTH-12H later supplies exact
`project.guide.activate` Project Manager authority over these public facts;
`project.guide_sufficiency.run` cannot authorize publication or policy binding.
CON validation is a dependency, not a callback into PROJECTS activation.

The PROJECTS hidden activation command owns the replacement readiness guard:
ContributionPolicy must be same-project and active, with the explicit expected
version equal to its current published selector, complete for submitter and
reviewer and binding-valid. CON validates this under lock; PROJECTS never
silently substitutes a newer version. This validation is for a new guide
binding, not revalidation of already frozen work against current policy.
Review/revision policy IDs, `policy_generation`, hashes and guide generation must also be
complete and consistent. CP07 replaces the legacy PaymentPolicy requirement
for this new path before AUTH-12H activates it; CP09 only removes unreachable
legacy schema/consumers later. No missing-policy bypass flag or dual fallback.
Reuse existing selected review/revision fields rather than duplicating them.
Provide the canonical activation response/read projection without a required
`payment_policy`: the current `ActiveGuideResponse` and load/refresh/serialize
path still require it. The replacement must reach successful activation and
response serialization without that legacy row, not just bypass one boolean
guard. AUTH-12H wires this complete command/response, not the old service path.

Within one caller transaction, lock and validate the selected immutable CON
version/eligibility, consume exact activation authority, bind the version and
activate the guide atomically. Define replay/resource facts and rollback/race
proof here for AUTH-12H to consume; CP07 must not depend on an already-active
guide. Hidden tests use the unavailable-by-default port and controlled authority
fixtures, not a public action that is still planned.

This chunk reconciles the current v0.1 baseline schema for ProjectGuide only.
TASK/Assignment/Submission fields and physical legacy economic-path removal
remain later. Required evidence: valid complete activation candidate, missing
reviewer rule, foreign/retired/binding-invalid policy, stale generation,
concurrent retire/activation ordering, and no partial guide binding on denial
or rollback. Canonical CON validation remains the sole policy-rule validator.

## Merge state

- Outcome on merge: `planned`
