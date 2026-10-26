# API drill source assertion — verify originals without fabricated requirements

- Initiative: `None`
- Durable disposition: `Planned`
- Intended merge outcome: The API-drill regression verifies exact original evidence under the checker-only setup contract.

## Intent

Keep the source-read regression meaningful after setup stops generating informational requirements.

## Current behavior

`backend/tests/test_api_contract_e2e.py` indexes `result.requirements[0]`, but the scripted API runtime now correctly returns an empty inventory when it proposes no project checks. The hosted shared-foundations lane fails with `IndexError` although the real API drill passes.

## Bounded change

### Allowed

- `backend/tests/test_api_contract_e2e.py`: replace the obsolete requirement comparison with complete source-reference assertions and the empty project-check inventory.
- This change record.

### Not allowed

- Product code, runtime fixtures, inference validation, migrations, CI selection or gates, skips, and unrelated tests.

## Design and decisions

Assert the source item, original document version and digest directly from the observed document. Preserve the exact neutral read call and invocation count. Require an empty inventory instead of inventing a check for a non-check guide.

## Acceptance criteria

- [x] The existing test passes with the current scripted runtime and verifies the complete original reference.
- [x] The focused API-drill and strict setup contract modules pass together.
- [x] A substituted original reference is detected by the assertion.

## Risk and review routing

- Risk class: `L2`
- Required reviewers: `qa`, `test_delta`
- Human review focus: The repaired assertion retains actual source custody proof without reintroducing out-of-scope generated requirements.

## Evidence

The pre-fix hosted lane retained the exact `IndexError` at the removed requirement. Local reproduction failed at the same assertion. The API-drill and strict setup modules then passed together: 58 tests. Three independent runtime-result mutations (source item, document version and digest) each fail the repaired assertion. Ruff, Commitrail and whitespace checks pass. One local run encountered corrupt generated SDK bytecode; removing that exact cache file allowed Python to rebuild it from installed source. No source or test gate changed to address that environment failure. No deployment or live-provider claim applies.

## Review findings

No production behavior changes are proposed.

## Reconciliation

- Current-source reconciliation: Main `7f6a71a69` merged checker-only setup in #660, Omnicore setup support in #661 and CLI distribution in #664. This fix touches only the stale API-drill assertion.
- Roadmap impact: None; product capability and exposure are unchanged.
- Next usable boundary: None within this repair.
- Remaining risks: Full hosted checks must complete before merge readiness.
