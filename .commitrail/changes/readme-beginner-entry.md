# readme-beginner-entry — Make the README a beginner entry point

- Initiative: None
- Durable disposition: `Planned`
- Intended merge outcome: a new reader can learn what Workstream is, its
  current status and how to run it from a short README, and every detail the
  old README held remains available, unchanged, in linked documents.

## Intent

The README had grown to 1,033 lines of implementation history, internal change
identifiers and setup detail. The repository owner asked for a beginner-friendly
README written to ASD-STE100 Simplified Technical English principles.

## Current behavior

`README.md` mixed the product definition, lifecycle invariants, change-by-change
implementation status, the full CLI command narrative, developer setup and the
documentation index in one file.

## Bounded change

### Allowed

- Rewrite `README.md` as a short introduction: definition, lifecycle steps, key
  terms, non-goals, current status, Docker quick start, CLI pointer, repository
  layout, reading guide, contribution pointer and license.
- Move the detailed sections verbatim to `docs/workstream_reference.md`, the
  setup procedures to `docs/engineering/developer-setup.md` and the document
  lists to `docs/README.md`, with link paths rebased.
- Repoint the two inbound `#developer-quickstart` links.

### Not allowed

- Any change to product behavior, capability claims or roadmap status.
- Dropping detailed content instead of moving it.

## Design and decisions

The README states only facts already in the old README or in
`docs/roadmap_status.md`, in short active sentences with defined terms. Moved
text is not rewritten, so its precision and its stale-wording checks are kept.
Only two moved lines changed: a "top of this README" reference now links to the
lifecycle section, and the setup guide has its own title and introduction. This
follows ASD-STE100 principles; it makes no claim of formal ASD-STE100 compliance.

## Acceptance criteria

- [x] Every non-blank line of the old README appears in the new files, apart
      from the retitled headings, the reworded license paragraph and the
      self-reference noted above.
- [x] Markdown links and stale-wording checks pass.
- [x] No roadmap impact: no capability, exposure or remaining scope changes.

## Risk and review routing

- Risk class: `L2`
- Required reviewers: docs review.
- Human review focus: whether the README status summary and lifecycle steps are
  accurate and simple enough for a new reader.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| No content lost | Line-by-line comparison of the old README with the four new files | 13 differences, all listed above | None |
| Links and wording | `scripts/check_markdown_links.py` and the stale-wording checks | Passed | None |

## Review findings

None yet.

## Reconciliation

- Current-source reconciliation: based on `main` at `34501cd64`.
- Next usable boundary: None.
- Remaining risks: None.
