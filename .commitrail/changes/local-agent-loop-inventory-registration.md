# Local agent loop inventory registration

- Initiative: None
- Durable disposition: Complete
- Intended merge outcome: restore green `main` after PR #642 by registering its two operator scripts with the behavior-ownership partition and the identifier inventory.

## Intent

PR #642 added `backend/scripts/provision_local_service_actors.py` and
`backend/scripts/transition_review_lifecycle.py`. Neither was registered, so
`main` at `a6b31c56c` fails `behavior_ownership validate`
(`partition_target_mismatch`) and the identifier inventory test (an
unclassified UUIDv5 generation site).

## Bounded change

- Allowed: `.ci/behavior-ownership/partition.v1.json` regenerated with
  `behavior_ownership partition` from its unchanged protected base; a
  `LOCAL_AGENT_LOOP_TARGETS` approved-addition set in
  `backend/scripts/behavior_ownership.py`; one site entry in
  `backend/scripts/identifier_generation_classifications.json`; this record.
- Not allowed: runtime behavior, the scripts themselves, other partition
  assignments, new classification categories.

## Acceptance criteria

- The partition adds exactly the two scripts (groups `shared` and `lifecycle`
  from `group_for_target`) and keeps every other assignment and the protected
  base commit.
- The provisioning script's `idempotency_key` UUIDv5 is classified
  `deterministic_selector`: it is an owner-defined replay selector for the
  admin API, not a persisted record ID.

## Risk and review routing

- Risk class: L1, CI evidence registration with no product behavior change.
- Reviewers: one bounded CI/evidence review.

## Evidence

- `python -m scripts.behavior_ownership validate` exits 0.
- `pytest tests/test_identifier_inventory.py tests/test_behavior_ownership.py`:
  187 passed. Ruff passes on the changed script.
- The `task_lifecycle_d` lane failure on `main`
  (`test_project_pages_and_summary_meet_budget_at_scale`, 1.21 s against a
  1.0 s budget) is a timing budget unrelated to this change and is not
  addressed here.
