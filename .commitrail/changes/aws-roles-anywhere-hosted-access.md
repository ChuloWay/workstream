# AWS Roles Anywhere — unattended artifact access on an external host

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: the existing native AWS artifact adapter and hosted Linux release can authenticate through dedicated certificate identities without EC2 or interactive login; live AWS activation remains a deployment prerequisite.

## Intent

The first realistic contribution drill needs the existing S3 bucket from a host
chosen independently of AWS compute. The user selected IAM Roles Anywhere and
has no existing application CA. Supply one supported external-host path, its
provisioning instructions and proof; do not require an IAM application user or
permanent AWS keys. Preserve the first automated contribution journey.

## Current behavior

`backend/app/adapters/artifacts/s3_compatible.py` installs an isolated credential
resolver for one selected workload identity. `aws_live_proof.py` verifies exact
three-role trust/policy and bucket custody. `deploy/hosted/preflight.py` only
accepts EC2 instance-role authentication. `provider_activation.py` already owns
short-lived database activation; no proof bypass or new storage owner is needed.

## Bounded change

### Allowed

- `backend/app/core/config.py` and a focused pure configuration helper if needed.
- `backend/app/adapters/artifacts/{s3_compatible,aws_live_proof,aws_roles_anywhere}.py`
  and a focused shared certificate/trust validation helper in this adapter owner.
- Existing AWS proof/activation command and owner only where required to bind
  the new configuration to existing activation evidence; a migration only if
  review demonstrates existing custody cannot bind the new security facts.
- `backend/tests/test_aws_*.py`, affected config/storage tests and focused new
  Roles Anywhere tests; test allocation/ownership inventories only as required.
- `docker/backend/Dockerfile.release`, `deploy/hosted/`, related image/config
  tests, `backend/.env.example`, artifact/deployment operator documentation,
  affected roadmap statements, and this record.

### Not allowed

- Product lifecycle, authorization permissions, artifact bytes/namespace semantics,
  checker execution semantics, compensation, CLI or unrelated cleanup changes.
- Static AWS access-key fallback, ambient credential discovery, arbitrary shell
  commands, metadata-service fallback, shared runtime/proof identities, weakened
  bucket policy or activation checks, manually forged passing probe evidence.
- Committed credentials or certificates, live resource provisioning, paid CA
  creation, deletion of retained data, or claims of live AWS proof from fakes.

## Design and decisions

- Extend the selected-method contract with `roles-anywhere`; keep one S3 adapter
  and one explicitly selected credential provider. Preserve independently valid
  OIDC/EC2 methods rather than treating supported hosting choices as compatibility.
- Use the official, version/hash-pinned `aws_signing_helper` at a fixed installed
  path through an isolated async credential provider. Invoke a fixed argv (no
  shell, arbitrary credential_process config or ambient AWS profile); enforce
  bounded output, execution time, cancellation cleanup and sanitized failures.
  SDK temporary credentials refresh without writing session keys to disk.
- Configuration identifies an exact trust anchor, Roles Anywhere profile and
  selected role, plus certificate/private-key file paths. The configured role
  must be one of the existing three roles; hosted application processes use
  only the runtime role. Files must be regular, privately mounted, owned by the
  workload and unreadable to other users. Never print helper output or keys.
- A pilot uses one dedicated offline CA and distinct leaf certificates for the
  runtime, readiness and denial-test identities. Its signing key is never in
  application containers. Provide explicit renewal/revocation instructions;
  local generated test certificates do not stand in for provisioned identities.
- Readiness validates enabled trust-anchor/profile resources, expected CA
  certificate identity, exact allowed roles and a closed trust shape bound to
  account, anchor, issuer and distinct exact subject common names. Bind these
  facts to the existing release/activation contract before permitting access.
  Extend the readiness role only with narrowly scoped necessary read actions.
- The hosted Linux/Docker profile uses certificate mounts and the official
  helper. No EC2 metadata dependency. Separate proof jobs receive only their
  own identity; runtime never receives readiness/negative keys or CA signing key.
- Keep current three-identity activation and immutable bucket policy. A live
  scheduled proof group remains required; update deployment instructions for
  external-host execution rather than leaving an EC2-only prerequisite.

## Acceptance criteria

- [ ] Explicit Roles Anywhere settings construct only that credential provider;
  absent/mixed/foreign configuration rejects before helper or cloud I/O.
- [ ] Valid helper output yields refreshable credentials; malformed, expired,
  oversized, failed, hanging or cancelled execution rejects safely with no
  secrets retained in error/log text and no lingering owned process.
- [ ] Certificate identity cannot assume another of the three roles. Closed
  trust, account/region/anchor/profile substitutions and broad trust reject;
  readiness/negative roles still cannot access artifact content.
- [ ] Existing activation evidence cannot authorize changed Roles Anywhere
  security bindings; identity changes require matching fresh proof.
- [ ] Hosted configuration mounts only the intended certificate/key, rejects
  unsafe mounts/modes and unavailable helper, and works without EC2 metadata.
- [ ] A reproducible provisioning guide covers offline CA custody, separate
  certificates/roles, renewable sessions, certificate renewal, revocation,
  three proof jobs and retained-data restrictions.
- [ ] Existing AWS/MinIO, settings, release and activation regressions pass.
  Real helper/local process tests are distinguished from unexecuted live AWS
  trust, permission and ZIP custody proof.

## Risk and review routing

- Risk class: L1 (bounded cloud credential and deployment security).
- Required reviewers: plan security/architecture; implementation security,
  architecture/reuse, QA/test-delta, deployment CI integrity and documentation.
- Human review focus: host credential custody, CA operations, exact-role
  separation, no ambient fallback, proof coverage versus real AWS evidence.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Current owner gap | inspect native AWS credential resolver, live proof and hosted preflight | EC2-only hosted topology; Roles Anywhere absent | integration implementation pending |
| New behavior | focused configuration/provider/trust tests and hosted release tests (to implement) | pending | local tests cannot prove AWS enforcement |
| Real pilot | provision three identities, run existing proof modes, then public ZIP contribution drill | pending | AWS resources and certificates not provisioned |

## Review findings

Plan review precedes implementation. Record material findings and repairs here.

## Reconciliation

- Current-source reconciliation: based on main `c59230613`; open PRs concern CLI
  and deferred contributor leases, not this adapter/deployment boundary.
- Next usable boundary: provision identities and run live AWS activation and
  the public contribution drill tracked by #582/#555.
- Remaining risks: certificate signing-key custody and renewal are operational
  responsibilities; no live AWS claim can be made without real provisioning.
