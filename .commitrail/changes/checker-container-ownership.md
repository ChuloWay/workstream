# Checker container ownership — isolate startup recovery

- Initiative: None
- Durable disposition: Planned
- Intended merge outcome: checker startup recovers only its own deployment's containers.

## Intent and current behavior

The CLI journey found ARCH-CLI43-001: startup enumerates every Docker container
with `workstream.external-checker=true`, validates only a generic name/attempt,
and force-removes it. Separate services with separate socket directories can
therefore delete each other's active work on one daemon. The existing socket
parent lock protects only services sharing that directory.

## Bounded change

Allowed: `external_checkers/workstream-checker-service/src/main.rs`,
`external_checkers/workstream-checker-service/tests/container_ownership.py`,
`external_checkers/README.md`, `docs/architecture_checker_framework.md`,
`docs/roadmap_status.md`, and this record.
No checker protocol/result, policy, admission, AUTH, ART, database, dependency,
CI selection, project-image or sandbox privilege changes. No unrelated cleanup.

## Design and decisions

Retain the existing locked private socket directory as deployment custody.
Under that lock, load or exclusively create a private persistent random owner
token, with bounded reads and fail-closed file/type/mode/ownership validation.
Keep the token in memory after startup. Label each created container with that
owner and include it in its name. Startup filters by owner and independently
checks inspected full ID, owner label, generic label, name and attempt before
removing the exact ID. Generic/unowned and foreign containers are never adopted.
The owner file survives process restarts; replacement/corruption fails closed
or leaves orphan cleanup to an operator. Operators must not clone custody
directories into independently running deployments. Docker administrators remain
trusted; labels do not isolate against a malicious daemon administrator.

A per-process random owner would abandon crash recovery; a configured human
string can accidentally collide; path-only hashes collide across container
mount namespaces. A persisted random token uses the existing lock and requires
no extra public configuration or compatibility implementation.

The file is `.workstream-checker-owner`: 32 random bytes encoded as exactly
64 lowercase hexadecimal bytes. Creation uses exclusive `0600` no-follow access
under the pinned, locked parent, followed by file and parent sync. Existing reads
are nonblocking/no-follow and bounded to 65 bytes, requiring a regular file,
one link, effective UID/GID ownership, exact mode/size/content. Partial creation
fails closed. A serde-skipped optional cached owner remains unset until this
protocol succeeds; execution and recovery reject unset or malformed custody.
Loss of this file after prior use cannot be distinguished from first startup:
operators must preserve it and reconcile old exact containers explicitly after
loss; the service never adopts them by their generic label.

## Acceptance criteria

- Two services with different private socket parents have different owners.
- Restart with the same parent preserves its owner and recovers its stale work.
- Starting B cannot remove A's active container; unowned generic containers remain.
- A wrong/missing owner, different inspected ID or mismatched attempt is not removed.
- Malformed, substituted, unsafe or partial owner files reject startup before cleanup.
- Existing request timeout/disconnect cleanup and same-parent lock exclusion remain.
- A regression fails with the prior daemon-wide recovery semantics; real Docker
  proof uses only explicitly created disposable test containers and removes them.

## Risk and review routing

- Risk class: L1 (destructive infrastructure ownership).
- Required reviewers: security; architecture/docs; QA/test delta.
- Human review focus: restart custody, cross-instance isolation, exact deletion
  targets and deployment-directory lifecycle. Human merge only.

## Plan and evidence

Inspect startup/create/recovery and fixtures; review this plan; implement one
owner path; run Rust format/tests/clippy, discriminating fake-Docker tests and
bounded real-Docker ownership proof; freeze and review; open one PR. Then use
the repaired service in the separately scoped CLI journey and retain raw proof.
No deployment, live AWS or completed CLI journey claim follows from this repair.

Future proof (not yet executed): Rust `owner_custody_is_stable_private_and_bounded`
covers distinct parents, restart, unsafe file forms and incomplete creation;
`startup_recovery_is_instance_scoped` uses a stateful fake Docker executable with
A/B/unowned inventories and actual calls through recovery, asserting A/unowned
survive and B disappears; `container_identity_requires_all_ownership_facts`
independently substitutes ID/owner/name/attempt/generic label. Existing
`losing_full_startup_cannot_run_cleanup_under_the_live_owner` and request
timeout/disconnect tests retain their assertions and add owner-qualified targets.
The opt-in process proof `tests/container_ownership.py` starts the built service
with two fresh private directories and real Docker, creates only disposable
containers, records their full IDs, proves restart cleanup and foreign survival,
and tears down only those recorded IDs. This is future executed composition
evidence. No fake is credited as real Docker proof.

## Reconciliation

Base: main `91df16e76`. Open PRs #633/#648/#650 do not modify this Rust owner.
Next usable boundary: safely rerun the pending CLI full journey.
