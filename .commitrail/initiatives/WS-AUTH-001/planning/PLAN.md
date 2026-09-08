# WS-AUTH-001 — Current pre-review activation plan

The [cross-owner dependency contract](../../WS-ARCH-001/planning/PLAN.md#current-dependency-contract)
owns current delivery order through `allow_review`. The
[preserved plan](../pre-cutover/PLAN.md) retains completed history; its broad
AUTH-13/14 cutovers are not additional implementation work.

- AUTH-12I/12J/12B2 are complete. POL-04B consumes their exact adapters.
- AUTH-12F4 follows hidden POL-05A approval/provenance and precedes POL-05B.
- AUTH-12G follows hidden POL-06A post-policy operations and precedes POL-06B.
- [AUTH-12H](chunks/WS-AUTH-001-12H-guide-activation.md) follows POL-07 and
  hidden CP07. It activates only the complete PROJECTS guide command.
- CP05 owns exact ContributionPolicy-action activation after merged CP04B.
- ARCH-03B owns task behavior and ARCH-03C owns its exact activation.
  [AUTH-13 is superseded](chunks/WS-AUTH-001-13-task-assignment-cutover.md).
- ARCH-04D alone activates post-submit materialization and final-result
  persistence after ARCH-04B/04C; historical AUTH-14 and XINT-06B cannot start
  in parallel. Later queue/read/reconciliation work must be separately owned.

For 12F4/12G, adopt only the exact action purposes from preserved contracts;
the current POL-05A/06A operations determine authoritative resource facts,
replay identity and separate downstream storage. AUTH consumes public facts,
never creates policy storage or mutates a finalized setup row. Each mutation
binds actor/link/grant or exact fixed service, project, operation/correlation,
compilation/component/approval identities, session and transaction. Test
cross-project, stale generation, substituted action/resource, revoked authority,
concurrent replay and rollback before activating the live adapter.

No legacy task-eligibility fallback survives in a replacement command. Remove
its affected consumer with ARCH-03B/03C; later cleanup proves absent consumers,
not permission to delete a still-live public path. Existing actions and
registrations are reused, never re-created under aliases.
