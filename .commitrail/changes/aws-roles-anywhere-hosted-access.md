# AWS Roles Anywhere — unattended artifact access on an external host

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: the existing native AWS artifact adapter and hosted Linux release can authenticate through dedicated certificate identities without EC2 or interactive login; live AWS activation remains a deployment prerequisite.

## Intent

The first realistic contribution drill needs the existing S3 bucket from a host
chosen independently of AWS compute. The user selected IAM Roles Anywhere and
has no existing application CA. Supply one supported external-host path, its
provisioning instructions and proof; do not require an IAM application user or
permanent AWS keys. Preserve the first automated contribution journey.

## Starting behavior

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
- Existing AWS proof/activation command, ART models, activation owner, Alembic
  environment and a new linear migration extending both proof and activation
  rows with exact Roles Anywhere anchor/profile identities and state digests.
  Associated schema fingerprint and migration regressions are included.
- `backend/tests/test_aws_*.py`, affected config/storage tests and focused new
  Roles Anywhere tests; test allocation/ownership inventories only as required.
- `docker/backend/Dockerfile.release`, its release entrypoint, `deploy/hosted/`,
  the existing release-environment loader, related image/config tests,
  `backend/scripts/aws_roles_anywhere_config.py`, `backend/.env.example`,
  artifact/deployment operator documentation, the canonical artifact-storage
  specification, README setup navigation, affected roadmap statements, and this record.
- Focused consumer composition tests and necessary exact-custody fixture
  extensions for assigned guide access; no product route or permission changes.
- Existing ART worker composition in `backend/app/adapters/artifacts/__init__.py`
  and `internal_workers.py`, plus affected guide/post-submit composition tests,
  to retain loop-owned activation database custody throughout provider use.

### Not allowed

- Product lifecycle, authorization permissions, artifact bytes/namespace semantics,
  checker execution semantics, compensation, CLI or unrelated cleanup changes.
- Static AWS access-key fallback, ambient credential discovery, arbitrary shell
  commands, metadata-service fallback, shared runtime/proof identities, weakened
  bucket policy or activation checks, manually forged passing probe evidence.
- Committed credentials or certificates, paid CA creation, deletion of retained
  data, or claims of live AWS proof from fakes. The user has separately authorized
  the exact pilot AWS setup and live checks; private provisioning evidence stays
  outside the repository and does not imply hosted journey completion.

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
- The user selected same-server administrative CA custody for this pilot instead
  of requiring a separate offline machine. Use an administrator-only directory,
  an encrypted signing key, a passphrase retained outside the host/application,
  and an encrypted off-server backup of the key and signing database. Only
  distinct leaf identities reach the runtime, readiness and denial-test jobs.
  The CA key is never mounted into containers. This trusts host administrators
  and the privileged checker controller; it is not offline or host-compromise
  isolation. Renewal/revocation remain explicit; generated test certificates do
  not stand in for provisioned identities.
- The user selected an existing IAM administrator user that is independently
  authorized for ECR publication as the provisioning identity. Preserve its
  independently authorized existing permissions, including ECR access, in one
  combined administrator policy and merge only the three exact-resource Roles
  Anywhere completion grants. Keep setup grants needed during provisioning; its
  later cleanup removes only Workstream grants that are no longer needed. A
  dedicated temporary identity remains supported and can be retired after setup.
  No administrator access key or policy is an application credential; runtime
  processes continue to use only the restricted certificate roles.
- Readiness validates enabled trust-anchor/profile resources, expected CA
  certificate identity, exact allowed roles and a closed trust shape bound to
  account, anchor, issuer and distinct exact subject common names. Bind these
  facts to four explicit fields on both probe and activation records:
  `roles_anywhere_trust_anchor_arn`, `roles_anywhere_trust_anchor_sha256`,
  `roles_anywhere_profile_arn`, `roles_anywhere_profile_sha256`. All four are
  absent for existing independent credential methods, or all present for this
  method. Canonical digests cover enabled anchor CA source and enabled profile
  role/duration/session-policy/attribute-mapping state; resource ARNs alone are
  insufficient because resources are mutable. Extend the existing immutable
  guards, exact group matching, coordinator filters and runtime filters. Do not
  overload release or IAM trust-policy digests. Extend the readiness role only
  with narrowly scoped necessary read actions. Each proof identity must also
  prove that its certificate is denied assumption of both other roles; network,
  certificate, helper or timeout errors do not count as authorization denial.
  The pinned helper exposes an AWS error-code token, not an HTTP status:
  require the exact `AccessDeniedException` token for each wrong-role attempt,
  bracketed by successful own-role credential acquisition, within a bounded
  probe window. Never enable debug or retain raw stderr; no second signer.
- The hosted Linux/Docker profile uses certificate mounts and the official
  helper. No EC2 metadata dependency. Separate proof jobs receive only their
  own identity; runtime never receives readiness/negative keys or CA signing key.
  Beat schedules work with database/broker access and receives no certificate
  or private key. A proof command explicitly binds its selected role to its
  probe mode; the application session factory remains runtime-only by default.
  The hosted profile rejects inherited volumes and Compose configs across all
  services, retaining exact configured direct-volume and secret-source inventories.
  Private inputs remain outside shared roots and cannot alias each other's files.
- Generate configuration digests and policy templates from the same canonical
  validation helpers. Operator configuration should be a small input document
  plus certificate paths, not hand-computed hashes or parallel policy logic.
- Keep current three-identity activation and immutable bucket policy. A live
  scheduled proof group remains required; update deployment instructions for
  external-host execution rather than leaving an EC2-only prerequisite.

## Acceptance criteria

- [x] Readiness accepts the actual AWS AES256 encryption response with its
  optional boolean bucket-key flag and exact customer-key block, without
  changing bucket controls. KMS, unknown fields, malformed flags and unsupported
  blocked-type structures remain rejected; the live-response regression must
  fail against the prior validator.
- [x] Setup-agent document reads and post-submit materialization retain the
  existing worker activation context until provider use and cleanup finish.
  Exercise the production composition with the real activation guard; missing
  or expired activation must still deny. A regression must detect removal of
  the operation's database scope, including after cached runtime initialization.
- [x] Explicit Roles Anywhere settings construct only that credential provider;
  absent/mixed/foreign configuration rejects before helper or cloud I/O.
- [x] Valid helper output yields refreshable credentials; malformed, expired,
  oversized, failed, hanging or cancelled execution rejects safely with no
  secrets retained in error/log text and no lingering owned process.
- [x] Certificate identity cannot assume another of the three roles. Closed
  trust, account/region/anchor/profile substitutions and broad trust reject;
  readiness/negative roles still cannot access artifact content.
- [x] Existing activation evidence cannot authorize changed Roles Anywhere
  security bindings; identity changes require matching fresh proof.
- [x] Hosted configuration mounts only the intended certificate/key, rejects
  unsafe mounts/modes and unavailable helper, and works without EC2 metadata.
- [x] A reproducible provisioning guide covers administrator-managed CA custody, separate
  certificates/roles, renewable sessions, certificate renewal, revocation,
  three proof jobs and retained-data restrictions.
- [x] An integrated proof exercises upload, exact verified read-back/download
  and the setup agent opening only its assigned guide documents through the
  selected provider; retained bytes and hashes match. The real AWS execution
  of this journey is separately pending persisted activation and public workflow
  execution; the real certificate identities are provisioned.
- [x] Existing AWS/MinIO, settings, release and activation regressions pass.
  Real helper/local process tests remain distinct from real AWS diagnostics and
  the still-outstanding public ZIP custody proof.

## Risk and review routing

- Risk class: L1 (bounded cloud credential and deployment security).
- Required reviewers: plan security/architecture; implementation security,
  architecture/reuse, QA/test-delta, deployment CI integrity and documentation.
- Human review focus: host credential custody, CA operations, exact-role
  separation, no ambient fallback, proof coverage versus real AWS evidence.

This exceeds the usual L1 size guideline because one usable credential path
requires the existing activation schema, release image, isolated proof jobs and
operator configuration to agree. The user explicitly requested this complete
S3 integration in one PR. Review is divided by those existing owners; no new
product lifecycle or alternative storage subsystem is introduced.

## Evidence

| Claim | Command or proof | Result | Remaining uncertainty |
|---|---|---|---|
| Credential/configuration/proof contracts | focused credential, settings, proof, activation and lane suite | initial 484 passed; 330 affected credential/configuration/proof-command tests passed after repairs | overlapping counts; no live AWS authorization claim |
| Immutable activation and terminal custody | isolated PostgreSQL activation and terminal regressions; focused null-field discriminator | 38 passed plus focused discriminator | hosted complete-suite evidence remains separate |
| Retained-data migration | separate-invocation predecessor upgrade and targeted downgrade refusal | passed; isolated database cleanup confirmed | no production migration executed |
| S3 consumer composition | real helper subprocess, actual SDK signing and loopback HTTP with isolated PostgreSQL | exact sealed upload/readback, refreshed credentials, scoped guide access and scratch cleanup passed | loopback transport does not prove AWS policy enforcement |
| Hosted configuration | generator/normalizer and release configuration/image-contract tests | 24 affected release configuration tests passed after exact-file-custody repairs; earlier 14 image-contract tests and candidate release image build passed | repaired-head image build and real deployment remain separate |
| Owner boundaries | architecture and authorization boundary tests | 127 passed locally | no new storage owner or public route |
| Existing public guide integration | isolated PostgreSQL/MinIO batch | earlier local run timed out after 900 seconds; cleanup confirmed; not credited as a pass | full regression execution subsequently passed in the hosted row below |
| Complete regression execution | hosted aggregate evidence for candidate `f1e6750fd` | 10,351 unique tests completed, zero skipped/deselected; all 16 lanes record cleanup; tested merge tree equals candidate tree | later live-discovered repairs require fresh complete execution |
| Current AWS encryption response | actual-response readiness regression, negative structure cases and full proof-transport module | reproduced prior validator rejection; repaired module passes 60 tests | local response contracts alone do not prove AWS enforcement |
| Cached worker activation custody | real-PostgreSQL guide/post-submit matrix covering valid, missing, expired, exception and cancellation paths | 10 cases passed on `5dadbba49`; removing the database scope makes both consumer regressions fail; isolated cleanup confirmed | transport shells isolate composition; these tests do not replace live AWS or the public journey |
| Reconciled migration chain | exact-head graph, immediate-predecessor upgrade and retained-proof/downgrade regressions | 3 passed on `5dadbba49`; chain reaches `0057_roles_anywhere_custody`; isolated cleanup confirmed | no deployed database migration claimed |
| Real AWS connection | provisioned certificate identities running the production native-AWS observation owner in isolated containers | runtime immutable upload/exact readback, readiness controls and analyzer checks, negative/anonymous object denial, and all three certificate-role separation checks pass | diagnostic observations do not create database activation or establish the public guide/Submission journey; retained challenge bytes are not deleted |
| Database-backed live AWS proof attempt | exact-source, separate-role containers and canonical proof recorder against isolated PostgreSQL | all three observations passed and persisted; coordinator rejected activation; the cold-container sequence exceeded the fixed freshness allowance | not a passing activation; preserve the rejection and measure a viable deployment sequence without relaxing freshness; temporary database cleanup confirmed |

## Review findings

Initial security/architecture inspection identified that existing release and
IAM trust digests cannot bind mutable CA/profile state. The design now includes
explicit persistent bindings and the complete cross-role denial matrix. Final
plan security/architecture review passed against clean head `574746155`;
implementation and live deployment evidence remain separate requirements.

Implementation review found that proof jobs were incorrectly constructed through
the runtime-only session default, generator ARN validation differed from Settings,
and Beat received an unnecessary private key. The repairs bind production proof
construction to its exact mode, share canonical resource validation, and remove
Beat's identity mounts. Command-level role-selection tests, generator-to-Settings
round trips, and rendered-topology counterexamples protect those boundaries.
Helper download/runtime/verifier hashes also have a shared parity regression.
Actual Compose rendering regressions cover inherited API volumes, configs,
unexpected direct mounts and substituted secret sources. Exact source inventories
replace the partial mount checks. Host validation also rejects private files
under shared scratch/socket roots and inode aliases across configured private
inputs; these controls preserve role separation across the supported file paths.
The provisioning instructions create untagged resources before an administrator
adds exact returned-resource permissions to the combined policy. Needed setup
grants remain through provisioning; later cleanup removes only obsolete
Workstream grants and preserves independently authorized permissions, including
ECR. Only a dedicated temporary setup identity is retired after provisioning.
The user selected same-server administrative certificate signing. Its encrypted
key, terminal-only passphrase, exclusive signing lock and encrypted off-server
backup replace the separate-offline-machine prerequisite without changing
application credential mounts, trust checks or runtime authorization.

## Reconciliation

- Current-source reconciliation: preserve main `b1da3f8eb`'s manager-authored
  guide runtime, guide-first intake, CLI/MCP operations and checker-image
  publishing. Chain the AWS custody migration after the manager-authored runtime
  migration; retain both ownership inventories and test-family allocations.
- Next usable boundary: persist fresh live AWS activation and run
  the public contribution drill tracked by #582/#555.
- Remaining risks: certificate signing-key custody and renewal are operational
  responsibilities; passing cloud diagnostics do not establish deployed product
  custody, recovery, or the hosted journey.
