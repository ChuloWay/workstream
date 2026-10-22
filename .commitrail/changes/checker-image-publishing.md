# Checker image publishing — test once and publish the same image

- Initiative: `None`
- Durable disposition: `Complete`
- Intended merge outcome: Give engineering one generic command to build, test and publish a project-owned checker image to private ECR and produce exact registration/cache inputs.

## Intent

Each project owns its checker source, dependencies and samples. Engineering can
prepare an image without modifying Workstream or the shared Rust service. One
command should make the tested image's identity and next operator steps clear.

## Current behavior

The shared service accepts cached platform manifests and the CHECKERS public
Python contracts validate request/result identities. The opt-in Harnessy proof
has its own loopback publisher; there is no generic project image publishing
command. Registration and approved policy binding remain separate operations.

## Bounded change

### Allowed

- `scripts/checker-image`, `backend/scripts/checker_image*.py`: generic developer
  command, project sample validation, bounded container execution, ECR publishing.
- `.gitignore`: generated local publishing outputs.
- Focused script tests and their existing CI selection where needed.
- `backend/scripts/test_lane_catalogue.py`: select the new script regression file.
- `backend/scripts/behavior_ownership.py` and its partition: register exactly the
  three added script targets under the existing ownership rules.
- `external_checkers/README.md`, engineering runbook, affected roadmap claims,
  and this record.

### Not allowed

- No project rules in the shared Rust service; no new runtime or builder service.
- No database, migration, authorization, policy, lifecycle or registry mutation.
- No automatic project activation, deployment or credentials written to outputs.
- No cloud account/repository creation without the user's selected destination.
- No removal of existing runtime proofs or weakening CI.

## Design and decisions

Use a project-owned descriptor beside its Dockerfile, with explicit capability,
schemas, finite resources and positive/negative samples. Reuse CHECKERS public
contract validation. Test the immutable built image ID in a networkless,
non-root, read-only container with bounded resources. Local `docker-dev` proof
must be identified as such; gVisor must be selected explicitly for that claim.
Publish that same image, verify ECR's exact platform manifest and configuration
identity, and emit the digest, registry body and runner cache entry. Publishing
never registers or changes policy. Dry run performs no AWS calls.

## Acceptance criteria

- [x] One command builds once, tests project-owned passing/failing samples and publishes only after success.
- [x] Dry run needs no AWS or Workstream API/database and identifies its isolation profile.
- [x] Wrong verdict, invalid output, timeout and failed cleanup prevent publication.
- [x] Samples are read-only; no network, host socket, root or host credentials reach the checker.
- [x] Published manifest/config identity matches the tested image; outputs use a platform digest, never a tag or image index.
- [x] Errors and outputs do not disclose AWS credentials; failed publication reports uncertainty without an automatic retry.
- [x] Documentation explains separate runner provisioning, registry registration and policy approval.

## Risk and review routing

- Risk class: `L1`
- Required reviewers: architecture/reuse, security, QA/test delta, documentation/CI integrity.
- Human review focus: simple engineering workflow, image identity, credential isolation and honest local versus hosted proof.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Publishing and failure boundaries | `pytest -q tests/test_checker_image.py`; actual Docker sample run | 113 script, lane-catalogue and checker-contract tests passed; real positive/negative Docker samples passed; a 2,048-byte aggregate output budget correctly rejected the image | Real ECR push, raw-manifest verification, digest pull, final positive/negative samples and output generation passed in eu-north-1; gVisor is not installed on this host |
| Architecture and documentation | Public CHECKERS contracts; existing Markdown and lint checks | Public request/result validation reused; focused lint and Markdown checks passed | Independent candidate review and full hosted CI are required before merge |

Live qualification used the isolated private `workstream-checker-pre-publisher-proof`
repository. The command returned zero with `publication=verified`; its platform
manifest was `sha256:c40d539fa600395529eb9b691e18c2573ec750f286156106a9884494c45c45cc` and
configuration image was `sha256:360e2cbf91fce711ba808913f55e1d5ef38f3a38b8867966820eefa6f1d85621`.
Both original and digest-bound positive/negative samples completed. No Workstream
registration, policy, activation or runner deployment was performed. Real Docker
also proved proxy-marker isolation in build/container execution and rejection of
the undersized aggregate output limit; no owned test containers remained.

## Review findings

The design review selected a small Python engineering command that reuses public CHECKERS models. It required expected negative finding codes, explicit image-compatibility proof limits, and a second sample run using the final registry digest. Those requirements are implemented; the shared Rust runtime remains unchanged.

Candidate review also required an explicit expected AWS account, isolated Docker
client configuration, one sample-wide output/deadline budget, rejection of image
health checks, accurate preflight receipt state, and corrected CI membership and
runbook wording. These repairs are covered by discriminating regressions; a real
Docker low-budget counterexample now fails before checker execution. Builds use
locally cached or publicly pullable bases; private-base authentication is outside
this bounded command.

Live ECR qualification found that removing the last local publishing tag also
removed the verified RepoDigest and could block the final sample replay. The
publisher now retains that intended local image cache; the regression models
image removal as destructive and requires the pulled identity during final
samples. The first cloud publication was inspected by digest before the corrected
command was run again; it was never reported as qualification success. ECR then
returned multiple tag rows for that same digest. Verification now accepts only
byte-identical manifest aliases, rejects conflicting rows, and explicitly pushes
a single platform. Both real failures remained closed with no registration output.

Hosted preflight found the three new scripts missing from the separate behavior
ownership partition. The repair adds only those exact targets and their existing
artifact group, retaining the protected base and all existing assignments. The
ownership validation and its existing adversarial tests are required alongside
the script, lane and contract checks.

## Reconciliation

- Current-source reconciliation: main `9b67c8106`, including merged generic project image boundary and MCP participation tools. No overlapping open implementation PR found.
- Next usable boundary: use the resulting registered image in a separately approved project policy and live project rehearsal.
- Remaining risks: sample success is image compatibility evidence, not live ART custody, policy activation or a full project journey.
