# Hosted drill identity fixture

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: A separate, explicitly simulated issuer can supply short-lived identities to the existing Flow verifier during an isolated hosted drill.

## Intent

The operator needs tokens for the first hosted contribution journey without
making Workstream a login or token-issuance product. The actual Flow issuance
service and its credentials are unavailable in the inspected deployment inputs.
`backend/scripts/local_flow_tokens.py` signs local-only HMAC tokens; it cannot
exercise production asymmetric verification. `backend/app/adapters/auth/flow.py`
already verifies asymmetric tokens through HTTPS JWKS. Existing authentication
tests supply their own RSA keys with mocked HTTP transports.

## Bounded change

Allowed: this record and `experiments/hosted_drill_identity/` containing the
operator-only fixture, focused tests, and instructions. Private generated keys,
tokens, TLS certificates and operation records stay outside the checkout.

Not allowed: production auth adapter changes, a Workstream login/token endpoint,
HMAC in a hosted profile, disabled TLS verification, new actor admission mechanisms or
role grants, changes to Flow Node, deployment of a publicly accessible minting
service, or a claim of actual Flow Identity interoperability. No existing test or
auth path is removed: local HMAC remains a separately scoped existing local-test
facility, not a fallback selected by this fixture.

## Design and plan

1. Use a fixed reserved drill issuer and audience. Generate an isolated RSA
   signing key and separate TLS material into a new private directory. Use
   locked existing PyJWT/cryptography dependencies, not a new auth framework.
2. Mint bounded, short-lived human identity tokens offline to exclusive
   private files. Bind identities to a small explicit inventory; no role claims
   or arbitrary claim overrides. Reject unsafe output and key files.
3. Serve only public JWKS over TLS on an isolated Docker network. That process
   receives public JWKS plus its TLS leaf key, never the token-signing key.
   The drill clients explicitly trust the added drill CA alongside their
   ordinary trust bundle; production verifier code remains unchanged. Its
   `trust_env=False` means `SSL_CERT_FILE` is not sufficient. The private drill
   composition mounts the combined public bundle at the actual image's
   `certifi.where()` path. No global trust-store edit or production Compose
   change is implied; this is an explicit fixture composition.
4. Exercise the actual Flow verifier across real HTTPS, including incorrect
   signature, issuer, audience, expired tokens and wrong scopes. Confirm TLS
   failure without the CA and denial before issuer key substitution is trusted.
5. Generate the drill identities and verify their tokens on the dedicated host.
   Public actor admission, bootstrap and grants remain the existing operations.

### Exact fixture boundary

Issuer: `https://flow-drill.test:8443`; audience: `workstream-drill`;
algorithm: `RS256`; key ID: SHA-256 of DER SubjectPublicKeyInfo. Named human
inventory: access-admin, manager, finance, operator, contributor,
foreign-contributor. Subjects are persisted random UUIDs; `subject_kind=human`
and scope is exactly `workstream:access`. Tokens last 900 seconds, with configured
clock skew of zero. Each issuance generates a fresh UUID `jti`. The tool does not
accept arbitrary claims or a custom lifetime.

The signing-key custodian can sign other subjects outside this tool: the inventory
limits the tool, not the verifier's trust in that key. Tokens are replayable until
expiry. Introspection is disabled with reason `isolated simulated issuer drill;
short-lived tokens; no revocation proof`. No revocation or real Flow integration
is claimed. Raw JWTs never enter argv, stdout, stderr, logs or evidence. Remove
retained token files after the drill.

The JWKS service publishes no host port and serves one fixed public JSON value,
not a directory. TLS keys are separate from public JWKS; the JWT signing key is
never mounted in server or application containers. Only the experiment uses the
combined CA bundle. No host trust-store or release composition is changed.
Negative proof uses test-only service tokens and role-like claims: unprovisioned
service identities stay denied and token claims create no role grants. Existing
actor admission tests remain authoritative; the hosted drill records first-access
admission and absence of grants before explicit bootstrap/grant operations.

## Acceptance criteria

- The existing verifier accepts generated human tokens using actual TLS
  and JWKS, without a mock transport, development verifier, or verification bypass.
- Tokens contain `iss`, `sub`, `aud`, `iat`, `nbf`, `exp`, unique `jti`,
  `subject_kind` and `scope` only. Verification grants no project role. Existing
  first-access human admission still creates an active actor and identity link;
  the fixture adds no admission or grant mechanism.
- Private key/token contents never appear in stdout, errors, Git or web responses.
- Serving JWKS needs no signing key; unknown routes and methods cannot mint tokens.
- Invalid signature, issuer, audience, lifetime, scope and untrusted TLS reject.
- Keys and tokens use private regular files, exclusive creation and no symlinks;
  repeated issuance does not silently replace retained token files.
- Evidence calls this a simulated issuer and does not close real Flow integration.

## Risk and review routing

- Risk class: L1, bounded authentication drill tooling.
- Required reviewers: plan/security; architecture/reuse; QA/test delta.
- Human focus: the fixture is a substitute issuer for isolated testing only.
- Verification: focused unit tests and real HTTPS verification with the existing
  backend image, then isolated host evidence with no raw tokens recorded.
- Roadmap impact: no product capability or public exposure changes. Actual Flow
  integration and the complete hosted contribution drill remain unproven.

## Evidence

Inspected current main `a82f0d45e`; no deployed Flow issuance contract was found
in Workstream inputs. The sibling Flow Node exposes a different DID/WebAuthn
contract and is not silently treated as this JWT issuer. Next boundary is the
public hosted journey using clearly identified drill identities, followed by
actual external issuer integration when its supported configuration exists.

Local verification exercises actual HTTPS using the unchanged verifier, with no
mock transport. Regressions distinguish invalid credentials from issuer outages,
require distinct fixture subjects, reject unsafe output parents, and reject
private JWK fields. Review clarified that first-access admission is retained and
that tool inventory is not a verifier-enforced subject allowlist. The release
image requires an explicit experiment-script mount; it does not include this
fixture. Remote proof is recorded privately and remains distinct from public
journey completion or real Flow interoperability.
