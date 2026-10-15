# Submission Packet Template

## Task

`<task id>`

## Contributor

`<contributor id>`

## Submission Version

Assigned by Workstream after blocking pre-submit checks pass. The contributor does not provide this value.

## Summary

Briefly describe what was completed.

## Submission Bundle

Upload exactly one outer ZIP. Its internal files and directories must satisfy
the locked Project Guide. Workstream safely inspects that tree and computes all
artifact identity; the contributor does not submit links or storage references.

## Provenance

- generated at:

Workstream records the server-computed outer-ZIP SHA-256/byte count, canonical
semantic manifest including normalized regular-file executable intent, verified
admission, and immutable binding. Those values are
server output, not contributor input.

A successful preparation may return a verified `ready` admission before a
Submission exists. Submission creation obtains fresh authority and atomically
consumes that admission with the immutable Submission/binding. An abandoned
ready admission has no review, contribution, compensation, or reputation
effect, remains capacity-charged, and has no client expiry/release/delete path.

Workstream derives the locked project guide version, locked guide-source
snapshot id/hash, effective project submission artifact policy id/hash,
generated project pre-submit checker policy id/bundle hash, post-submit
checker policy context, review policy version, and revision policy version from
the task's locked context. The contributor does not
provide those ids, versions, hashes, or internal policy bodies in the
submission packet.

Compensation is not submission input. The server stamps the continuing
TaskAssignment's ContributionPolicyVersion on this exact Submission attempt;
ReviewLease later copies that stamped version. A prior checker or human
`needs_revision` preparation may have atomically rebased the continuing Task
and TaskAssignment for this next attempt; publication or submission input alone
cannot change it. Checker preparation is implemented; genuine human Review
integration remains #554 work.

Workstream runs the single effective pre-submission plan against the uploaded
outer ZIP in bounded scratch before creating the submission. The mounted
public authorized ZIP preparation route returns `pre_submission_checker_failed`
with ART's exact ordered bounded results in the same request. ARCH-02I-B
publishes it in OpenAPI with admission-backed Submission creation. Failed preparation creates no
submission row, no submission version, and no submission-created audit event,
and does not return review decision values: `accept`, `needs_revision`, or
`reject`. POL-07B connects the internal checker phase service and removes the
standalone JSON precheck. The admission-backed public Submission route is
delivered by ARCH-02I-B.

The hidden default phase first validates ART's server-generated commitment,
semantic manifest, change result, and one sealed scratch projection. Its
path-redacted same-request entries use `passed`, `warning`, `failed`,
`advisory_disabled`, or `dependency_not_run`; infrastructure, authority,
integrity, timeout, cancellation, and scratch-capacity failures remain distinct
from contributor checker failures. Project-specific rules run later through the
same effective plan, not through a second API or registry.

## Submission Bundle Manifest

Workstream generates this manifest from normalized directory/file paths, entry
type, each file's SHA-256/byte count, and normalized executable intent for
regular files. Valid Unix execute bits normalize to true; non-Unix or invalid
mode metadata defaults false, and directories have no executable value. Other
archive permission metadata is excluded. Nested archives remain opaque in v0.1.

## Evidence

Required evidence files belong inside the same outer ZIP at the paths defined by
the locked Project Guide. The contributor does not submit a separate evidence
URI, provider reference, hash, or evidence ID. After inspection, Workstream may
project server-derived evidence facts:

| Normalized ZIP Path | Server SHA-256 | Byte Count | Locked Requirement |
| --- | --- | --- | --- |
| `<server-derived path>` | `sha256:<64 lowercase hex>` | `<server-derived bytes>` | `<locked project rule>` |

When relevant, the evidence file itself should describe the command,
environment, dataset/version, or generation settings that produced it.

Workstream assigns any evidence identity at persistence time. Checker run IDs
are created only after post-submit internal checks run.

## Draft Checker Notes

Any known contributor-facing context that helps explain the packet. The contributor does not provide checker outcomes, severities, policy versions, or pass/fail statuses.

## Revision Replay

For checker remediation, read the authorized task context and acknowledge its
exact preparation ID/digest during ZIP preparation. The server retains that
acknowledgement through admission and immutable Submission creation. The
corrected ZIP addresses contributor-visible checker messages; this path requires
no ReviewFinding response or contributor-supplied resolution status.

For future human-Review revision (#554), Workstream provides the complete frozen
prior/next guide and policy context. Each unresolved blocking ReviewFinding
requires one immutable bounded SubmissionFindingResponse; see the
[human Revision Replay Template](template_revision_replay.md). The contributor
supplies response text and evidence, while the later reviewer records the
immutable FindingResolution. Neither path accepts guide/policy versions or
finding closure as contributor authority.

Each assignment starts at round 0. Each fixable failure with another revision remaining starts a
fresh PostgreSQL-time window under the failed attempt's locked policy. Only
immutable resubmission ends it; upload, ready admission, replay and repair do
not. Setup blocks pause the allowance and notify the PM; repair resumes only
its remainder. Final-attempt failure immediately rejects and releases the
assignment without another window. Timeout also returns the task to ready.
Either permits any eligible contributor to claim a fresh assignment at round 0.

## Contributor Attestation

I confirm this submission is original, complete, follows the locked project guide, and does not include prohibited confidential material, private source data, credentials, or copied platform artifacts.

I also confirm that any agent-assisted or tool-assisted work was reviewed by me before submission and that I am accountable for the submitted packet.
