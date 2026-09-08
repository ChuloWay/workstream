# Chunk Contract: WS-ARCH-001-CP06 — ContributionPolicy Validation Port

Status: proposed non-executable skeleton after CP05. Risk: L1.

CON exposes one caller-session, flush-only public validation capability that
accepts explicit project, ContributionPolicy and expected version IDs.
For new guide activation, lock the same-project policy aggregate first,
require it to be active, and require its `current_published_version_id` to
equal the expected version. Then lock and validate that exact published,
complete, binding-valid version, both rules, definitions and bindings.
An explicit old published version is not eligible merely because it exists.
It owns no ProjectGuide, Task, TaskAssignment,
Submission, claim, ReviewLease, or authorization write.

The current selector is validated, never silently substituted for a stale or
missing expected version. Reuse exact repository reads and caller-session
locking; `get_selected_version` alone is insufficient because its explicit-ID
path does not check selector equality and its omitted-ID path permits fallback.
Return canonical version, project and validation facts. Do not read global
current policy at claim or call back into guide activation. Controlled human
revision adopts the complete eligible guide context, not an independently
selected replacement policy. Already stamped attempts do not revalidate
against later publication/retirement.

Expose distinct typed validation purposes, not a boolean fallback:

- New guide activation validates the expected active-policy/current-version
  selector as above.
- Later human-revision adoption validates the exact version bound to the
  supplied newly active complete guide context, including same-project rule
  and binding eligibility. It must not require that guide-bound version to
  equal a subsequently advanced global selector. Unchanged guide/context
  preserves the old attempt without a CON reselection call.

Prove an unchanged revision context survives later publication, a changed
complete guide adopts its exact bound version, and a caller's unrelated newer
policy version cannot be substituted. CP06 defines this port contract only;
downstream REV/TASK execution remains outside this pre-review implementation.

No migration or legacy removal belongs here. Missing, ambiguous, crossed-
project, inactive aggregate, stale expected selector, draft, incomplete, or
invalid binding state fails closed. Prove concurrent publication/retirement
against activation in both lock orderings, complete caller rollback, and that
later publication does not mutate or invalidate an existing locked attempt.

## Merge state

- Outcome on merge: `planned`
