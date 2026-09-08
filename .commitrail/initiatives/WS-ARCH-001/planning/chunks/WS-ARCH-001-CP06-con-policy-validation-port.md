# Chunk Contract: WS-ARCH-001-CP06 — ContributionPolicy Validation Port

Status: proposed non-executable skeleton after CP05. Risk: L1.

CON exposes one caller-session, flush-only public validation capability that
accepts an explicit project ID and selected ContributionPolicyVersion ID,
locks and validates that exact published, complete, binding-valid,
same-project ContributionPolicyVersion for guide activation or controlled
human-revision preparation. It owns no ProjectGuide, Task, TaskAssignment,
Submission, claim, ReviewLease, or authorization write.

It does not select a latest/current version, read global current policy at
claim, or call back into guide activation. Return canonical immutable version,
project and validation facts from the selected row. Initial activation and
future controlled revision validate eligibility for that new binding; already
stamped attempts do not revalidate against later publication/retirement.

No migration or legacy removal belongs here. Missing, ambiguous, crossed-
project, draft, incomplete, or invalid binding state fails closed.

## Merge state

- Outcome on merge: `planned`
