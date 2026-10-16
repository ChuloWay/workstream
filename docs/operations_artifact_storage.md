# Artifact Storage Operations

This runbook covers the hidden Operator surfaces for immutable artifact
storage. These surfaces diagnose Workstream records; they never expose provider
object references, endpoints, credentials, signed URLs, or raw provider
responses.

## Activation boundary

The routes are composed under `/api/v1/operator/artifacts`, but production
authority remains deny-only while the corresponding Authorization Service
Operator actions are planned. WS-XINT-002-03 activates only the fixed verifier,
pending-work scanner, and put resolver through transaction-bound prepared
authority. It grants no Operator route. Do not add role checks, fallback
constructors, or artifact-owned grant evaluation.

AWS S3 is activation-gated. Configuration supplies only non-secret exact
release, namespace, role/policy and bucket-policy bindings; it cannot assert a
pass. API, worker and Beat startup load an exact fresh activation after the
namespace claim and before credential inspection. Every AWS SDK call reloads
the same activation selected for its logical operation, and ART reloads that ID
inside any provider-derived terminal transaction.

The deployment runs one fixed command separately under each configured proof
identity, using one newly generated non-secret UUID nonce. Run runtime proof
first so its retained challenge object exists, followed by readiness and
negative-access proof, then run credential-free coordination:

```bash
python -m scripts.aws_artifact_provider_proof runtime_immutability --group-nonce <uuid>
python -m scripts.aws_artifact_provider_proof readiness --group-nonce <uuid>
python -m scripts.aws_artifact_provider_proof negative_access --group-nonce <uuid>
python -m scripts.aws_artifact_provider_proof coordinate --group-nonce <uuid>
```

Each proof process first binds its STS-observed caller to its configured role,
performs only that mode's fixed calls, and writes one append-only bounded result
using PostgreSQL time. Coordination has database access and no AWS transport;
it accepts exactly one passing result of every type in the common group. Run
the sequence every five minutes. Results and activations expire 15 minutes from
their individual starts, so overlapping unexpired groups are expected.

Each independently deployed executor supplies its own selected workload-identity
method and identity environment; the common settings contract does not imply
that the runtime, readiness and negative jobs share one credential method.

Do not supply bootstrap credentials or run all modes under one identity. The
readiness identity may inspect only the exact three role attachments/inline
policies and the exact two required managed-policy documents. A failed,
expired, mixed or drifted group cannot activate AWS. An expired activation
during a possibly successful write leaves recoverable acknowledgement-unknown
state; rerun proof and let the existing resolver observe the object.

## Diagnosis sequence

1. Start from the exact project, project guide, snapshot, snapshot item, task,
   submission, or checker run and list its artifact bindings. Review lookup is
   deferred until the review lifecycle owns a canonical review record.
2. Follow the stable `content_id` to replicas. Replica responses contain only
   Workstream identity and verification, availability, and integrity states.
3. Follow a `replica_id` to redacted put receipts and its verification job.
4. Read exact audit events for the selected artifact resource.
5. If a verification job exhausted all attempts with terminal
   `provider_unavailable`, submit a reason-bound retry with a client
   idempotency key and expected source-job CAS version.
6. Follow the returned recovery-attempt ID to the immutable source/retry chain,
   current statuses, terminal mapping, and audit IDs.

Unauthorized, cross-project, and missing resources return the same concealed
not-found response. A retry revalidates actor state, identity link, exact
authority, source lineage, terminal eligibility, and CAS inside its creation
transaction. Never infer success from a database row alone; use the Operator
HTTP response and audit identifiers.

## Admission pressure

`GET /api/v1/operator/artifacts/admission-usage` requires an exact canonical
`project_id` and reports bounded deployment, project, and optional task usage.
It never enumerates producer-scope identifiers. It is read-only: it cannot
release charges, change configuration, or create recovery work.

Each bounded scope also reports submission-bundle pressure as
`unbound_ready_count`/`unbound_ready_bytes` and
`stale_count`/`stale_bytes`. Ready admissions are verified but not yet consumed
by a Submission; stale admissions proved incompatible at a later consumption
boundary. Both remain charged under v0.1 capacity limits. Use these projections
to distinguish abandoned or context-invalid bundles from ordinary artifact
growth; there is no operator deletion or release action.

Every successful admission transaction emits
`workstream_artifact_admission_pressure_total`
for each derived deployment, project, producer, and task scope. The bounded
structured-log metric contains only
`scope_type` (`deployment`, `project`, `producer`, or `task`) and
`pressure_band` (`normal`, `warning`, `critical`, or `exhausted`). Configure
the deployment log collector to aggregate this counter and alert for:

- warning at 75 percent;
- critical at 90 percent;
- exhausted at 100 percent.

Treat a critical or exhausted scope as an incident. Identify whether growth is
expected, confirm that its parent scopes have capacity, and compare the
configured limit with the persisted scope limit. Do not delete admission
charges or edit counters in PostgreSQL.

The v0.1 baseline installs immutable ready-admission custody. Recovery planning
must preserve those facts and move forward with a corrective migration rather
than deleting or bypassing them; the baseline cannot be downgraded.

## Quota expansion and rollback

Quota changes are configuration-driven. Increase the smallest affected scope
and deploy the validated configuration. The next admission transaction locks
the affected counters and reconciles their persisted limits with configuration
using CAS fencing before reserving bytes. Confirm the read-only admission view
reports matching configured and persisted limits. Keep task, producer, project,
and deployment limits mutually consistent.

If the change is wrong, restore the previous configuration and redeploy. The
same locked reconciliation permits a decrease only when it is not below
already-counted bytes. Otherwise admission fails closed: stop new artifact
writes, retain the higher safe limit, and resolve the incident without deleting
charges or directly editing database state.

## Prohibited operations

These routes do not delete, retain, release, or mutate provider objects; change
admission configuration; activate AWS; or cut over any guide, task, submission,
checker, review, contribution, payment, or reputation lifecycle.

## Contributor-intake baseline invariant

The v0.1 baseline contains only the current contributor-intake schema. The
retired upload-session/item shape and version-1 receipt contract are not an
upgrade source. Recreate pre-v0.1 development databases; for production data,
use a separately reviewed evidence-preserving maintenance migration rather
than deleting, detaching, rewriting, or restamping rows.
