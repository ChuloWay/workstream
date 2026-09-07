# Roadmap checker stages and same-PR maintenance

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: distinguish intake checks from post-submit evaluation and require same-PR roadmap impact assessment.

## Intent

Make both checker stages visible in the existing v0.1 roadmap and prevent stale
capability claims without a separate post-merge update cycle.

## Bounded change

- Allowed: `docs/roadmap_status.md`, `AGENTS.md`, `CONTRIBUTING.md`, this record;
  synchronize ignored roadmap exports if present.
- Not allowed: runtime behavior, checker dispatch, canonical specifications,
  CI gates, approval authority, historical archives, new release scope.

## Acceptance criteria

- Show pre-submission checks before Submission creation and durable post-submit
  evaluation after it; neither replaces authorized review.
- Distinguish unified setup proposals from runtime execution and supported
  current behavior from future integration.
- Reconcile the selected AUTH audit delivered in PR #379; do not mark open
  product implementation complete.
- Each PR assesses roadmap impact before readiness. Update changed capabilities
  and next boundaries in that PR; explain no impact in the PR when applicable.
  No mandatory no-op file edits, second permission system, or post-merge PR.

## Risk and review routing

- Risk class: L2, documentation of existing lifecycle and contribution rules.
- Reviewers: documentation and product/operations, one bounded review assignment.
- Human focus: stage separation and proportionate same-PR maintenance.

## Evidence

- Proof: canonical checker specifications and current initiative records;
  Markdown links, stale wording, Commitrail validation, diff checks. Hosted
  CI remains unchanged. No local roadmap spreadsheet exports are present.
