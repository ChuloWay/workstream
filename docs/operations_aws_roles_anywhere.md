# AWS Roles Anywhere for the hosted artifact path

This guide provisions the supported external-host identity for the existing
native AWS S3 artifact adapter. It does not create a second storage adapter.
The API upload path, verified download/read-back path, and setup agent document
reads continue to use the same `ArtifactStore` configuration and private S3
namespace.

## Short operator path

The one-time path is: create the administrator-managed CA and three leaf identities, fill in
one `operator-input.json`, run the generator, apply its exact role/policy/profile
files, save the AWS trust-anchor and profile read responses, then run the same
generator for `roles-anywhere.env`. Copy that fragment into the hosted release
file and run the fixed preflight and proof commands. Every S3 consumer uses this
single release configuration. Operators do not derive policy documents, type
canonical hashes, or maintain separate upload, download, and setup-agent storage
settings.

No live AWS resources or certificates are included in the repository. Local
image, helper, configuration, and certificate-process tests are not evidence
that AWS accepted the trust or enforced the policies. Retain the AWS read
results and the later public API drill as environment evidence.

## Identity and custody layout

Use one pilot CA and exactly three leaf identities:

| Identity | Certificate subject CN | Selected role | Mounted into |
|---|---|---|---|
| runtime | exact runtime role basename | runtime role | API, Celery execution process; runtime proof job |
| readiness | exact readiness role basename | readiness role | readiness proof job only |
| negative | exact negative role basename | negative role | negative proof job only |

The CA private key, OpenSSL database, CRL signing state, readiness private key,
and negative private key must never enter the long-lived application
containers. Beat receives no certificate or private key: it schedules work using
the database and broker. The credential-free coordinator receives only the database secret.
Do not configure static AWS keys, an AWS profile, EC2 metadata, web identity, a
credential-process file, or another signing helper.

The hosted profile rejects inherited volumes (`volumes_from`) and Compose
`configs` on every service. Only the declared, validated volumes and role-specific
secrets may supply files; Beat has no host volumes. Preflight binds every mount
and secret to its configured host file. Keep certificates, keys, secrets and the
checker configuration outside the shared scratch and socket directories, with
distinct files; symlinked directory paths and hard links do not bypass these checks.

The release image installs the official `aws_signing_helper` 1.8.5 at
`/usr/local/bin/aws_signing_helper`. The Docker build and image verifier pin
these SHA-256 identities:

- x86_64: `beec9ed1c492d93db809890f16713e3556353294b823c2184ad4e891f1b2b54d`
- aarch64: `3d131aa888cd56da446f9c6bb460b1f0569f6c7edc74eae6193a2fe3928883ba`

## Build the pilot CA on the deployment server

The pilot may use the same server for administrative signing and application
execution. Keep the CA in a separate administrator-owned `0700` directory,
at a canonical absolute path outside the checkout, runtime identity directory,
secret/configuration directories, all container mounts and shared scratch/socket roots. The application UID must not own or access it.
Encrypt its signing key and keep a high-entropy passphrase in the operator's
password manager outside this host, never in a release environment, command
argument, script, log or application secret. Enter it only at OpenSSL's trusted
terminal prompt; do not capture it through an agent, script, CI or shell tracing.
The application uses its leaf key and never needs the CA passphrase.

This is administrator separation on a trusted host, not an offline CA or a
boundary against host root or Docker administrators. A compromise of the host
can expose leaf identities and capture CA material or its passphrase during signing;
encryption at rest does not protect an actively compromised signing host. Do not grant application
or checker workloads access to the CA directory; the privileged checker
controller and host administrators remain trusted infrastructure.

Start in an empty private directory on storage whose backup and recovery
procedure is tested. Keep an encrypted backup outside the server, using separate
backup encryption material. The CA
database, serial files, and `crlnumber` are durable signing state; back them up
with the encrypted CA key. A bare `openssl x509 -req` workflow is insufficient because it
does not maintain the revocation database needed to issue a CRL.

```sh
set +x
umask 077
mkdir -m 0700 workstream-ca
cd workstream-ca
exec 9>.signing.lock
flock -n 9
mkdir certs crl csr issued newcerts private
mkdir -m 0700 ../workstream-leaf-staging
touch index.txt
printf '1000\n' > serial
printf '1000\n' > crlnumber
```

Create `openssl.cnf` in that directory:

```ini
[ ca ]
default_ca = CA_default

[ CA_default ]
dir               = .
database          = $dir/index.txt
new_certs_dir     = $dir/newcerts
certificate       = $dir/certs/ca.cert.pem
serial            = $dir/serial
crlnumber         = $dir/crlnumber
private_key       = $dir/private/ca.key.pem
default_md        = sha256
default_days      = 30
default_crl_days  = 7
policy            = policy_leaf
x509_extensions   = leaf_cert
unique_subject    = no
copy_extensions   = none

[ policy_leaf ]
commonName        = supplied

[ req ]
prompt             = no
distinguished_name = ca_name
x509_extensions    = root_ca

[ ca_name ]
CN = Workstream Artifact Root CA

[ root_ca ]
basicConstraints       = critical,CA:true,pathlen:0
keyUsage               = critical,keyCertSign,cRLSign
subjectKeyIdentifier   = hash
authorityKeyIdentifier = keyid:always

[ leaf_cert ]
basicConstraints       = critical,CA:false
keyUsage               = critical,digitalSignature
extendedKeyUsage       = clientAuth
subjectKeyIdentifier   = hash
authorityKeyIdentifier = keyid:always
```

Create the encrypted CA key and ten-year pilot root. Keep the passphrase outside
shell history and logs.

```sh
openssl genpkey -algorithm RSA -aes-256-cbc \
  -pkeyopt rsa_keygen_bits:4096 -out private/ca.key.pem
chmod 0400 private/ca.key.pem
openssl req -config openssl.cnf -new -x509 -sha256 -days 3650 \
  -key private/ca.key.pem -out certs/ca.cert.pem
openssl x509 -in certs/ca.cert.pem -noout -subject -issuer -dates -text
```

For each of `runtime`, `readiness`, and `negative`, set `ROLE_BASENAME` to the
exact basename of its final IAM role ARN and issue a distinct key and leaf. Run
the commands three times; never reuse a leaf key.

```sh
IDENTITY=runtime
ROLE_BASENAME=workstream-runtime
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out "../workstream-leaf-staging/${IDENTITY}.key.pem"
openssl req -new -sha256 -key "../workstream-leaf-staging/${IDENTITY}.key.pem" \
  -subj "/CN=${ROLE_BASENAME}" -out "csr/${IDENTITY}.csr.pem"
openssl ca -batch -config openssl.cnf -extensions leaf_cert -days 30 \
  -in "csr/${IDENTITY}.csr.pem" -out "issued/${IDENTITY}.cert.pem"
openssl verify -CAfile certs/ca.cert.pem "issued/${IDENTITY}.cert.pem"
openssl x509 -in "issued/${IDENTITY}.cert.pem" -noout -subject -issuer -serial -dates
```

Hold the same `.signing.lock` for every signing, revocation, CRL and backup
operation. Before releasing it, take a consistent encrypted backup of the CA
key, configuration, index, serial, `crlnumber`, certificates and CRL state; copy
that backup off the server and test restoration into an isolated private
directory. Exclude `workstream-leaf-staging` from the CA backup. Leaf keys are
unencrypted for unattended helper use and rely on private ownership and mounts.
After the exact leaf pairs are installed and verified, remove their staging keys.

Record the certificate serial, role ARN, issuance time, expiry, custodian, and
deployment target without recording private-key bytes. Transfer the three leaf
pairs into the exact runtime-owned host files described below; use an encrypted
channel if transferring them to another host. Copy only `certs/ca.cert.pem`,
which is public, into the separate AWS provisioning directory and compare its
SHA-256 fingerprint to the original. The CA private key, database, serial files,
`crlnumber`, CSRs, and issued-certificate archive stay in the administrator-only
CA directory and its encrypted backup, never in application mounts.

## Provision the closed AWS trust

Use an authorized provisioning identity only for this section. A dedicated IAM
user with an access key is supported for this temporary setup administration;
its credentials must stay separate from the application environment. An existing
authorized provisioning role is also supported. Neither identity is a runtime
credential.

Have an account administrator grant only the actions needed for the declared
resource names. Use two stages because AWS assigns the trust-anchor and profile
IDs when creating them:

1. Allow creation of the three exact IAM roles and two exact managed policies,
   attach each policy only to its matching role, and allow `iam:PassRole` only
   for those roles with `iam:PassedToService=rolesanywhere.amazonaws.com`.
   Allow `rolesanywhere:CreateTrustAnchor` and `rolesanywhere:CreateProfile` in
   the selected region; create both resources **without tags**. Do not grant
   wildcard tag, read, or attribute-mapping access. If needed, permit creation
   of the exact Roles Anywhere service-linked role with
   `iam:AWSServiceName=rolesanywhere.amazonaws.com`. Grant the bucket-control
   reads and writes below only for the declared bucket, with no direct object
   read, write, or delete actions.
2. After both create responses supply their ARNs, have the account administrator
   replace the setup policy with exact-resource read/mapping access described
   below and `iam:CreatePolicyVersion` only for the readiness policy. The setup
   identity does not need permission to modify its own IAM policy.

This is trusted setup administration. Exact resource names do not constrain the
contents of submitted trust policies, managed policies, CA bundles, or bucket
policies. In particular, bucket-policy administration can grant data access.
Review those generated documents before applying them; do not give this setup
identity to application processes. Remove its temporary permissions and access
key after provisioning. Ongoing proof jobs use their own certificate identities.

Start from the reviewed repository root, record its absolute
path, and use one separate private provisioning directory for every command in
this section:

```sh
umask 077
WORKSTREAM_CHECKOUT=$(pwd -P)
PROVISION_DIR="$(dirname "$WORKSTREAM_CHECKOUT")/workstream-aws-provision"
mkdir -m 0700 "$PROVISION_DIR"
cd "$PROVISION_DIR"
```

Place the copied public certificate at `$PROVISION_DIR/ca.cert.pem` and
verify its fingerprint against the CA copy before continuing. No leaf private key or
other CA file belongs in this connected directory.

```sh
test -f ca.cert.pem && test ! -L ca.cert.pem
chmod 0444 ca.cert.pem
openssl x509 -in ca.cert.pem -noout -fingerprint -sha256 -subject -issuer
```

Prepare one `operator-input.json` here using the example below. Role and policy
ARNs may be declared before those resources exist. Use `PENDING` only for the
trust anchor; a command below replaces it from the AWS create response before
the generator runs. Keep `profile_arn` as `null` for the bootstrap pass. All six
certificate fields are future host paths, not certificate contents. The
generator derives the exact runtime, readiness, and bucket policies from this
one document.

```json
{
  "release_id": "sha256:<reviewed-release-digest>",
  "region": "us-east-1",
  "bucket": "workstream-artifacts-prod",
  "private_prefix": "workstream/artifacts",
  "trust_anchor_arn": "PENDING",
  "profile_arn": null,
  "roles": {
    "runtime": {
      "role_arn": "arn:aws:iam::123456789012:role/workstream-runtime",
      "policy_arn": "arn:aws:iam::123456789012:policy/workstream-runtime",
      "certificate_host_file": "/etc/workstream/roles-anywhere/runtime-certificate.pem",
      "private_key_host_file": "/etc/workstream/roles-anywhere/runtime-private-key.pem"
    },
    "readiness": {
      "role_arn": "arn:aws:iam::123456789012:role/workstream-readiness",
      "policy_arn": "arn:aws:iam::123456789012:policy/workstream-readiness",
      "certificate_host_file": "/etc/workstream/roles-anywhere/readiness-certificate.pem",
      "private_key_host_file": "/etc/workstream/roles-anywhere/readiness-private-key.pem"
    },
    "negative": {
      "role_arn": "arn:aws:iam::123456789012:role/workstream-negative",
      "certificate_host_file": "/etc/workstream/roles-anywhere/negative-certificate.pem",
      "private_key_host_file": "/etc/workstream/roles-anywhere/negative-private-key.pem"
    }
  },
  "bootstrap_principal_arn": "arn:aws:iam::123456789012:user/workstream-provisioner"
}
```

Derive the shell values used below from that document rather than entering a
second copy of the settings:

```sh
AWS_REGION=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["region"])' operator-input.json)
BUCKET=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["bucket"])' operator-input.json)
RUNTIME_ROLE_NAME=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["roles"]["runtime"]["role_arn"].rsplit("/",1)[-1])' operator-input.json)
READINESS_ROLE_NAME=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["roles"]["readiness"]["role_arn"].rsplit("/",1)[-1])' operator-input.json)
NEGATIVE_ROLE_NAME=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["roles"]["negative"]["role_arn"].rsplit("/",1)[-1])' operator-input.json)
RUNTIME_POLICY_ARN=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["roles"]["runtime"]["policy_arn"])' operator-input.json)
READINESS_POLICY_ARN=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["roles"]["readiness"]["policy_arn"])' operator-input.json)
RUNTIME_POLICY_NAME=${RUNTIME_POLICY_ARN##*/}
READINESS_POLICY_NAME=${READINESS_POLICY_ARN##*/}
export AWS_REGION BUCKET RUNTIME_POLICY_ARN READINESS_POLICY_ARN
```

Create the untagged certificate-bundle trust anchor from the transferred public
CA and retain its create response. Its read response is collected after the
exact-resource permissions are installed:

```sh
python3 - ca.cert.pem > trust-anchor-input.json <<'PY'
import json, pathlib, sys
certificate = pathlib.Path(sys.argv[1]).read_text(encoding="ascii")
print(json.dumps({
    "name": "workstream-artifacts",
    "enabled": True,
    "source": {
        "sourceType": "CERTIFICATE_BUNDLE",
        "sourceData": {"x509CertificateData": certificate},
    },
}))
PY
aws rolesanywhere create-trust-anchor \
  --cli-input-json "file://${PROVISION_DIR}/trust-anchor-input.json" \
  --region "$AWS_REGION" > trust-anchor-create.json
python3 - operator-input.json trust-anchor-create.json <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
document = json.loads(path.read_text())
response = json.loads(pathlib.Path(sys.argv[2]).read_text())
document["trust_anchor_arn"] = response["trustAnchor"]["trustAnchorArn"]
path.write_text(json.dumps(document, indent=2) + "\n")
PY
TRUST_ANCHOR_ID=$(python3 -c \
  'import json; print(json.load(open("trust-anchor-create.json"))["trustAnchor"]["trustAnchorId"])')
```

Generate the role trust policies and closed profile request. This performs no
AWS calls and prints no credential or policy content:

```sh
(
  cd "$WORKSTREAM_CHECKOUT/backend"
  .venv/bin/python scripts/aws_roles_anywhere_config.py \
    --input "$PROVISION_DIR/operator-input.json" \
    --bootstrap-templates \
    --output-directory "$PROVISION_DIR/generated-bootstrap"
)
```

Review `generated-bootstrap/roles-anywhere-bootstrap-templates.json`. The
generator also writes ready-to-apply trust, identity, bucket, and profile JSON
files. Create the three roles from their matching trust file, create the two
managed policies from the exact identity files, and attach each only to its
matching role. The negative role receives no managed policy.

```sh
aws iam create-role --role-name "$RUNTIME_ROLE_NAME" \
  --assume-role-policy-document "file://${PROVISION_DIR}/generated-bootstrap/runtime-role-trust-policy.json"
aws iam create-role --role-name "$READINESS_ROLE_NAME" \
  --assume-role-policy-document "file://${PROVISION_DIR}/generated-bootstrap/readiness-role-trust-policy.json"
aws iam create-role --role-name "$NEGATIVE_ROLE_NAME" \
  --assume-role-policy-document "file://${PROVISION_DIR}/generated-bootstrap/negative-role-trust-policy.json"
aws iam create-policy --policy-name "$RUNTIME_POLICY_NAME" \
  --policy-document "file://${PROVISION_DIR}/generated-bootstrap/runtime-identity-policy.json" \
  > runtime-policy-create.json
aws iam create-policy --policy-name "$READINESS_POLICY_NAME" \
  --policy-document "file://${PROVISION_DIR}/generated-bootstrap/readiness-identity-policy.json" \
  > readiness-policy-create.json
test "$(python3 -c 'import json; print(json.load(open("runtime-policy-create.json"))["Policy"]["Arn"])')" = "$RUNTIME_POLICY_ARN"
test "$(python3 -c 'import json; print(json.load(open("readiness-policy-create.json"))["Policy"]["Arn"])')" = "$READINESS_POLICY_ARN"
aws iam attach-role-policy --role-name "$RUNTIME_ROLE_NAME" \
  --policy-arn "$RUNTIME_POLICY_ARN"
aws iam attach-role-policy --role-name "$READINESS_ROLE_NAME" \
  --policy-arn "$READINESS_POLICY_ARN"
```

The policy ARNs in `operator-input.json` must be the two ARNs returned by these
commands. Configure the dedicated bucket with versioning, bucket-owner-enforced
ownership, all four public-access blocks, default SSE-S3, and the exact generated
deny policy:

```sh
aws s3api put-bucket-versioning --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration \
BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-ownership-controls --bucket "$BUCKET" \
  --ownership-controls 'Rules=[{ObjectOwnership=BucketOwnerEnforced}]'
aws s3api put-bucket-encryption --bucket "$BUCKET" \
  --server-side-encryption-configuration \
'Rules=[{ApplyServerSideEncryptionByDefault={SSEAlgorithm=AES256}}]'
aws s3api put-bucket-policy --bucket "$BUCKET" \
  --policy "file://${PROVISION_DIR}/generated-bootstrap/bucket-policy.json"
```

Do not add an enabled lifecycle rule that can expire or delete completed objects
under the configured private prefix. The generated bucket policy permits object
data only through the runtime role and denies unconditional writes.

Create the untagged profile from `profile_create_parameters` with the three exact
role ARNs and a 3600-second duration:

```sh
aws rolesanywhere create-profile \
  --cli-input-json "file://${PROVISION_DIR}/generated-bootstrap/profile-create-parameters.json" \
  --region "$AWS_REGION" > profile-create.json
PROFILE_ID=$(python3 -c \
  'import json; print(json.load(open("profile-create.json"))["profile"]["profileId"])')
```

Before continuing, have the account administrator replace the setup policy.
Use `trustAnchor.trustAnchorArn` from `trust-anchor-create.json` for
`rolesanywhere:GetTrustAnchor`. Use `profile.profileArn` from
`profile-create.json` for `rolesanywhere:GetProfile`,
`rolesanywhere:PutAttributeMapping`, and `rolesanywhere:DeleteAttributeMapping`.
Retain only the necessary exact-role/policy read access and allow
`iam:CreatePolicyVersion` on the readiness policy alone. Remove the initial
creation, role attachment, pass-role, and bucket-administration grants. Do not
substitute wildcard resource ARNs or add tag permissions.

The profile must add only the issuer-CN and subject-CN mappings used by the
generated trust policies. Roles Anywhere may create a broader default SAN
mapping, so remove it explicitly. Collect both exact-resource read responses:

```sh
aws rolesanywhere put-attribute-mapping --profile-id "$PROFILE_ID" \
  --certificate-field x509Issuer --mapping-rules specifier=CN \
  --region "$AWS_REGION"
aws rolesanywhere put-attribute-mapping --profile-id "$PROFILE_ID" \
  --certificate-field x509Subject --mapping-rules specifier=CN \
  --region "$AWS_REGION"
aws rolesanywhere delete-attribute-mapping --profile-id "$PROFILE_ID" \
  --certificate-field x509SAN --region "$AWS_REGION"
aws rolesanywhere get-profile --profile-id "$PROFILE_ID" \
  --region "$AWS_REGION" > profile-read.json
aws rolesanywhere get-trust-anchor \
  --trust-anchor-id "$TRUST_ANCHOR_ID" --region "$AWS_REGION" \
  > trust-anchor-read.json
```

Set the real `profile_arn` from the retained create response, then generate the
final environment fragment and reviewable templates. The generator calls the
same closed normalizers as live readiness; operators never calculate
anchor/profile or policy hashes manually.

```sh
python3 - operator-input.json profile-create.json <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
document = json.loads(path.read_text())
response = json.loads(pathlib.Path(sys.argv[2]).read_text())
document["profile_arn"] = response["profile"]["profileArn"]
path.write_text(json.dumps(document, indent=2) + "\n")
PY
(
  cd "$WORKSTREAM_CHECKOUT/backend"
  .venv/bin/python scripts/aws_roles_anywhere_config.py \
    --input "$PROVISION_DIR/operator-input.json" \
    --trust-anchor-response "$PROVISION_DIR/trust-anchor-read.json" \
    --profile-response "$PROVISION_DIR/profile-read.json" \
    --output-directory "$PROVISION_DIR/generated-release"
)
```

Promote the generated final readiness policy, which adds only the exact profile
read action to the bootstrap policy. Neither the runtime nor negative role
receives either Roles Anywhere read action.

```sh
aws iam create-policy-version --policy-arn "$READINESS_POLICY_ARN" \
  --policy-document "file://${PROVISION_DIR}/generated-release/readiness-identity-policy.json" \
  --set-as-default
```

Re-read the profile and trust anchor after every resource update and rerun the
final generator into a new empty output directory before release.

Copy the generated key/value lines from
`$PROVISION_DIR/generated-release/roles-anywhere.env` into one copy of
`deploy/hosted/release.env.example`, replacing the corresponding example keys.
Do not append duplicate keys. Complete the image, Flow, database, broker,
OpenAI, checker, and timeout values described in
[`deploy/hosted/README.md`](../deploy/hosted/README.md).

## Secure host installation and proof

Create the private host directory and install the transferred leaf material as
regular runtime-owned files. Never copy the CA private key or OpenSSL database.

```sh
sudo install -d -m 0700 -o 10001 -g 10001 /etc/workstream/roles-anywhere
sudo install -m 0400 -o 10001 -g 10001 runtime.cert.pem \
  /etc/workstream/roles-anywhere/runtime-certificate.pem
sudo install -m 0400 -o 10001 -g 10001 runtime.key.pem \
  /etc/workstream/roles-anywhere/runtime-private-key.pem
sudo install -m 0400 -o 10001 -g 10001 readiness.cert.pem \
  /etc/workstream/roles-anywhere/readiness-certificate.pem
sudo install -m 0400 -o 10001 -g 10001 readiness.key.pem \
  /etc/workstream/roles-anywhere/readiness-private-key.pem
sudo install -m 0400 -o 10001 -g 10001 negative.cert.pem \
  /etc/workstream/roles-anywhere/negative-certificate.pem
sudo install -m 0400 -o 10001 -g 10001 negative.key.pem \
  /etc/workstream/roles-anywhere/negative-private-key.pem
sudo stat -Lc '%u:%g:%a %n' /etc/workstream/roles-anywhere/*.pem
```

All six lines must report the configured runtime UID/GID, mode `400`, distinct
regular files, and no symbolic links. Full preflight enforces the same custody
contract before launch or proof.

Run full preflight, then run one exact proof group. The wrapper executes runtime
immutability first, readiness second, negative access third, and the
credential-free coordinator last. Every identity proves its own credential
acquisition, both wrong-role denials, then its own credential acquisition again.
The coordinator cannot fabricate a passing observation.

```sh
python3 deploy/hosted/preflight.py --env-file /etc/workstream/release.env
GROUP_NONCE=$(python3 -c 'import uuid; print(uuid.uuid4())')
python3 deploy/hosted/compose.py --env-file /etc/workstream/release.env \
  proof --group-nonce "$GROUP_NONCE"
```

After activation, start the long-lived release and run the public backend drill:
upload a ZIP, read/download the exact retained bytes and digest, and run guide
setup so the setup agent opens only its assigned original guide documents from
the same S3 provider. Record exact release/configuration identities and bounded
results. Do not record document bytes, helper output, session credentials, or
private keys. A passing local proof is not a substitute for this AWS drill.

For continuous eligibility, install this root-owned `0555` wrapper as
`/usr/local/sbin/workstream-aws-proof` (adjust only the reviewed checkout and
environment paths):

```sh
#!/bin/sh
set -eu
nonce=$(/usr/bin/python3 -c 'import uuid; print(uuid.uuid4())')
exec /usr/bin/python3 /opt/workstream/deploy/hosted/compose.py \
  --env-file /etc/workstream/release.env proof --group-nonce "$nonce"
```

Use a oneshot unit and persistent five-minute timer:

```ini
# /etc/systemd/system/workstream-aws-proof.service
[Unit]
Description=Workstream AWS artifact proof group
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
User=root
WorkingDirectory=/opt/workstream
ExecStart=/usr/local/sbin/workstream-aws-proof
TimeoutStartSec=120s
```

```ini
# /etc/systemd/system/workstream-aws-proof.timer
[Unit]
Description=Schedule Workstream AWS artifact proof

[Timer]
OnCalendar=*-*-* *:0/5:00
Persistent=true
AccuracySec=5s
RandomizedDelaySec=10s
Unit=workstream-aws-proof.service

[Install]
WantedBy=timers.target
```

Enable it with `systemctl enable --now workstream-aws-proof.timer`. The hosted
wrapper gives the whole group a 120-second monotonic budget, reserves bounded
cleanup time, names each one-off container from the group nonce and fixed
service, and runs the Python proof under the image's independently verified
`/usr/bin/timeout`. It force-removes that exact container after every Docker
call. A timeout fails the group without running later modes or the coordinator;
it never retries a proof effect automatically. Systemd also refuses to start a
second oneshot while the first is active and applies the same outer 120-second
bound before the next five-minute trigger. The wrapper fails when any job fails;
a successful group follows only the fixed runtime, readiness, negative and
coordinator sequence. It never calls the coordinator alone or
writes a passing database row. Review timer logs for bounded result metadata
only.

Each scheduled readiness proof invokes IAM Access Analyzer custom policy checks
and each group performs S3 probe calls. These AWS operations may incur request
charges; review the official
[IAM Access Analyzer pricing](https://aws.amazon.com/iam/access-analyzer/pricing/)
and the account's S3 pricing before enabling the timer. Repository-local builds
and tests create no AWS resources and make none of these calls.

## Renewal, revocation, and containment

Set an alert well before the 30-day leaf expiry. Renewal means issuing a new
leaf with the same exact role-basename CN and a new private key using the
administrator-managed CA database, verifying its signature, securely staging the pair, stopping the
affected containers, atomically installing the new `0400` files, rerunning
preflight and a complete fresh proof group, and restarting the release. Keep the
old private key only for the approved rollback window, then destroy it under the
key-custody procedure. Never extend validity by copying or editing a certificate.

To revoke a leaf, use the administrator-only CA directory, identify the exact
serial, then issue and verify a new CRL. Serialize signing and revocation so
only one administrator writes the CA database at a time, using the same lock:

```sh
exec 9>.signing.lock
flock -n 9
openssl ca -config openssl.cnf -revoke issued/runtime.cert.pem
openssl ca -config openssl.cnf -gencrl -out crl/workstream-artifacts.crl.pem
openssl crl -in crl/workstream-artifacts.crl.pem -noout -issuer -lastupdate -nextupdate
```

Import and enable the first PEM CRL with `aws rolesanywhere import-crl`; update
the same CRL resource later with `aws rolesanywhere update-crl`. AWS documents
the exact commands in the
[Roles Anywhere CRL reference](https://docs.aws.amazon.com/cli/latest/reference/rolesanywhere/import-crl.html).
Disabling the trust anchor/profile or publishing a CRL prevents future sessions;
it does not by itself guarantee that temporary credentials already issued for a
3600-second session lose permissions immediately.

For emergency containment, stop the affected Workstream processes, disable the
profile or trust anchor, publish the CRL, and revoke active sessions for all
three roles using the AWS IAM **Revoke sessions** operation or its reviewed
`AWSRevokeOlderSessions` equivalent. AWS notes that this deny affects every
session issued before the cutoff; follow the
[IAM role-session revocation procedure](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html).
Confirm old credentials are denied, issue replacement leaves if recovery is
authorized, restore the exact trust, and require a new full proof group before
activation. Preserve PostgreSQL evidence and every retained S3 object throughout
containment and recovery; revocation never authorizes deleting artifact data.
