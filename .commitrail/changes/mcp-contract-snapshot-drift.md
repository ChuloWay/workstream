# MCP contract snapshot drift — recapture fifteen selected fragments from main

- Initiative: `None`
- Durable disposition: `Planned`
- Intended merge outcome: `mcp-contract / real-api-contract` passes on main because the fifteen drifted snapshots match the backend OpenAPI they pin.

## Intent

Restore a green real-API contract check on main so that drift detection stays meaningful for every open pull request.

## Current behavior

Since #684 merged (`a2ace51f9`), `tests/test_contract_drift.py::test_contracts_match_current_backend_openapi_when_command_is_provided` fails on main and on every pull request. Fifteen snapshots in `mcp_server/contracts/` no longer equal the selected backend OpenAPI fragment: they lack schema `description` fields the backend already emitted before #684, and three guide post-policy snapshots still reference split `PostPolicyTarget-Input` / `PostPolicyTarget-Output` schemas that the current backend emits as one `PostPolicyTarget`.

## Bounded change

### Allowed

- The fifteen drifted snapshots: `actor_assignments_list`, `contribution_policies_list`, `contribution_policy_current_get`, `contribution_policy_get`, `contribution_policy_create`, `contribution_policy_update`, `contribution_policy_publish`, `contribution_policy_retire`, `project_assignments_list`, `ready_tasks_list`, `guide_activate`, `guide_post_policy_get`, `guide_post_policy_approve`, `guide_post_policy_correct`, `guide_proposal_get`.
- This change record.

### Not allowed

- Backend code, MCP gateway code, the drift test and its comparison rules, other snapshots, CI workflows, skips or gate changes.

## Design and decisions

Each snapshot is recaptured with the drift test's own `_selected` fragment selection and `_without_schema_titles` normalization, from backend OpenAPI generated at main `59c52cc81` with `uv run --frozen` on linux/amd64 (the CI command). `source.repository_sha` records that commit and `canonical_sha256` is recomputed with the test's `_canonical` encoding. The other seventy-five snapshots already match and are unchanged.

## Acceptance criteria

- [x] `tests/test_contract_drift.py` passes with `WORKSTREAM_MCP_OPENAPI_COMMAND` set as in CI (76 passed).
- [x] Every snapshot's tamper-evident hash test passes.
- [x] The MCP unit suite and ruff pass unchanged.

## Risk and review routing

- Risk class: `L2`
- Required reviewers: `qa`, `test_delta`
- Human review focus: The recaptured fragments reflect the intended backend contract; the `PostPolicyTarget` merge and restored descriptions are backend facts, not new MCP behavior.

## Evidence

Main runs `40118981845` and `40128815712` fail `mcp-contract / real-api-contract`; the last passing main run is `40117285248` (`f45036433`), immediately before #684. A linux/amd64 `uv run --frozen` OpenAPI export of main was byte-for-byte equal, as parsed JSON, to a local export pinned to the locked pydantic 2.13.5, fastapi 0.141.1 and starlette 1.3.1. In that container: ruff passes, the MCP unit suite gives 770 passed and 3 skipped, and the contract drift module gives 76 passed. No deployment or live-provider claim applies.

## Review findings

No production behavior changes are proposed. Response validation now pins the current backend schemas for these fifteen operations.

## Reconciliation

- Current-source reconciliation: Main `59c52cc81` includes #684 (MCP guide checker and artifact tools) and #681. This change touches only the drifted snapshots.
- Roadmap impact: None; MCP capability and exposure are unchanged.
- Next usable boundary: None within this repair.
- Remaining risks: Full hosted checks must complete before merge readiness.
