# Chunk Contract: WS-ARCH-001-CP09 — Legacy Economic Path Removal

Disposition: Planned. Non-executable cleanup coordination after replacement
consumers, including CHECKERS and the public Submission path, are cut over.
Risk: L1.

CP07 removes the legacy economic readiness guard from the new activation
command before AUTH-12H; ARCH-03B removes semantic reads/writes from replacement
task/assignment/submission commands before ARCH-03C. CP09 is not a prerequisite
for either activation or `allow_review`. `ARCH-03C` alone is insufficient:
CHECKERS currently reads locked payment snapshots and legacy public Submission
remains until 02I. Before physical deletion, prove no runtime, response schema,
checker snapshot or public legacy route consumes the fields. If any remains,
its owning delivery boundary removes that consumer first. Remove the remaining retired guide-bound economic schema, fields, services, API vocabulary,
checker snapshots, and remaining semantic consumers after the canonical
ContributionPolicy lineage is the sole live path. Update the consolidated v0.1
baseline and fresh-install parity directly through the repository's bounded
schema workflow. Do not preserve aliases, dual reads/writes, compatibility
columns, historical backfills, or guessed conversion behavior.

The chunk must be split further if current-main discovery shows removal crosses
more than one safely reviewable product boundary.

## Merge state

- Outcome on merge: `planned`
