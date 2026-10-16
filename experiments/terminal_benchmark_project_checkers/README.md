# Terminal benchmark project-checker runtime proof

This experiment supplies the real Docker/gVisor evidence required by the
bounded WS493 checker change. The pull-request workflow is the supported proof
environment: it creates an owned XFS project-quota backing file, starts the
trusted networkless DIND harness, registers the pinned `runsc` runtime, builds
the checker from the exact pull-request head, and runs only the public
`ledger-reconcile` package.

The matrix first pauses the trusted Docker wrapper after a labeled builder has
been created and inspected but before the wrapper returns to the Rust service.
It kills only the recorded service PID, observes adapter failure and live ART
workspace unwind, releases the wrapper, and verifies restart cleanup without
removing an unowned control. A second request must build successfully, reject
the unchanged starter with exit 1, and pass three fresh reference containers
with stable observations.

Preparation is the only phase that uses external networking. DIND and all
product sandboxes are externally networkless during execution. Builder and
oracle continuation containers use `--pull=never --network none`; every
product container receives no Docker socket and is inspected for the fixed
runtime, user, capabilities, root mode and mounts. The host shell makes no
offline claim.

The workflow also proves the production 384 MiB writable-layer option on the
owned XFS backing store: an allocated and fsynced 320 MiB write succeeds and an
allocated 400 MiB write fails. It stages only the fixed nonsecret evidence
allowlist through no-follow file descriptors. Cleanup removes the exact DIND
and checker image, unmounts XFS, detaches the loop device, deletes raw state,
and adds a verified cleanup receipt before upload.

The verifier tests require no Docker resources:

```bash
cd experiments/terminal_benchmark_project_checkers
python3 -m unittest -q test_verify_evidence
```

Do not run `proof.sh` on a shared development host. It is intentionally bound
to an ephemeral `ubuntu-24.04` GitHub runner with the resource and timeout
ceilings in `.github/workflows/terminal-benchmark-project-checkers.yml`. The
result is development evidence for the image and service. It is not hosted
deployment or registry-activation evidence.
