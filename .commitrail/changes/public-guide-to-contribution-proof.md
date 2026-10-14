# Public guide input to governed contribution proof

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Replace the approved-guide shortcut in the bounded public runtime drill with public guide upload, asynchronous setup, separate manager approvals and exact policy activation, preserving both outcome branches.

## Intent

Issue #552 closes the integration gap between existing guide setup and the public
contributor journey. The first usable v0.1 path must start with original guide
bytes and task examples, not injected approved policy rows. This is integration
proof and owner-scoped defect repair, not a new setup or acceptance subsystem.

## Current behavior

Main `82a46ff3c` includes #549 public intake and #550 false-guide activation.
`experiments/pilot04_external_checker_runtime/run_public_journey_probe.py` runs
real API, MinIO, Redis, prefork workers, Beat and external checker images, but
`_one_mode` arranges compilation and approved policy facts through `source_case`.
`backend/scripts/guide_document_api_drill.py` covers real public upload and live
setup separately. `backend/scripts/guide_compilation_e2e.py` provides a scripted
external runtime behind the canonical adapter port. Neither composes the whole
journey from public source documents to contribution facts.

## Bounded change

### Allowed

- `experiments/pilot04_external_checker_runtime/run_public_journey_probe.py` and
  narrowly scoped companion guide-input/runtime helpers in that directory:
  replace fixture setup, retain downstream custody/outcome assertions.
- `experiments/pilot04_external_checker_runtime/README.md`: exact invocation,
  input, evidence, resource cleanup and limitations.
- `backend/scripts/guide_compilation_e2e.py` only where sharing existing scripted
  provider behavior avoids duplicate source/custody rules; callers must retain
  their current supported contracts.
- Focused drill tests under `scripts/test_public_guide_journey*.py` or existing
  affected test owners; root tests must not silently require a backend install.
- This record, README, affected current roadmap and ARCH navigation: connected
  local proof versus hosted deployment and held evaluator work.
- Product fixes only after a concrete integration failure is reproduced and its
  exact owner/files, requirement and discriminating regression are added here
  and reviewed before implementation.

### Not allowed

No direct guide, compilation, policy, activation, Task, Submission or acceptance
fixture writes for the connected setup path. No weakened AUTH/custody guards,
new approval semantics, fallback routes, provider discovery, live model claim
from recorded output, private project documents, CI gate changes, evaluator
expansion, payment delivery, contributor lease work, frontend or CLI work.
Checker registry and initial identity/service provisioning remain explicit
isolated infrastructure preconditions and must not substitute for guide facts.
Held #492/#493/#496 remain held. Security #565 and pagination #497 are separate.

## Design and decisions

Extend the existing real runtime drill; remove its superseded approved-guide
bootstrap mode rather than maintain parallel fixture/public journeys. Use only
synthetic shareable guide originals with at least one meaningful task example.
Exercise actual Celery delivery and the canonical runtime adapter port with an
explicitly recorded test provider in the isolated worker entry point. The
production composition must not gain a test switch or fallback constructor.
The recorded provider opens exact ART-granted documents and returns the existing
closed proposal schema; production owners perform compilation/finalization.
Public reads supply every manager decision target. PRE approval and POST
approval remain separate; Finance publishes ContributionPolicy through its
public owner and PM activates the exact context. Existing downstream public
claim, preparation, submission, selected POST, retry/replay and outcome proof
remain authoritative.

Use read-only database observations to prove complete lineage and no premature
or duplicate effects. An optional provider suggestion is advisory; a required
unsupported capability cannot silently disappear or authorize activation.
Insufficient source and provider failure must remain distinct. Prefer existing
owner tests for already-proven negative boundaries, adding only missing
connected proof and regressions for discovered defects.

## Acceptance criteria

- [ ] Original guide upload and task examples drive real async setup; no direct
  compiled/approved/active row insertion supplies the public journey.
- [ ] Setup stops at proposal; independent public PM PRE/POST approvals and
  Finance publication precede exact public activation, including replay.
- [ ] Source document, setup/proposal, policies, activation, Task, Submission,
  checker and outcome identifiers/hashes form one exact retained lineage.
- [ ] Default true reaches `review_pending` without acceptance/economic facts;
  false reaches exactly one shared FinalAcceptance and submitter contribution
  with the applicable awards, no fabricated Review/reviewer contribution.
- [ ] Insufficient source, provider failure, required unsupported capability,
  correction, stale completion, cross-project access and replay have explicit
  authoritative proof; new integration defects have discriminating regressions.
- [ ] Real runtime cleanup releases every owned database, storage prefix,
  scratch area, worker, broker and subprocess; failure is bounded and reported.

## Risk and review routing

- Risk class: L1, cross-owner integration proof using real policy/AUTH/runtime.
- Required reviewers: architecture/security; QA/test_delta; documentation and
  product_ops for source-to-outcome scope and claims. CI integrity only if an
  actual gate change becomes necessary (not currently allowed).
- Human review focus: no fixture shortcut, real async execution, exact locked
  lineage, independent approvals, realistic outcome proof and honest limits.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Existing shortcut identified | `_one_mode` and guide API drills inspected | Confirmed | Public composition not yet run |
| Connected journey | Updated isolated public journey invocation (to be recorded) | Planned | No hosted Flow/S3/gVisor or live model claim |
| Failure boundaries | Existing owner tests plus focused new drill tests | Planned | Map exact nodes during implementation |
| Repository integrity | Lint, boundaries, links, Commitrail, full hosted CI | Planned | No sampling or weakened gates |

## Reconciliation

- Current-source reconciliation: #550 merged at main `82a46ff3c`; its manifest
  renewal and replay guarantees remain unchanged. Parallel #565/#497 own their
  separate branches and PRs; existing CLI agent owns #499.
- Next usable boundary: #555 hosted operation and pilot after connected proof.
- Remaining risks: Recorded inference proves integration, not model quality;
  local identity, MinIO and development container isolation are not deployment.
