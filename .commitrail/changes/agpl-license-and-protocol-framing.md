# agpl-license-and-protocol-framing — License Workstream and frame it as protocol plus implementation

- Initiative: None
- Durable disposition: `Planned`
- Intended merge outcome: Workstream carries an explicit `AGPL-3.0-only`
  license grant, and its entry documents distinguish the shared protocol from
  the software that implements it.

## Intent

Workstream is publicly visible but has no license grant, so nobody has
permission to use, modify, or redistribute it. Flow Research's license policy
prefers AGPL-3.0 for network server software, and the repository owner directed
`AGPL-3.0-only`, consistent with Garden and Harnessy.

The same change set reframes Workstream as a shared protocol for governed work
plus the software that implements it. It also records future accountable
orchestration as a research hypothesis, and it aligns the product brief with the
community-first funded pilot.

## Current behavior

`main` has no `LICENSE`, no license metadata in `backend/pyproject.toml`, and
no contribution-license statement. Entry documents describe Workstream only as
governed contribution infrastructure.

## Bounded change

### Allowed

- Licensing: `LICENSE`, `backend/LICENSE`, `THIRD_PARTY_NOTICES.md`, the README
  License section, the CONTRIBUTING contribution grant, and PEP 639 metadata in
  `backend/pyproject.toml` (`license`, `license-files`, `setuptools>=77`).
- Framing: `docs/protocol-and-implementation.md` and protocol wording in
  `AGENTS.md`, `README.md`, `docs/glossary.md`, `docs/principles.md`,
  `docs/product_principles.md`, and `docs/architecture_lockdown.md`.
- Research hypothesis: the accountable-orchestration sections in
  `docs/product_brief.md`, `docs/architecture_system_architecture.md`,
  `docs/product_principles.md`, `docs/roadmap_status.md`, and `README.md`.
- Pilot alignment: the v0.1 internal proof surface and success metrics in
  `docs/product_brief.md`.

### Not allowed

- Application behavior, APIs, schemas, migrations, tests, runtime
  dependencies, or CI.
- A license other than `AGPL-3.0-only`, or a sole Flow Research copyright claim.
- Any claim that orchestration is Planned or implemented, or that independent
  protocol interoperability exists.
- Any change to `docs/roadmap_status.md` capability claims.

## Design and decisions

The license text is the unmodified canonical AGPLv3. `backend/` repeats it
because it is the Python distribution root; PEP 639 then packages it in the
wheel. `AGPL-3.0-or-later`, legacy `license = { text = ... }` metadata, a
root-only license, and sole Flow Research copyright attribution were rejected.

The documentation edits predate several merged lifecycle changes. On
reconciliation, current `main` wording ("policy-governed checks" and
"policy-governed acceptance") was kept. FinalAcceptance statements were
corrected to include authorized automated acceptance when the locked
ReviewPolicy sets `human_review_required: false`.

## Acceptance criteria

- [x] `LICENSE` and `backend/LICENSE` are the byte-identical canonical AGPLv3.
- [x] README, CONTRIBUTING, and package metadata declare `AGPL-3.0-only`.
- [x] Third-party notices distinguish installed dependencies from bundled
      material and disclaim a complete transitive inventory.
- [x] No Workstream product behavior changes.
- [ ] A human confirms authority to license existing contributions before merge.

## Risk and review routing

- Risk class: `L0` for licensing; documentation framing is `L2`.
- Required reviewers: docs, senior engineering, CI integrity for package
  metadata, product/operations for contributor-facing wording, and the
  repository owner or counsel for contributor licensing authority.
- Human review focus: authority to license existing contributor history,
  `only` versus `or-later`, and the protocol and orchestration positioning.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| License copies match | `shasum -a 256 LICENSE backend/LICENSE` | Equal hashes | Copies could drift later |
| Metadata parses | `tomllib` read of `project.license` | `AGPL-3.0-only` | None |
| Links and wording | `scripts/check_markdown_links.py`, `scripts/check_stale_workstream_wording.py` | See PR | None |
| Wheel carries license | Isolated `uv build` and wheel inspection on 2026-08-10 | Passed | Re-run in CI against the PR head |

## Review findings

Local reviews of the licensing patch on 2026-08-10 returned PASS or PASS WITH
LOW RISKS with no blocking findings. Those reviews bound to an uncommitted
patch, so they must be repeated against the PR head.

## Reconciliation

- Current-source reconciliation: rebased from `0d0e6a2c3` onto `ce60d0f02`.
  This change resolved conflicts in `AGENTS.md`, `README.md`,
  `docs/product_brief.md`, and `docs/roadmap_status.md`, and replaced the
  retired `.agent-loop/` records with this Commitrail record.
- Next usable boundary: human contributor-rights confirmation, then merge.
- Remaining risks: existing contributor rights are not provable from Git
  history; the third-party notice is not a complete transitive inventory.
