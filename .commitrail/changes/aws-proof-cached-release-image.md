# Run recurring AWS verification from the cached immutable release image

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: Recurring hosted AWS proof jobs run the selected digest-pinned release image without depending on registry login freshness.

## Intent and observed defect

The deployed pilot's scheduled verification stopped after its ECR authorization expired. The application containers remained healthy, but the required AWS activation evidence became stale. `deploy/hosted/compose.yml` gives backend services `pull_policy: always`; `run_proof_group` in `deploy/hosted/preflight.py` inherits that policy for each short-lived proof container. Thus even a locally cached exact release image causes registry authentication before verification starts.

## Bounded change and design

Allowed files: this record, `deploy/hosted/preflight.py`, `scripts/test_hosted_release_config.py`, and `deploy/hosted/README.md`.

Pass `--pull never` only to the fixed proof-group Compose run command. Docker must use the selected immutable image already present on the release host. A missing image must fail the group before subsequent identities/coordinator execute. Keep explicit authenticated release pulls and deployment policy unchanged. Do not add a token-renewal subsystem or widen IAM permissions to support a recurring image pull that this operation does not need.

Prohibited: changes to AWS role separation, proof freshness/activation criteria, image digest validation, credentials, timers, timeout/cleanup bounds, application behavior, CI selection/workflows, or other agents' POST/model-runtime work. No tags, alternate image, implicit pull or credential fallback when the selected image is absent.

## Plan and acceptance

1. Review the bounded command change against image identity and proof custody.
2. Add the fixed no-pull argument; preserve identity order, exact-container cleanup and failure propagation.
3. Extend existing proof-command coverage for every identity and coordinator. Add a missing-image failure regression proving later steps do not execute. Deliberately remove no-pull behavior and prove the new assertion fails.
4. With real Docker Compose on the pilot host, reproduce expired-registry rejection with the cached digest, prove the corrected command executes without registry credentials, and prove an uncached digest fails. Use networkless smoke containers with no product secrets; remove only those owned containers.
5. Run a real AWS verification group and confirm current activation. Do not count a temporary login refresh as the durable fix.
6. Run existing hosted configuration tests, applicable gates and internal reviews, then prepare one PR for human merge.

## Risk and review routing

Risk: L1, bounded deployment/verification reliability. Review tracks: security/architecture for cached immutable identity and role boundaries; QA/test-delta for failure discrimination; documentation for operational claims. CI-integrity assessment covers unchanged test/gate selection; no CI changes are planned.
Human focus: a cached digest is the same reviewed release identity; absence fails closed. Registry authentication is still required to acquire release images. This does not extend the validity of old AWS proofs or bypass activation.

## Roadmap assessment

The roadmap already retains live AWS activation and the connected hosted journey as outstanding release evidence. This repair changes neither capability exposure nor the release sequence; no no-op capability-ledger edit is needed. Issue #582 and parent #555 retain the observed operational failure and recovery evidence.

## Evidence

Execution and review results belong in the PR trust summary. The complete hosted ZIP-to-contribution journey and other agents' POST implementations are outside this correction.
